export class GatewayClient {
  constructor({ gatewayUrl, apiKey, agentSlug }) {
    this.gatewayUrl = gatewayUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
    this.agentSlug = agentSlug;
  }

  async realtimeToken() {
    const response = await fetch(`${this.gatewayUrl}/api/v1/realtime/tokens`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.apiKey}` },
    });
    if (!response.ok) throw new Error(`Token exchange failed: ${response.status}`);
    return (await response.json()).token;
  }

  async connect(onEvent) {
    const token = await this.realtimeToken();
    const url = this.gatewayUrl.replace(/^http/, "ws") + `/v1/realtime?token=${encodeURIComponent(token)}`;
    const socket = new WebSocket(url);
    socket.addEventListener("open", () => socket.send(JSON.stringify({
      type: "session.register", agent_slug: this.agentSlug, protocol_version: "1",
    })));
    socket.addEventListener("message", (event) => onEvent(JSON.parse(event.data)));
    return socket;
  }
}
