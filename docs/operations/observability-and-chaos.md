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
