# Observability and failure drills

Scrape `/api/v1/system/metrics` from the private monitoring network. Import
`observability/dashboards/gateway-overview.json` and load
`observability/alerts/gateway-rules.yaml` into Prometheus-compatible tooling.
Identifiers stay in structured application logs; metrics intentionally use
only low-cardinality labels and never contain API keys or caller audio.

Run dependency recovery only in a maintenance window:

```bash
bash tests/chaos/run-dependency-recovery.sh /opt/asterisk-ai-agent-gateway
```

Expected behavior:

- API restart reconnects one ARI listener and readiness returns to `1`.
- Redis interruption prevents reliable new leases/token rate checks; existing
  media is not reassigned to another worker.
- PostgreSQL interruption leaves system health and active realtime media up,
  while database-backed management operations fail until recovery.
- After every drill, verify zero orphan channels, active calls return to zero,
  and run the live PBX probe again.

The live probe accepts `--calls N` for a measured concurrency baseline. Its
temporary key is always revoked and temporary destination policy is restored.

## Partner call signals probe

`tests/e2e/asterisk/live-call-signals-probe.py` exercises the existing partner
proxy and REST token exchange, using a separate ephemeral app/key. It checks
busy, rejected, unavailable, failed, timeout, cancellation, remote hangup and
partner hangup, then queries every completed result through `call.status`.
It verifies audio on the remote-hangup case and zero active gateway calls.
The key is revoked and app disabled in `finally`; credentials are never printed.

Run only against an isolated test dialplan, with no customer destination. On
this pilot the PBX container is `freepbx-docker-freepbx-1`. Provision a unique
context using `asterisk -rx 'dialplan add extension ... into <context>'`:

| Extension | Priorities (application and data) |
|---|---|
| `answer` | `Answer`; `Playback,hello-world`; `Wait,1`; `Hangup,16` |
| `ring` | `Ringing`; `Wait,15`; `Hangup,19` |
| `busy` | `Hangup,17` |
| `reject` | `Hangup,21` |
| `unavailable` | `Hangup,1` |
| `failed` | `Hangup,34` |

Example CLI: `dialplan add extension busy,1,Hangup,17 into gateway-signals-test`.
Verify the context with `dialplan show gateway-signals-test`, then from the
Compose directory run:

```bash
docker compose exec -T api python - --context gateway-signals-test \
  < tests/e2e/asterisk/live-call-signals-probe.py
```

The default `--base-url http://admin-ui` exercises the same Nginx REST/WebSocket
proxy that partners reach. The deployed bootstrap login must still be valid.
Remove every temporary extension afterwards with
`dialplan remove extension <extension>@gateway-signals-test`, including when a
probe fails. Verify PBX active channels/bridges and gateway active-call/media
metrics return to their pre-probe baseline. Do not reload unrelated dialplans.
