import assert from "node:assert/strict";
import { test } from "node:test";

import { GatewayClient, decodeAudioFrame, encodeAudioFrame } from "../src/index.js";

const CALL_ID = "8c1f4b2e-0d5a-4f77-9a51-6b0c7e2d3a44";

test("audio frame roundtrip preserves call and payload", () => {
  const frame = encodeAudioFrame(CALL_ID, Buffer.from([1, 2, 3, 4]));
  assert.equal(frame.length, 20);
  const { callId, pcm } = decodeAudioFrame(frame);
  assert.equal(callId, CALL_ID);
  assert.deepEqual([...pcm], [1, 2, 3, 4]);
});

test("audio frame rejects payload without pcm", () => {
  assert.throws(() => encodeAudioFrame(CALL_ID, Buffer.alloc(0)), TypeError);
});

test("audio frame rejects a call id that is not a uuid", () => {
  assert.throws(() => encodeAudioFrame("not-a-uuid", Buffer.from([1])), TypeError);
});

test("decode rejects a frame that carries no pcm", () => {
  assert.throws(() => decodeAudioFrame(Buffer.alloc(16)), RangeError);
});

test("originate rejects timeouts outside gateway bounds", () => {
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    apiKey: "agw_live_a_b",
    agentSlug: "support-agent",
  });
  assert.throws(() => client.originate("from-internal", "1002", { timeout: 0 }), RangeError);
  assert.throws(() => client.originate("from-internal", "1002", { timeout: 121 }), RangeError);
});

test("route rejects targets the gateway has no command for", () => {
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    apiKey: "agw_live_a_b",
    agentSlug: "support-agent",
  });
  assert.throws(() => client.route("call", "parking_lot", "ctx", "1001"), TypeError);
});

test("control without a session fails loudly", () => {
  const client = new GatewayClient({
    gatewayUrl: "https://gateway.example.com",
    apiKey: "agw_live_a_b",
    agentSlug: "support-agent",
  });
  assert.throws(() => client.hangup(CALL_ID), /not connected/);
});

test("constructor requires every credential", () => {
  assert.throws(() => new GatewayClient({ gatewayUrl: "https://x", apiKey: "k" }), TypeError);
});
