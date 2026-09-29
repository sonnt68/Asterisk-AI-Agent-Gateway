/** Realtime protocol v1 client: token exchange, session, audio, and control. */

import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";

import WebSocket from "ws";

import { decodeAudioFrame, encodeAudioFrame } from "./frames.js";

export {
  AUDIO_CHANNELS,
  AUDIO_ENCODING,
  AUDIO_SAMPLE_RATE,
  DEFAULT_AUDIO_SAMPLE_RATE,
  decodeAudioFrame,
  encodeAudioFrame,
} from "./frames.js";

export const PROTOCOL_VERSION = "1";
export const DEFAULT_HEARTBEAT_MS = 10_000;

const INITIAL_BACKOFF_MS = 1000;
const MAX_AUTHENTICATION_ATTEMPTS = 4;

/** Close code the gateway uses for a dead token or a revoked key. */
export const CLOSE_UNAUTHORIZED = 4401;

/** The API key or realtime token was refused; connection flows may retry before surfacing it. */
export class AuthenticationError extends Error {
  constructor(message) {
    super(message);
    this.name = "AuthenticationError";
  }
}

/** Token exchange exceeded the per-key rate limit. */
export class RateLimitedError extends Error {
  constructor(message) {
    super(message);
    this.name = "RateLimitedError";
  }
}

/**
 * One partner connection to one `agentSlug`.
 *
 * The gateway allows a single live connection per slug, so run exactly one
 * client per slug. Emits every JSON event under its own `type` name, plus
 * `audio` for decoded binary frames.
 */
export class GatewayClient extends EventEmitter {
  #apiKey;
  #socket = null;
  #heartbeat = null;
  #closing = false;
  #backoff = INITIAL_BACKOFF_MS;
  #authFailures = 0;
  #retryTimer = null;
  #retryWaiters = [];

  constructor({
    gatewayUrl,
    apiKey,
    agentSlug,
    heartbeatIntervalMs = DEFAULT_HEARTBEAT_MS,
    reconnect = true,
    maxBackoffMs = 30_000,
  }) {
    super();
    if (!gatewayUrl || !apiKey || !agentSlug) {
      throw new TypeError("gatewayUrl, apiKey and agentSlug are all required");
    }
    this.gatewayUrl = gatewayUrl.replace(/\/$/, "");
    this.agentSlug = agentSlug;
    this.heartbeatIntervalMs = heartbeatIntervalMs;
    this.reconnect = reconnect;
    this.maxBackoffMs = maxBackoffMs;
    this.connectionId = null;
    this.#apiKey = apiKey;
  }

