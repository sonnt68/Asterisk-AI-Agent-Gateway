import WebSocket from "ws";

export type GatewayMessage =
  | { type: "audio"; callId: string; audio: Buffer }
  | Record<string, unknown>;

function uuidToBytes(value: string): Buffer {
  return Buffer.from(value.replaceAll("-", ""), "hex");
}

function bytesToUuid(value: Buffer): string {
  const hex = value.toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export class GatewayClient {
  private socket?: WebSocket;
  private heartbeat?: NodeJS.Timeout;

  constructor(
    private readonly gatewayUrl: string,
    private readonly apiKey: string,
    private readonly agentSlug: string,
  ) {}

  async connect(): Promise<void> {
    const tokenResponse = await fetch(`${this.gatewayUrl.replace(/\/$/, "")}/api/v1/realtime/tokens`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.apiKey}` },
    });
    if (!tokenResponse.ok) throw new Error(`Token exchange failed: HTTP ${tokenResponse.status}`);
    const { token } = (await tokenResponse.json()) as { token: string };
    const url = new URL("/v1/realtime", this.gatewayUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.searchParams.set("token", token);
    this.socket = new WebSocket(url);
    await new Promise<void>((resolve, reject) => {
      this.socket?.once("open", resolve);
      this.socket?.once("error", reject);
    });
    this.socket.send(JSON.stringify({
      type: "session.register",
      agent_slug: this.agentSlug,
      protocol_version: "1",
    }));
    await new Promise<void>((resolve, reject) => {
      const onMessage = (data: WebSocket.RawData) => {
        const event = JSON.parse(data.toString()) as { type?: string; message?: string };
        if (event.type === "session.ready") resolve();
        else reject(new Error(event.message ?? "Gateway registration failed"));
      };
      this.socket?.once("message", onMessage);
    });
    this.heartbeat = setInterval(() => this.socket?.send(JSON.stringify({ type: "heartbeat" })), 10_000);
  }

  onMessage(handler: (message: GatewayMessage) => void): void {
    this.socket?.on("message", (data, isBinary) => {
      const bytes = Buffer.from(data as ArrayBuffer);
      if (isBinary && bytes.length > 16) {
        handler({ type: "audio", callId: bytesToUuid(bytes.subarray(0, 16)), audio: bytes.subarray(16) });
      } else if (!isBinary) handler(JSON.parse(bytes.toString()) as Record<string, unknown>);
    });
  }

  sendAudio(callId: string, pcm16: Buffer): void {
    this.socket?.send(Buffer.concat([uuidToBytes(callId), pcm16]));
  }

  control(callId: string, command: string, payload: Record<string, unknown> = {}): void {
    this.socket?.send(JSON.stringify({ type: "call.control", call_id: callId, command, payload }));
  }

  originate(context: string, extension: string, timeout = 30): void {
    this.socket?.send(JSON.stringify({
      type: "outbound.originate",
      payload: { context, extension, timeout },
    }));
  }

  cancelOutbound(callId: string): void {
    this.socket?.send(JSON.stringify({ type: "outbound.cancel", call_id: callId }));
  }

  close(): void {
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.socket?.close();
  }
}
