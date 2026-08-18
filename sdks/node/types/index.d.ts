import { EventEmitter } from "node:events";

export const PROTOCOL_VERSION: "1";
export const DEFAULT_HEARTBEAT_MS: number;
export const CLOSE_UNAUTHORIZED: 4401;
export const UUID_BYTES: 16;
export const AUDIO_ENCODING: "pcm_s16le";
export const AUDIO_SAMPLE_RATE: 16000;
export const AUDIO_CHANNELS: 1;

export class AuthenticationError extends Error {}
export class RateLimitedError extends Error {}

export interface AudioFrame {
  callId: string;
  pcm: Buffer;
}

export function encodeAudioFrame(callId: string, pcm: Buffer | Uint8Array): Buffer;
export function decodeAudioFrame(frame: Buffer | Uint8Array | ArrayBuffer): AudioFrame;

export interface GatewayClientOptions {
  gatewayUrl: string;
  apiKey: string;
  agentSlug: string;
  heartbeatIntervalMs?: number;
  reconnect?: boolean;
  maxBackoffMs?: number;
}

export interface ControlOptions {
  /** Reuse a request id to make a retry idempotent. */
  requestId?: string;
}

export interface CallEvent {
  type: string;
  call_id?: string;
  request_id?: string;
  connection_id?: string;
  digit?: string;
  code?: string;
  message?: string;
  sequence?: number;
  agent_slug?: string;
  media?: { encoding: string; sample_rate: number; channels: number };
  caller?: Record<string, unknown>;
  [key: string]: unknown;
}

export type RouteTarget = "queue" | "ring_group" | "voicemail";

export class GatewayClient extends EventEmitter {
  constructor(options: GatewayClientOptions);

  readonly gatewayUrl: string;
  readonly agentSlug: string;
  connectionId: string | null;

  realtimeToken(): Promise<string>;
  start(): Promise<void>;
  close(): Promise<void>;

  sendAudio(callId: string, pcm: Buffer | Uint8Array): void;
  control(
    callId: string,
    command: string,
    payload?: Record<string, unknown>,
    options?: ControlOptions,
  ): string;

  hangup(callId: string, options?: ControlOptions): string;
  hold(callId: string, options?: ControlOptions): string;
  resume(callId: string, options?: ControlOptions): string;
  mute(callId: string, options?: ControlOptions): string;
  unmute(callId: string, options?: ControlOptions): string;
  sendDtmf(callId: string, digits: string, options?: ControlOptions): string;
  clearAudio(callId: string, options?: ControlOptions): string;
  transferBlind(callId: string, context: string, extension: string, options?: ControlOptions): string;
  transferAttended(callId: string, context: string, extension: string, options?: ControlOptions): string;
  transferCancel(callId: string, options?: ControlOptions): string;
  route(
    callId: string,
    target: RouteTarget,
    context: string,
    extension: string,
    options?: ControlOptions,
  ): string;
  originate(
    context: string,
    extension: string,
    options?: { timeout?: number; requestId?: string },
  ): string;
  cancelOutbound(callId: string): void;

  on(event: "audio", listener: (frame: AudioFrame) => void): this;
  on(event: "event", listener: (payload: CallEvent) => void): this;
  on(event: "close", listener: (info: { code: number; reason: string }) => void): this;
  on(event: "reconnecting", listener: (info: { delayMs: number; cause: Error }) => void): this;
  on(event: "error", listener: (error: Error) => void): this;
  on(event: string, listener: (payload: CallEvent) => void): this;
}

export default GatewayClient;
