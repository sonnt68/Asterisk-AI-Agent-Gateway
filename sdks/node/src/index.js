/** Realtime protocol v1 client: token exchange, session, audio, and control. */

import { EventEmitter } from "node:events";
import { randomUUID } from "node:crypto";

import WebSocket from "ws";

import { decodeAudioFrame, encodeAudioFrame } from "./frames.js";

export {
  AUDIO_CHANNELS,
  AUDIO_ENCODING,
  AUDIO_SAMPLE_RATE,
  decodeAudioFrame,
  encodeAudioFrame,
} from "./frames.js";

export const PROTOCOL_VERSION = "1";
export const DEFAULT_HEARTBEAT_MS = 10_000;

/** Close code the gateway uses for a dead token or a revoked key. */
export const CLOSE_UNAUTHORIZED = 4401;

/** The API key or realtime token was refused; retrying does not help. */
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
  #backoff = 1000;

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
   * Resolves once the first socket is open. Transport failures reconnect with
   * a fresh token; an `AuthenticationError` is emitted on `error` and stops
   * the client, because no retry revives a revoked key.
   */
  async start() {
    this.#closing = false;
    await this.#connect();
  }

  /**
   * Stop reconnecting and close the socket.
   *
   * The gateway hangs up every call this connection owns, so drain in-flight
   * calls before calling this.
   */
  async close() {
    this.#closing = true;
    this.#stopHeartbeat();
    if (this.#socket && this.#socket.readyState === WebSocket.OPEN) {
      this.#socket.close(1000, "client shutdown");
    }
    this.#socket = null;
  }

  /** Send PCM s16le 16 kHz mono audio to a call the connection owns. */
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

  async #connect() {
    let token;
    try {
      token = await this.realtimeToken();
    } catch (error) {
      if (error instanceof AuthenticationError || !this.reconnect || this.#closing) throw error;
      this.#scheduleReconnect(error);
      return;
    }

    const url = `${this.gatewayUrl.replace(/^http/, "ws")}/v1/realtime?token=${encodeURIComponent(token)}`;
    const socket = new WebSocket(url);
    this.#socket = socket;

    await new Promise((resolve, reject) => {
      socket.once("open", resolve);
      socket.once("error", reject);
    }).catch((error) => {
      if (!this.reconnect || this.#closing) throw error;
      this.#scheduleReconnect(error);
    });

    if (socket.readyState !== WebSocket.OPEN) return;

    this.#backoff = 1000;
    this.#send({
      type: "session.register",
      agent_slug: this.agentSlug,
      protocol_version: PROTOCOL_VERSION,
    });
    this.#startHeartbeat();

    socket.on("message", (data, isBinary) => this.#receive(data, isBinary));
    socket.on("error", (error) => this.emit("error", error));
    socket.on("close", (code, reason) => {
      this.#stopHeartbeat();
      this.connectionId = null;
      this.emit("close", { code, reason: reason?.toString() ?? "" });
      if (code === CLOSE_UNAUTHORIZED) {
        this.emit(
          "error",
          new AuthenticationError(
            "Gateway closed the session with 4401: the token expired or the API key was revoked.",
          ),
        );
        return;
      }
      if (!this.#closing && this.reconnect) this.#scheduleReconnect(new Error(`closed ${code}`));
    });
  }

  #receive(data, isBinary) {
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
    if (event.type === "session.ready") this.connectionId = event.connection_id;
    this.emit("event", event);
    if (event.type) this.emit(event.type, event);
  }

  #scheduleReconnect(cause) {
    const delay = this.#backoff;
    this.#backoff = Math.min(this.#backoff * 2, this.maxBackoffMs);
    this.emit("reconnecting", { delayMs: delay, cause });
    setTimeout(() => {
      if (this.#closing) return;
      this.#connect().catch((error) => this.emit("error", error));
    }, delay).unref?.();
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
