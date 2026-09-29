import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { test } from "node:test";

import {
  AuthenticationError,
  GatewayClient,
} from "../src/index.js";
import { LoopbackGateway, waitUntil } from "./auth-retry-loopback.js";

const API_KEY = "agw_live_super_secret_key";

function makeClient(gateway, options = {}) {
  const client = new GatewayClient({
    gatewayUrl: gateway.url,
    apiKey: API_KEY,
    agentSlug: "support-agent",
    heartbeatIntervalMs: 60_000,
    maxBackoffMs: 1,
    ...options,
  });
  client.on("error", () => {});
  return client;
}

async function cleanup(client, gateway) {
  await client.close();
  await gateway.stop();
}

test("initial token HTTP auth retries four times, then start rejects safely", async () => {
  const gateway = new LoopbackGateway({ tokenStatuses: [401, 401, 401, 401] });
  await gateway.start();
  const client = makeClient(gateway);
  try {
    await assert.rejects(client.start(), (error) => {
      assert.equal(error.name, "AuthenticationError");
      assert.match(error.message, /HTTP 401/);
      assert.doesNotMatch(error.message, /agw_live_super_secret_key|rt-token/);
      return true;
    });
    assert.equal(gateway.tokenRequests, 4);
  } finally {
    await cleanup(client, gateway);
  }
});

test("direct token exchange is one-shot and reconnect false disables retries", async () => {
  for (const status of [401, 403]) {
    const gateway = new LoopbackGateway({ tokenStatuses: [status, status] });
    await gateway.start();
    try {
      const direct = makeClient(gateway);
      await assert.rejects(direct.realtimeToken(), AuthenticationError);
      assert.equal(gateway.tokenRequests, 1);
    } finally {
      await gateway.stop();
    }
  }

  const gateway = new LoopbackGateway({ tokenStatuses: [401, 401] });
  await gateway.start();
  try {
    const noReconnect = makeClient(gateway, { reconnect: false });
    await assert.rejects(noReconnect.start(), AuthenticationError);
    assert.equal(gateway.tokenRequests, 1);
    await noReconnect.close();
  } finally {
    await gateway.stop();
  }
});

test("handshake 401/403 and 4401 share a fresh-token budget", async () => {
  const gateway = new LoopbackGateway({
    tokenStatuses: [200, 200, 200, 200],
    wsActions: [401, 403, "4401", "ready"],
  });
  await gateway.start();
  const client = makeClient(gateway);
  const ready = [];
  client.on("session.ready", (event) => ready.push(event));
  try {
    await client.start();
    await waitUntil(() => ready.length === 1);
    assert.equal(gateway.tokenRequests, 4);
    assert.equal(gateway.wsRequests, 4);
    assert.deepEqual(gateway.tokens, gateway.wsTokens);
    assert.equal(new Set(gateway.tokens).size, 4);
  } finally {
    await cleanup(client, gateway);
  }
});

test("persistent handshake 403 rejects start after four fresh-token attempts", async () => {
  const gateway = new LoopbackGateway({
    tokenStatuses: [200, 200, 200, 200],
    wsActions: [403, 403, 403, 403],
  });
  await gateway.start();
  const client = makeClient(gateway);
  try {
    await assert.rejects(client.start(), (error) => {
      assert.equal(error.name, "AuthenticationError");
      assert.doesNotMatch(error.message, /agw_live_super_secret_key|rt-token/);
      return true;
    });
    assert.equal(gateway.tokenRequests, 4);
    assert.equal(gateway.wsRequests, 4);
    assert.deepEqual(gateway.tokens, gateway.wsTokens);
  } finally {
    await cleanup(client, gateway);
  }
});

