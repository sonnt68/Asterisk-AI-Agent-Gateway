# Plan: Asterisk AI Agent Gateway

Status: 6/6 engineering phases complete — external GA gates pending
Proposed project: `/Users/mac/workspace/sonnt/Asterisk-AI-Agent-Gateway`

## Outcome

Tạo gateway độc lập đứng giữa Asterisk và AI Agent của đối tác. Gateway sở hữu ARI/media/control plane; đối tác chỉ cần API key, SDK và một kết nối WSS outbound để nhận/gửi audio cùng lệnh điều khiển cuộc gọi.

## Assumptions

- Gateway SaaS do bên mình vận hành, MVP kết nối đúng một Asterisk qua private network/VPN.
- Bên thứ 3 không được nhận ARI credentials và không phải sửa dialplan ngoài snippet do gateway sinh.
- MVP ưu tiên AudioSocket streaming; ExternalMedia RTP là adapter fallback trước GA.
- Tái sử dụng giao diện React/Tailwind và UX auth của AVA theo MIT; thay backend single-admin JSON bằng PostgreSQL multi-tenant.
- MVP cung cấp đầy đủ call control: DTMF, hold/resume, mute/unmute, hangup, blind/attended transfer, cancel transfer, queue/ring-group/voicemail routing và outbound originate.

## Non-goals

- Không nhúng STT/LLM/TTS hoặc prompt orchestration vào gateway.
- Không cấp ARI/SIP credentials trực tiếp cho đối tác.
- Không mở Docker socket, terminal hoặc raw host configuration trên dashboard.
- Không bật recording/transcript mặc định trong MVP.
- Không sửa hoặc phát triển tính năng gateway trong repo AVA; AVA chỉ là nguồn tham khảo có attribution.

## Recommended partner flow

1. Đăng nhập dashboard, tạo Organization, Partner App và API key.
2. Cài SDK Python/Node, truyền `gateway_url`, API key và `agent_slug`.
3. SDK tự đổi API key thành token ngắn hạn và mở WSS outbound.
4. Asterisk route cuộc gọi vào `Stasis(asterisk-ai-gateway)` với `AI_GATEWAY_AGENT=<slug>`.
5. Gateway gửi `call.started` + audio PCM16 16 kHz; đối tác trả audio/control trên cùng session.

## Architecture

```text
PSTN/SIP -> Asterisk -> ARI + AudioSocket -> Gateway realtime core
                                              |       |
                                              |       +-> PostgreSQL / Redis
                                              +-> WSS -> Third-party AI SDK
Dashboard -> Control API ---------------------+
```

## Phases

| Phase | Status | Scope |
|---|---|---|
| [01](phase-01-project-foundation-and-contracts.md) | Complete | New repo, boundaries, schemas, OpenAPI/AsyncAPI |
| [02](phase-02-asterisk-control-and-media-plane.md) | Complete | ARI lifecycle, AudioSocket MVP, RTP adapter |
| [03](phase-03-third-party-realtime-gateway-api.md) | Complete | Partner WSS, session token, routing, call control |
| [04](phase-04-multi-tenant-auth-api-key-dashboard.md) | Complete | Auth, RBAC, API keys, AVA-derived dashboard |
| [05](phase-05-sdk-docs-and-ai-coding-skill.md) | Complete | SDKs, connection docs, examples, coding skill |
| [06](phase-06-hardening-observability-and-pilot.md) | Engineering complete | E2E, security, load, deployment; external pilot is a GA gate |

## Acceptance criteria

- Đối tác tích hợp cuộc gọi đầu tiên trong tối đa 15 phút, không cần biết ARI/AudioSocket/RTP.
- API key chỉ hiện plaintext một lần; DB chỉ giữ hash, prefix, scopes, expiry và audit trail.
- Một cuộc gọi có session/media/control độc lập; không rò dữ liệu chéo tenant hoặc chéo call.
- Revoke key ngăn kết nối mới ngay; session đang chạy có policy rõ ràng và kiểm thử.
- Dashboard quản lý một Asterisk, partner apps, routes, keys, active connections, calls, outbound calls, call-control policies và audit logs.
- Tài liệu REST + realtime protocol, Python/Node quickstart và skill AI Coding đều được validate.

## Dependencies

- Một Asterisk 18+ có ARI, Stasis và `app_audiosocket` hoặc ExternalMedia.
- PostgreSQL; Redis cho presence, session leases, rate limits và multi-instance routing.
- TLS termination/reverse proxy; private network/VPN giữa gateway và Asterisk.

## Unresolved questions

- Chưa có blocker cho scope MVP. SLO concurrency, retention PII/recording và AI-provider examples sẽ chốt trước Phase 06.
