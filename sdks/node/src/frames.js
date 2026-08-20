/**
 * Binary audio envelope for realtime protocol v1.
 *
 * Every audio frame is the 16 raw bytes of the gateway call UUID followed by
 * mono PCM samples. Nothing else may be prepended: the gateway routes on those
 * first 16 bytes.
 *
 * The encoding and rate are not fixed here. The gateway announces them per call
 * in `call.started`'s `media` block, because a deployment bridging plain
 * telephony carries 8 kHz while one bridging wideband endpoints carries more.
 * Read them from the event; the constants below are only the common default.
 */

export const UUID_BYTES = 16;

export const AUDIO_ENCODING = "pcm_s16le";
export const DEFAULT_AUDIO_SAMPLE_RATE = 8000;
/** @deprecated Read `call.started`'s `media.sample_rate` instead. */
export const AUDIO_SAMPLE_RATE = DEFAULT_AUDIO_SAMPLE_RATE;
export const AUDIO_CHANNELS = 1;

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Wrap PCM audio for `callId` in the protocol v1 envelope. */
export function encodeAudioFrame(callId, pcm) {
  if (!UUID_PATTERN.test(String(callId))) {
    throw new TypeError(`Not a gateway call UUID: ${callId}`);
  }
  const payload = Buffer.isBuffer(pcm) ? pcm : Buffer.from(pcm);
  if (payload.length === 0) {
    throw new TypeError("Audio frame needs PCM payload after the call UUID");
  }
  const uuid = Buffer.from(String(callId).replace(/-/g, ""), "hex");
  return Buffer.concat([uuid, payload], UUID_BYTES + payload.length);
}

/** Split a binary frame into `{ callId, pcm }`. */
export function decodeAudioFrame(frame) {
  const buffer = Buffer.isBuffer(frame) ? frame : Buffer.from(frame);
  if (buffer.length <= UUID_BYTES) {
    throw new RangeError("Binary audio frame is too short to carry PCM");
  }
  const hex = buffer.subarray(0, UUID_BYTES).toString("hex");
  const callId = [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20, 32),
  ].join("-");
  return { callId, pcm: buffer.subarray(UUID_BYTES) };
}
