# Partner call signals

Date: 2026-10-20

## Status

Completed; deployed and verified on 2026-10-20.

## Outcome

Partners receive real PBX dialing, ringing, answer and termination results and
can check their own call by gateway UUID using their existing SDK connection.

## Authority and scope

- User requested operator integration on `118.107.77.136`.
- Preserve the single outbound WebSocket contract in
  [decision 0002](../../decisions/0002-partner-outbound-websocket.md), existing
  scope/ownership checks and `call.started` media-ready semantics.
- Add `call.status` events and a `calls:read` control query. No new REST, DB
  retention, public SDK release, customer calls or unrelated dashboard changes.
- Completed snapshots stay in the owning connection's bounded memory (last
  256); reconnect/restart clears them. Customers persist results if needed.

## Approach

1. Bind both Local channel IDs before originate; retain originate deadline.
2. Normalize real ARI Dial/state/destroy signals; avoid treating Local helper
   events as the remote answer and preserve hangup evidence after StasisEnd.
3. Add scoped snapshot query, protocol documentation and regression coverage.
4. Run repository gates/review, back up deployment, deploy API only, and verify
   isolated PBX answer/hangup/busy/no-answer/reject/failure/cancel scenarios.

## Risks and recovery

- Live Asterisk 21.10.2 reports timeout as cause 0 without Dial NOANSWER;
  classify no-answer only with an elapsed originate deadline or explicit cause.
- StasisEnd precedes ChannelDestroyed; defer fallback cleanup briefly to let
  the listener consume authoritative cause. Cleanup stays idempotent.
- Keep current API image and source backup; restore those on failed readiness
  or live validation. Check zero active calls before restarting API.
- Test dialplan extensions are isolated, ephemeral and removed after probes.
- Deferred event work uses independent authenticated ARI HTTP sessions so an
  ARI listener reconnect cannot invalidate its retained session.

## Progress

- [x] Inspect source and live PBX; planner recommendation received.
- [x] Implement signals and status query.
- [x] Regression tests, repository validation and independent review.
- [x] Deploy and verify live partner interface, cleanup and documentation.

## Validation

- Baseline: 14 outbound/realtime tests passed.
- Raw live ARI: busy cause 17; ringing then timeout cause 0; answer then normal
  hangup cause 16; explicit channel IDs correlated both Local legs.
- `bash scripts/validate.sh`: Ruff, 156 pytest cases, protocol/config parsing,
  admin UI and Node SDK builds passed. Three existing aiohttp deprecation
  warnings remain. Independent reviewer reported no remaining findings.
- Final deployed image:
  `sha256:059ad3fa9cac97b97c554264b9cbbd664b9c733690a00349745dc645e653e7c8`.
  All nine deployed implementation files match local SHA-256 hashes.
- Real partner-interface probe
  [live-call-signals-probe.py](../../../tests/e2e/asterisk/live-call-signals-probe.py):

| Isolated PBX scenario | Final status | Cause | Query |
|---|---|---|---|
| Busy | `busy` | 17 | Passed |
| Rejected | `rejected` | 21 | Passed |
| Unavailable | `unavailable` | 1 | Passed |
| Failed | `failed` | 34 | Passed |
| Ring timeout | `no_answer` | 0 | Passed |
| Cancel while ringing | `cancelled` | 16 | Active + completed passed |
| Answer, remote hangup | `completed` | 16 | Passed; 71 audio frames |
| Answer, partner hangup | `completed` | 16 | Passed |

- Reused the active query request UUID after termination and received a fresh
  terminal result. Unknown call lookup returned generic `command-failed`.
- Public health OK; ARI connected; gateway calls, partner connections and
  AudioSocket sessions all zero. PBX has zero active channels; its existing
  empty bridge was preserved. All six temporary extensions removed; zero
  enabled probe apps or unrevoked probe keys remain.

## Result

Partner signals and scoped status reads are available on the deployed API;
existing SDK generic controls work without publication. Documentation updated.
No real customer/PSTN call was attempted. Completed results remain limited to
the owning connection's last 256 snapshots; partners persist durable history.

Recovery assets are on the host under
`/opt/asterisk-ai-agent-gateway/backups/20261020-call-signals/`:
`source-before.tgz`, `ari-requests-before.py`, `api-image-before.txt`;
the prior image is tagged `gateway-api:before-call-signals-20261020`.
Rollback: restore the original source archive and `ari_requests.py`, remove the
two new signal modules, tag the saved image as
`asterisk-ai-agent-gateway-api:latest`, then run
`docker compose up -d --no-deps api` without rebuilding. No configuration or
database schema changed. No commit or push performed.
