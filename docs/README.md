# Documentation Map

Start with the smallest authoritative surface.

## Gateway guides

- [`getting-started.md`](getting-started.md): first partner call.
- [`operations/asterisk-connection.md`](operations/asterisk-connection.md):
  connect and verify the single Asterisk.
- [`partner/authentication.md`](partner/authentication.md): API keys and tokens.
- [`partner/realtime-protocol.md`](partner/realtime-protocol.md): events/audio.
- [`partner/call-control.md`](partner/call-control.md): scopes and commands.
- [`partner/integration-guide.html`](partner/integration-guide.html): the
  handout for third parties. Bilingual Vietnamese/English, self-contained,
  covers the same surfaces as the three files above in one page.
- [`operations/deployment.md`](operations/deployment.md) and
  [`operations/observability-and-chaos.md`](operations/observability-and-chaos.md):
  deployment, metrics and recovery.

## Current Product

- `WORKFLOW.md`: request shape, planning, judgment, operation, validation, and
  completion.
- `ARCHITECTURE.md`: current product, code, state, update, and ownership
  boundaries.
- `HARNESS.md`: product principles and installed-core model.
- `product/`: current product behavior and installation contract.
- `decisions/`: lasting choices future work must inherit.
- `plans/`: one durable working-memory document for work that needs it.
- [`patterns/encoding-invariants.md`](patterns/encoding-invariants.md): turn
  accepted architecture, reliability, security, and quality rules into native
  mechanical validation.
- `templates/`: optional decision, plan, runbook, and Harness-improvement
  structures.

## Consumer-Owned Truth

The consumer's README, product documents, architecture, code, tests, CI,
runtime signals, and application behavior remain authoritative. Harness does
not overwrite those with upstream product assumptions.

## Source Repository

- Root `README.md`: product overview, installation, maintenance, EOL, and
  development.
- `crates/harness/`: safe core installer/updater.
- `scripts/`: platform bootstrap, release, and validation entrypoints.
- `tests/`: behavior ownership and repository contract.

## History

The former SQLite control plane, protocol v1, story packets, migration evidence,
and compatibility documentation are preserved by Git history and immutable
`harness-cli-v*` tags. They are intentionally absent from the current tree so
search and agent retrieval return current product authority.
