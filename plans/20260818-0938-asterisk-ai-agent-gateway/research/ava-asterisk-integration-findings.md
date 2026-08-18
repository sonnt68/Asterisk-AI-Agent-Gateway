# Research: AVA integration findings

## Scope and source snapshot

- Source repository: `AVA-AI-Voice-Agent-for-Asterisk`
- Commit inspected: `0d0a33a4f3f48ab63aac20d4be5b36a9c31a6427`
- License: MIT; copied substantial portions must retain the copyright and license notice.

## Current Asterisk connection

AVA uses a clean control/media split:

- `src/ari_client.py` owns ARI HTTP commands and the ARI event WebSocket. It authenticates with Asterisk credentials, registers a Stasis app, supervises reconnects and exposes answer/hangup/bridge/external-media operations.
- `src/engine.py` handles `StasisStart`, classifies caller/Local/AudioSocket/ExternalMedia channels, answers the caller, creates a mixing bridge, reads per-call channel variables and performs cleanup.
- `src/audio/audiosocket_server.py` implements Asterisk AudioSocket TLV framing, UUID binding, PCM audio, DTMF and disconnect callbacks.
- `src/rtp_server.py` and `create_external_media_channel()` provide the ExternalMedia RTP path.
- `src/core/transport_orchestrator.py` centralizes transport/audio format resolution.

The minimum dialplan is intentionally small:

```asterisk
[from-ai-gateway]
exten => s,1,NoOp(Asterisk AI Agent Gateway)
 same => n,Set(AI_GATEWAY_AGENT=support-bot)
 same => n,Stasis(asterisk-ai-gateway)
 same => n,Hangup()
```

The gateway should preserve AVA's useful invariant: dialplan only selects a logical agent; transport details remain server-side.

## Transport decision

AVA validates AudioSocket and ExternalMedia RTP. For this gateway:

- MVP default: AudioSocket with `slin`, streaming in both directions.
- Reason: one TCP port, no shared playback filesystem, no RTP/NAT discovery for partners, and direct full-duplex audio.
- Partner-facing default: PCM16 little-endian, mono, 16 kHz, 20 ms frames. Gateway owns conversion from the Asterisk transport format.
- GA fallback: ExternalMedia RTP for PBX environments where AudioSocket is unavailable or operationally unsuitable.

AudioSocket and RTP must implement the same internal `TelephonyTransport` contract so third-party protocol code never branches on Asterisk transport.

## Dashboard and authentication reuse

Reusable frontend surfaces:

- `admin_ui/frontend/src/components/layout/AppShell.tsx`
- `admin_ui/frontend/src/components/layout/Sidebar.tsx`
- `admin_ui/frontend/src/components/layout/Header.tsx`
- `admin_ui/frontend/src/pages/LoginPage.tsx`
- `admin_ui/frontend/src/auth/AuthContext.tsx`
- Dashboard cards, topology, status components and shared UI primitives.

Do not copy the operational contract unchanged:

- Current backend uses `config/users.json`, a first-run admin password and long-lived JWT in browser local storage.
- Current Admin UI mounts the Docker socket and project root; this is root-equivalent and unnecessary for a public multi-tenant gateway.
- New gateway needs PostgreSQL users/organizations/memberships, role checks, secure browser sessions and audited API-key management.
- Reuse visual language and interaction patterns, not AVA's single-host trust model.

## Recommended simplest third-party contract

Preferred MVP is a persistent outbound connection from the partner:

1. Partner receives a long-lived scoped API key once.
2. SDK calls `POST /v1/realtime/tokens` and receives a short-lived token.
3. SDK opens `wss://gateway.example.com/v1/realtime?agent=<slug>` using that token.
4. Gateway assigns inbound calls to an authenticated, healthy connection.
5. One WebSocket call session carries text control frames and binary audio frames.

This avoids requiring partners to expose public callbacks, manage SIP, know ARI credentials or understand Asterisk codecs.

Confirmed deployment scope:

- Centralized SaaS operated by our team.
- MVP connects to one Asterisk instance only; do not add speculative multi-PBX abstractions.
- The new project is a sibling repository at `/Users/mac/workspace/sonnt/Asterisk-AI-Agent-Gateway`.
- AVA remains reference-only; gateway implementation and history stay isolated in the new repository.

## Protocol outline

Gateway to partner events:

- `connection.ready`
- `call.started`
- `call.metadata`
- binary audio frames
- `dtmf.received`
- `call.ended`
- `error`

Partner to gateway events:

- binary audio frames
- `audio.clear`
- `call.hangup`
- `call.transfer`
- `call.metadata.update`
- `dtmf.send`
- `call.hold`, `call.resume`, `call.mute`, `call.unmute`
- `call.transfer`, `call.transfer.cancel`, `call.transfer.complete`
- `call.route.queue`, `call.route.ring_group`, `call.route.voicemail`
- `outbound.call.create`, `outbound.call.cancel`
- `ping`

Every control event includes `protocol_version`, `call_id`, monotonic `sequence` and idempotency semantics where relevant. Unsupported versions fail before media starts.

## Security boundaries

- ARI credentials are gateway-only secrets and never appear in partner APIs, logs or dashboard responses.
- API keys use high-entropy secrets, a lookup prefix and server-side hash; plaintext is shown once.
- Realtime token lifetime should be 5 minutes; active media session authorization is bound to organization, partner app, agent and connection ID.
- Transfer destinations require an allowlist per organization/app.
- Logs redact credentials, phone numbers according to policy and raw audio by default.
- Disconnects fail closed: stop media, apply configured fallback and clean Asterisk bridge/channels deterministically.

## AVA lessons to preserve

- Supervise ARI reconnects; readiness must reflect the real event WebSocket state.
- Expect ARI event-order races when media channels enter Stasis; bind by UUID/correlation ID and retry attachment with a bounded deadline.
- Keep caller channel, media channel, bridge and partner session in one typed call state object.
- Make cleanup idempotent and safe after partial startup.
- Treat codec, sample rate, frame pacing and downstream mode as explicit contracts.

## Excluded from the new gateway core

- Built-in STT/LLM/TTS providers and prompt management.
- Local model downloads and model UI.
- Raw YAML editor and host terminal.
- Docker socket control from the internet-facing dashboard.
- Shared file playback as the default media return path.

## Unresolved questions

- Call-control is fully in MVP and remains gated by per-key scopes plus per-app allowlists.
- Data retention period for metadata, PII and optional recordings remains to be approved before GA.
