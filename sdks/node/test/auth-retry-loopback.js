import http from "node:http";
import { once } from "node:events";
import { WebSocketServer } from "ws";

export class LoopbackGateway {
  constructor({ tokenStatuses = [], wsActions = [], blockToken = false } = {}) {
    this.tokenStatuses = [...tokenStatuses];
    this.wsActions = [...wsActions];
    this.blockToken = blockToken;
    this.tokenRequests = 0;
    this.wsRequests = 0;
    this.registered = 0;
    this.tokens = [];
    this.wsTokens = [];
    this.authHeaders = [];
    this.clients = new Set();
    this.hold = new Promise((resolve) => { this.releaseHold = resolve; });
    this.tokenStarted = new Promise((resolve) => { this.releaseTokenStarted = resolve; });
    this.releaseToken = new Promise((resolve) => { this.releaseTokenRequest = resolve; });
  }

  async start() {
    this.server = http.createServer((request, response) => this.#token(request, response));
    this.wss = new WebSocketServer({ noServer: true });
    this.server.on("upgrade", (request, socket, head) => this.#upgrade(request, socket, head));
    await once(this.server.listen(0, "127.0.0.1"), "listening");
    this.url = `http://127.0.0.1:${this.server.address().port}`;
  }

  async stop() {
    this.releaseTokenRequest?.();
    this.releaseHold?.();
    for (const socket of this.clients) socket.terminate();
    await new Promise((resolve) => this.server.close(resolve));
    this.wss.close();
  }

  async #token(request, response) {
    if (request.method !== "POST" || request.url !== "/api/v1/realtime/tokens") {
      response.writeHead(404).end();
      return;
    }
    this.tokenRequests += 1;
    this.authHeaders.push(request.headers.authorization ?? "");
    this.releaseTokenStarted?.();
    if (this.blockToken) await this.releaseToken;
    const status = this.tokenStatuses.shift() ?? 200;
    if (status !== 200) {
      response.writeHead(status).end();
      return;
    }
    const token = `rt-token-${this.tokenRequests}`;
    this.tokens.push(token);
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ token }));
  }

  #upgrade(request, socket, head) {
    this.wsRequests += 1;
    const url = new URL(request.url, `http://${request.headers.host}`);
    this.wsTokens.push(url.searchParams.get("token") ?? "");
    const action = this.wsActions.shift() ?? "ready";
    if (typeof action === "number") {
      socket.write(`HTTP/1.1 ${action} Unauthorized\r\nConnection: close\r\n\r\n`);
      socket.destroy();
      return;
    }
    this.wss.handleUpgrade(request, socket, head, (client) => this.#socket(client, action));
  }

  #socket(socket, action) {
    this.clients.add(socket);
    socket.once("close", () => this.clients.delete(socket));
    if (action === "4401") {
      socket.close(4401);
      return;
    }
    socket.once("message", (data) => {
      const registration = JSON.parse(data.toString());
      if (registration.type !== "session.register") return;
      this.registered += 1;
      if (action === "ready" || action === "ready-close" || action === "ready-close-4401") {
        socket.send(JSON.stringify({ type: "session.ready", connection_id: `conn-${this.registered}` }));
      }
      if (action === "ready-close") socket.close(1000);
      if (action === "ready-close-4401") socket.close(4401);
      if (action === "no-ready") socket.close(1000);
    });
    if (action === "ready") this.hold.then(() => socket.close(1000));
  }
}

export async function waitUntil(predicate, timeoutMs = 1000) {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error("loopback server did not reach expected state");
    await new Promise((resolve) => setTimeout(resolve, 1));
  }
}