test("session.ready resets auth budget; socket open without it does not", async () => {
  const recovered = new LoopbackGateway({
    tokenStatuses: [401, 200, 401, 401, 401, 200],
    wsActions: ["ready-close", "ready"],
  });
  await recovered.start();
  const client = makeClient(recovered);
  const ready = [];
  client.on("session.ready", (event) => ready.push(event));
  try {
    await client.start();
    await waitUntil(() => ready.length === 2);
    assert.equal(recovered.tokenRequests, 6);
  } finally {
    await cleanup(client, recovered);
  }

  const notReady = new LoopbackGateway({
    tokenStatuses: [401, 200, 401, 401, 401],
    wsActions: ["no-ready"],
  });
  await notReady.start();
  const noReadyClient = makeClient(notReady);
  const errors = [];
  noReadyClient.on("error", (error) => errors.push(error));
  try {
    await noReadyClient.start();
    await waitUntil(() => errors.length === 1);
    assert.equal(notReady.tokenRequests, 5);
    assert.equal(notReady.wsRequests, 1);
  } finally {
    await cleanup(noReadyClient, notReady);
  }
});

test("post-start 4401 exhaustion emits exactly one final error after four attempts", async () => {
  const gateway = new LoopbackGateway({
    tokenStatuses: [200, 200, 200, 200],
    wsActions: ["ready-close-4401", "4401", "4401", "4401"],
  });
  await gateway.start();
  const client = makeClient(gateway);
  const errors = [];
  client.on("error", (error) => errors.push(error));
  try {
    await client.start();
    await waitUntil(() => errors.length === 1);
    await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal(errors.length, 1);
    assert.equal(errors[0].name, "AuthenticationError");
    assert.equal(gateway.tokenRequests, 4);
    assert.equal(gateway.wsRequests, 4);
  } finally {
    await cleanup(client, gateway);
  }
});

test("standalone clients stay alive until the authentication retry budget is exhausted", async () => {
  const gateway = new LoopbackGateway({ wsActions: Array(4).fill("4401") });
  await gateway.start();
  const source = `
    import { GatewayClient } from ${JSON.stringify(new URL("../src/index.js", import.meta.url).href)};
    const client = new GatewayClient({gatewayUrl: ${JSON.stringify(gateway.url)},
      apiKey: "test-only", agentSlug: "standalone", maxBackoffMs: 5});
    client.on("error", error => console.log(error.name));
    await client.start();
  `;
  const child = spawn(process.execPath, ["--input-type=module", "-e", source], {
    stdio: ["ignore", "pipe", "pipe"], timeout: 2000,
  });
  let output = "";
  child.stdout.on("data", data => { output += data; });
  child.stderr.on("data", data => { output += data; });
  try {
    const code = await new Promise((resolve, reject) => {
      child.once("error", reject);
      child.once("close", resolve);
    });
    assert.equal(code, 0, output);
    assert.equal(output.trim(), "AuthenticationError");
    assert.equal(gateway.tokenRequests, 4);
  } finally {
    child.kill();
    await gateway.stop();
  }
});

test("close during backoff or an in-flight token prevents late socket attempts", async () => {
  const backoffGateway = new LoopbackGateway({ tokenStatuses: [200], wsActions: [500] });
  await backoffGateway.start();
  const backoffClient = makeClient(backoffGateway, { maxBackoffMs: 100 });
  try {
    const start = backoffClient.start();
    await waitUntil(() => backoffGateway.wsRequests === 1);
    await backoffClient.close();
    await start;
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(backoffGateway.tokenRequests, 1);
    assert.equal(backoffGateway.wsRequests, 1);
  } finally {
    await cleanup(backoffClient, backoffGateway);
  }

  const tokenGateway = new LoopbackGateway({ tokenStatuses: [200], blockToken: true });
  await tokenGateway.start();
  const tokenClient = makeClient(tokenGateway);
  try {
    const start = tokenClient.start();
    await tokenGateway.tokenStarted;
    await tokenClient.close();
    tokenGateway.releaseTokenRequest();
    await start;
    assert.equal(tokenGateway.wsRequests, 0);
  } finally {
    await cleanup(tokenClient, tokenGateway);
  }
});