  /** Exchange the long-lived API key for a five-minute realtime token. */
  async realtimeToken() {
    const response = await fetch(`${this.gatewayUrl}/api/v1/realtime/tokens`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.#apiKey}` },
    });
    if (response.status === 401 || response.status === 403) {
      throw new AuthenticationError(
        `Gateway refused the API key with HTTP ${response.status}. The key is invalid, ` +
          "revoked, expired, or its partner app is disabled.",
      );
    }
    if (response.status === 429) {
      throw new RateLimitedError(
        "Token exchange is rate limited. Reuse the live token instead of re-minting.",
      );
    }
    if (!response.ok) {
      throw new Error(`Token exchange failed with HTTP ${response.status}`);
    }
    return (await response.json()).token;
  }

  /**
   * Connect, register, and keep the session alive.
   *
   * Resolves once the first socket is open. Authentication failures receive a
   * bounded fresh-token retry budget; other transport failures reconnect with
   * the existing exponential backoff.
   */
  async start() {
    this.#authFailures = 0;
    this.#backoff = INITIAL_BACKOFF_MS;
    this.#closing = false;
    try {
      await this.#connect({ initial: true });
    } catch (error) {
      if (!this.#closing) throw error;
    }
  }

  /**
   * Stop reconnecting and close the socket.
   *
   * The gateway hangs up every call this connection owns, so drain in-flight
   * calls before calling this.
   */
  async close() {
    this.#closing = true;
    this.#clearRetry();
    this.#stopHeartbeat();
    this.connectionId = null;
    const socket = this.#socket;
    this.#socket = null;
    if (
      socket &&
      (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
    ) {
      if (socket.readyState === WebSocket.CONNECTING) {
        this.#abortSocket(socket);
      } else {
        socket.close(1000, "client shutdown");
      }
    }
  }

  /** Send mono PCM s16le at the rate `call.started` announced for this call. */
  sendAudio(callId, pcm) {
    this.#requireSocket().send(encodeAudioFrame(callId, pcm));
  }

  /**
   * Send a scoped control command; returns the `requestId` used.
   *
   * The gateway remembers accepted results per connection, so replaying the
   * same `requestId` never runs the ARI action twice.
   */
  control(callId, command, payload, { requestId = randomUUID() } = {}) {
    const message = { type: "call.control", request_id: requestId, call_id: callId, command };
    if (payload) message.payload = payload;
    this.#send(message);
    return requestId;
  }

  /** End the call. Requires `calls:hangup`. */
  hangup(callId, options) {
    return this.control(callId, "call.hangup", undefined, options);
  }

  /** Place the caller on hold. Requires `calls:hold`. */
  hold(callId, options) {
    return this.control(callId, "call.hold", undefined, options);
  }

  /** Take the caller off hold. Requires `calls:hold`. */
  resume(callId, options) {
    return this.control(callId, "call.resume", undefined, options);
  }

  /** Mute the channel in both directions. Requires `calls:mute`. */
  mute(callId, options) {
    return this.control(callId, "call.mute", undefined, options);
  }

  /** Unmute the channel. Requires `calls:mute`. */
  unmute(callId, options) {
    return this.control(callId, "call.unmute", undefined, options);
  }

  /** Play DTMF digits into the call. Requires `calls:dtmf`. */
  sendDtmf(callId, digits, options) {
    return this.control(callId, "dtmf.send", { digits }, options);
  }

  /** Drop buffered playback audio. Requires `media:control`. */
  clearAudio(callId, options) {
    return this.control(callId, "audio.clear", undefined, options);
  }

  /**
   * Play an Asterisk media file into the call. Requires `media:playback`.
   *
   * `media` must be `sound:<name>` or `recording:<name>`; every other scheme
   * is refused. The accepted response carries the `playback_id`.
   */
  startPlayback(callId, media, options) {
    return this.control(callId, "playback.start", { media }, options);
  }

  /** Stop a playback this call started. Requires `media:playback`. */
  stopPlayback(callId, playbackId, options) {
    return this.control(callId, "playback.stop", { playback_id: playbackId }, options);
  }

  /**
   * Set a channel variable. Requires `channel:variables`.
   *
   * Names live in the partner namespace and must match `AI_[A-Z0-9_]`;
   * dialplan functions such as `CHANNEL(...)` are refused.
   */
  setVariable(callId, variable, value, options) {
    return this.control(callId, "channel.set_var", { variable, value }, options);
  }

  /**
   * Hand the call back to the dialplan. Requires `calls:dialplan`.
   * The destination must be allowlisted, exactly as for a transfer.
   */
  continueInDialplan(callId, context, extension, options) {
    return this.control(callId, "dialplan.continue", { context, extension }, options);
  }

  /** Redirect the call. Destination must be allowlisted; `calls:transfer`. */
  transferBlind(callId, context, extension, options) {
    return this.control(callId, "transfer.blind", { context, extension }, options);
  }

  /** Start a consulting transfer. Destination must be allowlisted; `calls:transfer`. */
  transferAttended(callId, context, extension, options) {
    return this.control(callId, "transfer.attended", { context, extension }, options);
  }

  /** Abandon a consulting transfer. Requires `calls:transfer`. */
  transferCancel(callId, options) {
    return this.control(callId, "transfer.cancel", undefined, options);
  }

  /** Route to `queue`, `ring_group` or `voicemail`. Requires `calls:route`. */
  route(callId, target, context, extension, options) {
    if (!["queue", "ring_group", "voicemail"].includes(target)) {
      throw new TypeError("Route target must be queue, ring_group or voicemail");
    }
    return this.control(callId, `route.${target}`, { context, extension }, options);
  }

  /**
   * Place an outbound call. Requires `calls:originate`.
   *
   * The call is live only once `call.started` arrives; `outbound.accepted`
   * merely means Asterisk took the request.
   */
  originate(context, extension, { timeout = 30, requestId = randomUUID() } = {}) {
    if (!Number.isInteger(timeout) || timeout < 1 || timeout > 120) {
      throw new RangeError("Outbound timeout must be an integer between 1 and 120 seconds");
    }
    this.#send({
      type: "outbound.originate",
      request_id: requestId,
      payload: { context, extension, timeout },
    });
    return requestId;
  }

  /** Hang up an outbound call this connection started. */
  cancelOutbound(callId) {
    this.#send({ type: "outbound.cancel", call_id: callId });
  }

  // ------------------------------------------------------------- internals

  async #connect({ initial = false } = {}) {
    let token;
    try {
      token = await this.realtimeToken();
    } catch (error) {
      if (this.#closing || !this.reconnect) throw error;
      if (error instanceof AuthenticationError) {
        return this.#retryAuthentication(error, initial);
      }
      this.#scheduleReconnect(error);
      return;
    }

    if (this.#closing) throw new Error("Realtime connection closed before opening");
    const url = `${this.gatewayUrl.replace(/^http/, "ws")}/v1/realtime?token=${encodeURIComponent(token)}`;
    const socket = new WebSocket(url);
    this.#socket = socket;

    let opened = false;
    let openingSettled = false;
    let resolveOpening;
    let rejectOpening;
    const opening = new Promise((resolve, reject) => {
      resolveOpening = resolve;
      rejectOpening = reject;
    });
    const cleanupOpening = () => {
      socket.off("open", onOpen);
      socket.off("unexpected-response", onUnexpectedResponse);
    };
    const cleanupSocket = () => {
      cleanupOpening();
      socket.off("error", onError);
      socket.off("close", onClose);
      socket.off("message", onMessage);
    };
    const settleOpening = (callback, value) => {
      if (openingSettled) return;
      openingSettled = true;
      cleanupOpening();
      callback(value);
    };
    const onOpen = () => {
      opened = true;
      settleOpening(resolveOpening);
    };
    const onError = (error) => {
      if (opened) {
        this.emit("error", error);
      } else if (!openingSettled) {
        settleOpening(rejectOpening, this.#authenticationError(error) ?? error);
      }
    };
    const onUnexpectedResponse = (_request, response) => {
      response?.resume?.();
      settleOpening(rejectOpening, this.#handshakeError(response?.statusCode));
    };
    const onMessage = (data, isBinary) => this.#receive(data, isBinary, socket);
    const onClose = (code, reason) => {
      if (!opened) {
        settleOpening(rejectOpening, this.#closeError(code));
        return;
      }
      const current = this.#socket === socket;
      if (current) {
        this.#stopHeartbeat();
        this.connectionId = null;
        this.#socket = null;
      }
      this.emit("close", { code, reason: reason?.toString() ?? "" });
      if (!current || this.#closing) return;
      if (code === CLOSE_UNAUTHORIZED) {
        this.#handlePostStartAuthenticationFailure(this.#closeError(code));
        return;
      }
      if (this.reconnect) this.#scheduleReconnect(new Error(`closed ${code}`));
    };

    socket.on("message", onMessage);
    socket.on("error", onError);
    socket.once("open", onOpen);
    socket.once("unexpected-response", onUnexpectedResponse);
    socket.on("close", onClose);

    try {
      await opening;
    } catch (error) {
      cleanupSocket();
      if (this.#socket === socket) this.#socket = null;
      this.#abortSocket(socket);
      if (this.#closing || !this.reconnect) throw error;
      const authenticationError = this.#authenticationError(error);
      if (authenticationError) {
        return this.#retryAuthentication(authenticationError, initial);
      }
      this.#scheduleReconnect(error);
      return;
    }

    if (this.#closing) {
      this.#abortSocket(socket);
      throw new Error("Realtime connection closed before opening");
    }
    if (this.#socket !== socket || socket.readyState !== WebSocket.OPEN) return;

    this.#send({
      type: "session.register",
      agent_slug: this.agentSlug,
      protocol_version: PROTOCOL_VERSION,
    });
    this.#startHeartbeat();
  }

  #receive(data, isBinary, socket) {
    if (socket !== this.#socket || this.#closing) return;
    if (isBinary) {
      this.emit("audio", decodeAudioFrame(data));
      return;
    }
    let event;
    try {
      event = JSON.parse(data.toString());
    } catch (error) {
      this.emit("error", error);
      return;
    }
    if (event.type === "session.ready") {
      this.connectionId = event.connection_id;
      this.#authFailures = 0;
      this.#backoff = INITIAL_BACKOFF_MS;
    }
    this.emit("event", event);
    if (event.type) this.emit(event.type, event);
  }

  #scheduleReconnect(cause, { keepAlive = false } = {}) {
    if (this.#retryTimer && keepAlive) this.#retryTimer.ref?.();
    if (this.#closing || !this.reconnect || this.#retryTimer) return null;
    const delay = Math.min(this.#backoff, this.maxBackoffMs);
    this.#backoff = Math.min(this.#backoff * 2, this.maxBackoffMs);
    const timer = setTimeout(() => {
      if (this.#retryTimer !== timer) return;
      this.#retryTimer = null;
      const waiters = this.#retryWaiters.splice(0);
      waiters.forEach((resolve) => resolve(!this.#closing));
      if (waiters.length || this.#closing) return;
      this.#connect().catch((error) => {
        if (!this.#closing) this.emit("error", error);
      });
    }, delay);
    this.#retryTimer = timer;
    if (!keepAlive) timer.unref?.();
    this.emit("reconnecting", { delayMs: delay, cause });
    return null;
  }

  async #retryAuthentication(error, initial) {
    this.#authFailures += 1;
    if (
      this.#closing ||
      !this.reconnect ||
      this.#authFailures >= MAX_AUTHENTICATION_ATTEMPTS
    ) {
      throw error;
    }

    if (!initial) {
      this.#scheduleReconnect(error, { keepAlive: true });
      return;
    }

    const retry = this.#waitForRetry(error);
    if (!(await retry)) throw error;
    return this.#connect({ initial: true });
  }

  #waitForRetry(cause) {
    if (this.#retryTimer) {
      return new Promise((resolve) => this.#retryWaiters.push(resolve));
    }
    let resolveRetry;
    const retry = new Promise((resolve) => {
      resolveRetry = resolve;
      this.#retryWaiters.push(resolve);
    });
    this.#scheduleReconnect(cause, { keepAlive: true });
    if (!this.#retryTimer) {
      this.#retryWaiters = this.#retryWaiters.filter((resolve) => resolve !== resolveRetry);
      resolveRetry(false);
    }
    return retry;
  }

  #handlePostStartAuthenticationFailure(error) {
    this.#authFailures += 1;
    if (
      this.#closing ||
      !this.reconnect ||
      this.#authFailures >= MAX_AUTHENTICATION_ATTEMPTS
    ) {
      if (!this.#closing) this.emit("error", error);
      return;
    }
    this.#scheduleReconnect(error, { keepAlive: true });
  }

  #clearRetry() {
    if (this.#retryTimer) clearTimeout(this.#retryTimer);
    this.#retryTimer = null;
    const waiters = this.#retryWaiters.splice(0);
    waiters.forEach((resolve) => resolve(false));
  }

  #authenticationError(error) {
    if (error instanceof AuthenticationError) return error;
    const status = Number(error?.statusCode ?? error?.status ?? error?.code);
    if ([401, 403].includes(status)) {
      return new AuthenticationError(
        `Gateway refused the WebSocket handshake with HTTP ${status}. The token or API key ` +
          "is invalid, revoked, expired, or its partner app is disabled.",
      );
    }
    if (/unexpected server response:\s*(401|403)\b/i.test(error?.message ?? "")) {
      const matchedStatus = error.message.match(/(401|403)\b/)[1];
      return new AuthenticationError(
        `Gateway refused the WebSocket handshake with HTTP ${matchedStatus}. The token or API key ` +
          "is invalid, revoked, expired, or its partner app is disabled.",
      );
    }
    return null;
  }

  #handshakeError(status) {
    if ([401, 403].includes(Number(status))) {
      return new AuthenticationError(
        `Gateway refused the WebSocket handshake with HTTP ${status}. The token or API key ` +
          "is invalid, revoked, expired, or its partner app is disabled.",
      );
    }
    return new Error(`Gateway WebSocket handshake failed with HTTP ${status}`);
  }

  #closeError(code) {
    if (code === CLOSE_UNAUTHORIZED) {
      return new AuthenticationError(
        "Gateway closed the session with 4401: the token expired or the API key was revoked.",
      );
    }
    return new Error(`closed ${code}`);
  }

  #abortSocket(socket) {
    if (
      socket?.readyState === WebSocket.OPEN ||
      socket?.readyState === WebSocket.CONNECTING
    ) {
      if (socket.readyState === WebSocket.CONNECTING && socket.terminate) {
        socket.once("error", () => {});
        socket.terminate();
      } else {
        socket.close(1000, "connection attempt cancelled");
      }
    }
  }

  #startHeartbeat() {
    this.#stopHeartbeat();
    this.#heartbeat = setInterval(() => {
      if (this.#socket?.readyState === WebSocket.OPEN) this.#send({ type: "heartbeat" });
    }, this.heartbeatIntervalMs);
    this.#heartbeat.unref?.();
  }

  #stopHeartbeat() {
    if (this.#heartbeat) clearInterval(this.#heartbeat);
    this.#heartbeat = null;
  }

  #send(message) {
    this.#requireSocket().send(JSON.stringify(message));
  }

  #requireSocket() {
    if (!this.#socket || this.#socket.readyState !== WebSocket.OPEN) {
      throw new Error("Realtime session is not connected");
    }
    return this.#socket;
  }
}

export default GatewayClient;
