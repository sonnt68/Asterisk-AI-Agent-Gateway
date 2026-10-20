import assert from "node:assert/strict";
import http from "node:http";
import { test } from "node:test";

import {
  GatewayClient,
  GatewayHttpError,
} from "../src/index.js";

const API_KEY = "agw_live_history_secret";

async function startLoopback(handler) {
  const server = http.createServer(handler);
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const { port } = server.address();
  return {
    url: `http://127.0.0.1:${port}`,
    close: () => new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve())),
  };
}

function json(response, status, body) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(JSON.stringify(body));
}

test("call history uses direct API-key GETs, encoded paths, and paginated envelopes", async () => {
  const requests = [];
  const call = {
    call_id: "call/with slash",
    partner_app_id: "app-1",
    agent_slug: "support-agent",
    direction: "outbound",
    source: "gateway",
    status: "completed",
    terminal: true,
    answered: true,
    reason: "normal_hangup",
    hangup_cause: 16,
    dial_status: "ANSWER",
    sequence: 3,
    created_at: "2026-10-20T01:00:00+00:00",
    updated_at: "2026-10-20T01:02:03+00:00",
    answered_at: "2026-10-20T01:00:05+00:00",
    ended_at: "2026-10-20T01:02:03+00:00",
    duration_seconds: 123,
    talk_seconds: 118,
    history_complete: true,
  };
  const signalPage = {
    items: [{ type: "call.status", call_id: call.call_id, status: "completed", sequence: 3 }],
    next_cursor: null,
  };
  const server = await startLoopback((request, response) => {
    requests.push({ method: request.method, url: request.url, authorization: request.headers.authorization });
    const url = new URL(request.url, "http://loopback");
    if (url.pathname === "/api/v1/partner/calls") {
      const requestedPage = url.searchParams.get("page");
      if (requestedPage !== null) {
        if (url.searchParams.has("cursor")) {
          return json(response, 422, { detail: "page cannot be combined with cursor" });
        }
        if (requestedPage === "3") {
          return json(response, 200, {
            items: [],
            next_cursor: null,
            page: 3,
            page_size: 50,
            total: 0,
            total_pages: 1,
          });
        }
        return json(response, 200, {
          items: [call],
          next_cursor: null,
          page: Number(requestedPage),
          page_size: Number(url.searchParams.get("limit")),
          total: 201,
          total_pages: 3,
        });
      }
      return json(response, 200, {
        items: [call],
        next_cursor: url.searchParams.has("cursor") ? "cursor-2" : null,
        page: null,
        page_size: null,
        total: null,
        total_pages: null,
      });
    }
    if (url.pathname.endsWith("/signals")) {
      return json(response, 200, signalPage);
    }
    return json(response, 200, call);
  });
  const client = new GatewayClient({
    gatewayUrl: server.url,
    apiKey: API_KEY,
    agentSlug: "support-agent",
  });

  try {
    const page = await client.listCalls({
      limit: 100,
      cursor: "cursor/1 & two",
      status: "answered",
      direction: "outbound",
      agentSlug: "sales-agent",
      startedAfter: "2026-10-20T01:02:03+00:00",
      startedBefore: "2026-10-21T01:02:03+00:00",
    });
    assert.equal(page.next_cursor, "cursor-2");
    assert.equal(page.items[0].call_id, call.call_id);
    assert.equal(page.page, null);
    assert.equal(page.page_size, null);
    assert.equal(page.total, null);
    assert.equal(page.total_pages, null);

    const defaultPage = await client.listCalls();
    assert.equal(defaultPage.next_cursor, null);
    assert.equal(defaultPage.page, null);

    const wireAliasPage = await client.listCalls({ agent_slug: "wire-agent", page: 3 });
    assert.deepEqual(wireAliasPage.items, []);
    assert.equal(wireAliasPage.next_cursor, null);
    assert.equal(wireAliasPage.page, 3);
    assert.equal(wireAliasPage.page_size, 50);
    assert.equal(wireAliasPage.total, 0);
    assert.equal(wireAliasPage.total_pages, 1);

    const detail = await client.getCall(call.call_id);
    assert.equal(detail.call_id, call.call_id);

    const signals = await client.listCallSignals(call.call_id, {
      limit: 2,
      cursor: "signal & cursor",
    });
    assert.equal(signals.items[0].sequence, 3);

    assert.equal(requests.length, 5);
    assert.ok(requests.every(({ method, authorization }) => method === "GET" && authorization === `Bearer ${API_KEY}`));
    assert.equal(new URL(requests[0].url, server.url).searchParams.get("limit"), "100");
    assert.equal(new URL(requests[0].url, server.url).searchParams.get("cursor"), "cursor/1 & two");
    assert.equal(new URL(requests[0].url, server.url).searchParams.get("agent_slug"), "sales-agent");
    assert.equal(new URL(requests[0].url, server.url).searchParams.get("started_after"), "2026-10-20T01:02:03+00:00");
    assert.equal(new URL(requests[1].url, server.url).searchParams.get("limit"), "50");
    assert.equal(new URL(requests[2].url, server.url).searchParams.get("agent_slug"), "wire-agent");
    assert.equal(new URL(requests[2].url, server.url).searchParams.get("page"), "3");
    assert.match(requests[3].url, /call%2Fwith%20slash/);
    assert.match(requests[4].url, /call%2Fwith%20slash\/signals/);
    assert.equal(new URL(requests[4].url, server.url).searchParams.get("cursor"), "signal & cursor");
    assert.ok(requests.every(({ url }) => !url.includes("realtime")));
  } finally {
    await server.close();
  }
});

test("history HTTP failures expose status once without leaking the API key or retrying", async () => {
  for (const status of [401, 403, 404, 422]) {
    let requestCount = 0;
    let requestUrl;
    const server = await startLoopback((request, response) => {
      requestCount += 1;
      requestUrl = request.url;
      json(response, status, { detail: `invalid request for ${API_KEY}` });
    });
    const client = new GatewayClient({
      gatewayUrl: server.url,
      apiKey: API_KEY,
      agentSlug: "support-agent",
    });
    try {
      const options = status === 422 ? { cursor: "cursor-1", page: 2 } : undefined;
      await assert.rejects(client.listCalls(options), (error) => {
        assert.ok(error instanceof GatewayHttpError);
        assert.equal(error.status, status);
        assert.equal(error.statusCode, status);
        assert.doesNotMatch(String(error), new RegExp(API_KEY));
        return true;
      });
      assert.equal(requestCount, 1);
      if (status === 422) {
        const query = new URL(requestUrl, server.url).searchParams;
        assert.equal(query.get("cursor"), "cursor-1");
        assert.equal(query.get("page"), "2");
      }
    } finally {
      await server.close();
    }
  }
});

test("history methods reject empty call ids before making a request", async () => {
  const client = new GatewayClient({
    gatewayUrl: "http://127.0.0.1:1",
    apiKey: API_KEY,
    agentSlug: "support-agent",
  });
  assert.throws(() => client.getCall("  "), TypeError);
  assert.throws(() => client.listCallSignals(""), TypeError);
});
