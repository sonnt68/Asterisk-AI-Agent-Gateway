import assert from "node:assert/strict";
import { test } from "node:test";

import { GatewayClient } from "../src/index.js";
import { LoopbackGateway } from "./auth-retry-loopback.js";

const API_KEY = "agw_live_wire_test";

async function connectedClient(gateway) {
  const client = new GatewayClient({
    gatewayUrl: gateway.url,
    apiKey: API_KEY,
    agentSlug: "wire-agent",
    reconnect: false,
    heartbeatIntervalMs: 60_000,
  });
  const ready = new Promise((resolve) => client.once("session.ready", resolve));
  await client.start();
  await ready;
  return client;
}

async function close(client, gateway) {
  await client.close();
  await gateway.stop();
}

test("originate wire omits caller_number for legacy calls", async () => {
  const gateway = new LoopbackGateway({ captureMessages: true });
  await gateway.start();
  const client = await connectedClient(gateway);
  try {
    const requestId = client.originate("from-internal", "123", {
      timeout: 4,
      requestId: "legacy-request",
    });
    const message = await gateway.messageReceived;
    assert.equal(requestId, "legacy-request");
    assert.deepEqual(message, {
      type: "outbound.originate",
      request_id: "legacy-request",
      payload: { context: "from-internal", extension: "123", timeout: 4 },
    });
  } finally {
    await close(client, gateway);
  }
});

test("originate wire includes an exact explicit caller number", async () => {
  const gateway = new LoopbackGateway({ captureMessages: true });
  await gateway.start();
  const client = await connectedClient(gateway);
  try {
    client.originate("from-internal", "123", {
      timeout: 4,
      requestId: "explicit-request",
      callerNumber: "+84900000071",
    });
    const message = await gateway.messageReceived;
    assert.deepEqual(message, {
      type: "outbound.originate",
      request_id: "explicit-request",
      payload: {
        context: "from-internal",
        extension: "123",
        timeout: 4,
        caller_number: "+84900000071",
      },
    });
  } finally {
    await close(client, gateway);
  }
});

test("originate rejects invalid callerNumber before sending a wire message", async () => {
  const gateway = new LoopbackGateway({ captureMessages: true });
  await gateway.start();
  const client = await connectedClient(gateway);
  try {
    assert.throws(
      () => client.originate("from-internal", "123", { callerNumber: "+84-90000072" }),
      TypeError,
    );
    assert.deepEqual(gateway.messages, []);
  } finally {
    await close(client, gateway);
  }
});
