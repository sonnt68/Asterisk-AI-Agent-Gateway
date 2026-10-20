# Deployment

The pilot uses Docker Compose at `/opt/asterisk-ai-agent-gateway` and binds
dashboard/API to loopback until TLS termination is configured.

```bash
docker compose build api admin-ui
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:18080/api/v1/system/health
docker compose exec api alembic current
```

## Dashboard exposure

`GATEWAY_ADMIN_BIND` controls the interface the dashboard port binds to. It
defaults to `127.0.0.1`, so a fresh deployment is reachable only through a
tunnel:

```bash
ssh -i ~/.ssh/id_ed25519 -L 15173:127.0.0.1:15173 root@<gateway-host>
```

Open `http://localhost:15173`. It reverse-proxies REST and WSS to the API.

The pilot host binds publicly instead (`GATEWAY_ADMIN_BIND=0.0.0.0`,
`GATEWAY_ADMIN_PORT=15173`), serving the dashboard at
`http://<gateway-host>:15173`. Port 80/443 on that host belongs to FreePBX, so
the gateway must not claim them. `GATEWAY_WEB_ORIGIN` must match the URL the
browser uses, because the origin middleware rejects every other origin.

Public binding over plain HTTP puts the `gateway_session` cookie on the wire in
cleartext. Terminate TLS in front of the dashboard before the pilot carries real
tenant traffic, and set `GATEWAY_COOKIE_SECURE=true` once it does.
Back up PostgreSQL before migration. Roll back by restoring that backup and the
matching previous image, not by running a downgrade under active writers.

## Durable history rollout

The durable history baseline is the additive `0003_call_history` migration.
CMS destination-detail fields are a separate additive
`0004_call_destination` migration. Before any rollout, back up the database
and matching application image, then validate migration head, health, API-key
ownership isolation, pagination, restart recovery, and the internal management
view. Keep the existing realtime `call.status` behavior while the durable GET
surface is introduced.

The verified rollout sequence below covers the `0003` durable-history rollout.
Apply the same backup and isolated-migration gates before any `0004` rollout.

1. Create a PostgreSQL backup and a matching application-image record. Keep
   sanitized source exports and database backups at mode `0600`.
2. Restore the backup into an isolated database and run the migration there
   before touching the live database. Confirm real `CallRecord`/
   `CallSignal` foreign-key writes and remove the disposable database after
   the check.
3. Deploy the API/UI image with migration `0003`, verify health and migration
   head, then exercise partner ownership, cursor and numbered pagination,
   restart recovery, and the management view.

Legacy summaries must be imported only into the designated organization, with
no partner-app ownership inferred. They remain visible only to an organization
owner or admin in the internal management view; they must not appear in partner
GET responses. Mark them summary-only (`history_complete=false`) and keep the
import idempotent, with no audio, transcript, caller-number, or called-destination
data. Imported rows retain null `called_number` and `routing_context`.

Use the sanitized JSON importer from the API environment:

```bash
python -m app.call_history_import \
  --file <sanitized-json> \
  --organization-id <uuid>
```

The importer source is the schema authority:
[call_history_import.py](../../apps/control-api/app/call_history_import.py).
The document must be an object with a `records` array and may include a
`timezone`; each row is grouped by `linkedid` or `uniqueid` and uses the
exported `calldate`, `disposition`, `duration`, and `billsec` summary fields.
The importer creates deterministic summary records with
`partner_app_id=NULL`, `agent_slug=NULL`, `source="imported"`, and
`history_complete=false`; it never copies caller numbers, gateway markers, or
called-destination metadata or customer ownership. Do not hand-edit the
generated IDs or attach an app to an imported summary.

Record the command output. The verified import grouped 779 legacy records on
the first run; the exact same input on the second run inserted `0` new rows.
If a run fails, preserve the mode-`0600` input and database backup, inspect the
reported row/schema error against the importer source, and rerun only after
the input or organization identifier is corrected. Restore the matching
database and application image if migration validation fails; never run a
downgrade under active writers.

Root has verified the migration, isolated restore, import idempotency, scoped
private GET reads across eight real calls, cross-app `404`/empty results, and
byte-identical records after API-container recreation. The first media probe
showed a transient AudioSocket `EAGAIN`; an identical eight-scenario rerun
passed without media changes. Treat that as an operator-only limitation, not
as a fixed condition. Carrier/PSTN verification remains unperformed.

The final redeploy and live UI checks passed for the historic-agent selector,
numbered navigation and View modal: 794 total records, 16 pages, direct
last-page jump and an 8-call agent filter. Modal metadata/timelines, legacy
summary copy, Escape, focus trapping/restoration and tab keyboard handling
passed. Final rebuilt Python SDK agent/page/detail/signal reads also passed.
Temporary keys were revoked (401 verified), test apps disabled and six test
extensions removed; active calls/media/partner connections returned to zero
with ARI connected. The Node/Python `0.4.0` builds are served as direct artifacts
under `downloads/sdk-0.4.0/`; npm/PyPI publication was not performed. See the
[completed rollout record](../plans/completed/20261020-durable-call-history.md)
for image IDs and artifact hashes.

## CMS destination-detail rollout

The `0004_call_destination` fields are nullable and are shown only by the
authenticated browser detail route. New gateway records capture outbound
`extension`/`context` after destination validation, or inbound values from the
supplied `channel.dialplan.exten`/`channel.dialplan.context`. Missing or
unbounded inbound metadata remains null. The partner list/detail/signals
contracts, realtime frames, and SDKs do not gain these fields.

Existing imported rows stay null. A legacy gateway row may be considered for
backfill only after a restricted mode-`0600` database/log backup and only when
the same call UUID appears in `appArgs` and the logs provide an exact
`Local/<extension>@<context>` endpoint match. Leave every non-exact case null;
never infer from timestamps, destination numbers alone, status, or ownership.
The 2026-10-20 rollout passed the isolated PostgreSQL restore/migration gate and
deployed `0004` with API/UI only. Exact correlation filled 61 owned, ended
Gateway records; a second pass changed zero rows and imported destinations
remained null. Live reject/no-answer fixtures verified persistence and browser
detail reads while partner responses stayed unchanged. See the
[rollout record](../plans/completed/20261020-call-history-destination-details.md)
for evidence and the browser-inspection limitation.
