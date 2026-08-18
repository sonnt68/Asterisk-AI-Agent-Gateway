# Phase 05: SDKs, connection docs and AI Coding skill

## Context links

- [Overview](plan.md)
- [AVA findings](research/ava-asterisk-integration-findings.md)
- `packages/protocol/openapi.yaml`, `packages/protocol/asyncapi.yaml`

## Overview

- Priority: P0
- Status: Pending
- Goal: make the first real call reproducible without understanding Asterisk internals.

## Key insights

- The SDK should hide token exchange, WSS reconnect, sequencing, pacing and codec negotiation.
- Documentation must have separate operator and partner paths.
- The AI Coding skill should be concise and load protocol/API references only when needed.

## Requirements

- Python and Node SDKs generated/typed from canonical schemas, with handwritten realtime lifecycle wrappers.
- A real echo/loopback example and a minimal adapter example for an AI provider.
- Operator docs cover Asterisk modules, ARI, network, generated dialplan, routing and verification.
- Partner docs cover API key, SDK, event lifecycle, audio contract, control commands, error handling and production checklist.
- Repository-owned skill named `connect-asterisk-ai-gateway` under `.agents/skills/`.
- Skill contains no credentials and never edits user-global skill directories.

## Documentation set

- `docs/getting-started.md` — 15-minute end-to-end path
- `docs/operator/asterisk-connection.md` — ARI, AudioSocket/RTP, dialplan, firewall, health
- `docs/partner/authentication.md` — key lifecycle and realtime token exchange
- `docs/partner/realtime-protocol.md` — events, audio, sequencing, errors
- `docs/partner/call-control.md` — clear, hangup, transfer and allowlists
- `docs/partner/python-sdk.md`, `node-sdk.md`
- `docs/troubleshooting.md`

## Skill architecture

```text
.agents/skills/connect-asterisk-ai-gateway/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── realtime-protocol.md
│   ├── rest-api.md
│   └── integration-checklist.md
└── scripts/
    ├── validate-gateway-connection.py
    └── scaffold-partner-adapter.py
```

## Related code files

Create in new repository:

- `sdks/python/`, `sdks/node/`
- `examples/python-echo-agent/`, `examples/node-echo-agent/`
- documentation and skill files listed above
- `tests/sdk/`, `tests/docs/`, `tests/skill/`

## Implementation steps

1. Generate REST/realtime types and publish local SDK packages.
2. Implement `GatewayClient`, connection registration and `CallSession` abstraction.
3. Add callbacks/async iterators for call start, audio, DTMF, commands and end.
4. Build examples that connect to the real gateway and handle real audio frames.
5. Write operator and partner docs from clean-environment walkthroughs.
6. Initialize the skill with the official skill-creator script, then add only needed references/scripts.
7. Validate the skill with `quick_validate.py` and run its scripts against a local gateway.
8. Forward-test the skill with clean-context Python and Node integration tasks.

## Todo list

- [ ] Python SDK
- [ ] Node SDK
- [ ] Real examples
- [ ] Operator documentation
- [ ] Partner documentation
- [ ] AI Coding skill and metadata
- [ ] Skill validation and forward tests

## Success criteria

- A new partner reaches a successful bidirectional call by following only `getting-started.md`.
- SDK users never manually parse AudioSocket/RTP or manage realtime token refresh.
- Docs examples compile/run in CI against the current protocol version.
- Skill reliably scaffolds an adapter, validates connectivity and explains actionable failures.

## Risk assessment

- Generated SDKs become hard to use: keep generated models separate from ergonomic wrappers.
- Docs drift: execute snippets and validate schema references in CI.
- Skill context bloat: keep `SKILL.md` under 500 lines and move details to one-level references.
- Secret leakage: scripts accept environment/file input and redact values from output.

## Security considerations

- Examples use placeholder keys and `.env.example`, never committed credentials.
- Connection validator performs read-only/authentication checks unless explicitly asked otherwise.
- Skill instructs AI agents not to print, log or persist API keys.

## Next steps

Run production hardening and a controlled partner pilot in Phase 06.

## Unresolved questions

- Which AI providers need first-party adapter examples at launch.
- Whether SDK packages will be public or distributed from a private registry.

