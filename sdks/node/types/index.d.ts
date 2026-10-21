import { EventEmitter } from "node:events";

export const PROTOCOL_VERSION: "1";
export const DEFAULT_HEARTBEAT_MS: number;
export const PARTNER_CALLS_PATH: "/api/v1/partner/calls";
export const CLOSE_UNAUTHORIZED: 4401;
export const CLOSE_SUPERSEDED: 4409;
export const UUID_BYTES: 16;
export const AUDIO_ENCODING: "pcm_s16le";
export const DEFAULT_AUDIO_SAMPLE_RATE: 8000;
/** @deprecated Read `call.started`'s `media.sample_rate` instead. */
export const AUDIO_SAMPLE_RATE: 8000;
export const AUDIO_CHANNELS: 1;

export class AuthenticationError extends Error {}
export class RateLimitedError extends Error {}
export class GatewayHttpError extends Error {
  constructor(status: number, options?: { method?: string; path?: string });
  readonly status: number;
  readonly statusCode: number;
  readonly method: string;
  readonly path: string;
}
export { GatewayHttpError as GatewayHTTPError };
/** A newer connection registered this agent slug; the client has stopped. */
export class SessionSupersededError extends Error {}

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

export interface CallRecord {
  call_id: string;
  partner_app_id: string | null;
  agent_slug: string | null;
  direction: string;
  source: string;
  status: string;
  terminal: boolean;
  answered: boolean;
  reason: string | null;
  hangup_cause: number | null;
  dial_status: string | null;
  sequence: number;
  created_at: string;
  updated_at: string;
  answered_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  talk_seconds: number | null;
  history_complete: boolean;
  [key: string]: unknown;
}

export interface CallSignal {
  type?: string;
  call_id: string;
  status: string;
  terminal: boolean;
  answered: boolean;
  reason: string | null;
  hangup_cause: number | null;
  dial_status: string | null;
  sequence: number;
  updated_at: string;
  [key: string]: unknown;
}

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
}

export interface CallListResponse extends PaginatedResponse<CallRecord> {
  /** Numbered page when `page` was requested; null for cursor pagination. */
  page: number | null;
  page_size: number | null;
  total: number | null;
  total_pages: number | null;
}

export type CallSignalListResponse = PaginatedResponse<CallSignal>;

export interface CallListOptions {
  /** Gateway defaults to 50 and accepts at most 100. */
  limit?: number;
  cursor?: string;
  status?: string;
  direction?: string;
  /** Exact agent slug filter; the Gateway accepts at most 80 characters. */
  agentSlug?: string;
  /** Numbered page (1..2147483647); combining with cursor returns HTTP 422. */
  page?: number;
  startedAfter?: string;
  startedBefore?: string;
  /** REST spelling accepted when mirroring the exact agent filter query name. */
  agent_slug?: string;
  started_after?: string;
  started_before?: string;
}

export interface CallSignalsOptions {
  /** Gateway defaults to 50 and accepts at most 100. */
  limit?: number;
  cursor?: string;
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
  listCalls(options?: CallListOptions): Promise<CallListResponse>;
  getCall(callId: string): Promise<CallRecord>;
  listCallSignals(callId: string, options?: CallSignalsOptions): Promise<CallSignalListResponse>;
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
  startPlayback(callId: string, media: string, options?: ControlOptions): string;
  stopPlayback(callId: string, playbackId: string, options?: ControlOptions): string;
  setVariable(callId: string, variable: string, value: string | number | boolean, options?: ControlOptions): string;
  continueInDialplan(callId: string, context: string, extension: string, options?: ControlOptions): string;
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
    options?: { timeout?: number; requestId?: string; callerNumber?: string },
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
