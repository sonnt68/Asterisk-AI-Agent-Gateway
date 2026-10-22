# Execution Plan: Partner App Logical Deletion and Inline Copy Config

- Date: 2026-10-21
- Status: Complete — final build, live API, and dashboard validation passed
- Owner: control-plane/Admin UI implementation owners; root verified deployment

## Outcome

Make Partner App deletion a safe logical tombstone while preserving calls, history, phone mappings, and the globally unique agent slug. Add hidden per-app Copy configuration, explicit secret reveal, revoked-key purge, and app-name editing without changing partner SDK contracts.

## Final behavior

- Add nullable `PartnerApp.deleted_at` and nullable `ApiKey.encrypted_secret` in the next migration after `0006_outbound_phone_apps`. Key list responses expose metadata only, including `copy_available`; they never expose ciphertext or plaintext.
- Delete locks the `PartnerApp` row first, then checks every related key with `revoked_at IS NULL`, including expired keys. If any exists, return `409` with no mutation and no audit event. The user must revoke every key manually first.
- After all keys are revoked, delete sets `deleted_at` and `enabled=False`, retains all key/history/phone/outbound rows, and returns `204`. A repeated delete is idempotent `204`; it does not create a second mutation or audit event. There is no automatic key revocation or hard purge.
- Create-key and rotate-key lock the same app row first, so they serialize with deletion. Rotate rereads the key with `populate_existing=True` after acquiring the app lock before checking revocation. Deleted apps reject update, key-list, issue, rotate, reveal, and auth operations; deleted slugs remain reserved.
- Existing disabled-app gates, legacy non-empty `AI_GATEWAY_AGENT` precedence, active-call completion, and live connection behavior remain unchanged. Do not detach `PhoneNumber`, `PhoneNumberOutboundApp`, `CallRecord`, or `CallSignal` rows.

## Secret and Copy config contract

- `GATEWAY_API_KEY_ENCRYPTION_KEY` is optional. When configured, new and rotated keys retain the normal authentication hash plus a Fernet-encrypted secret. The live deployment uses a dedicated value stored with deployment secrets and database backups.
- Explicit create/rotate responses retain the existing plaintext `key` field for API compatibility. The UI hides it and may retain a volatile React fallback; browser persistence and list responses remain metadata-only. When the setting is unset, issuance stays hash-only and `copy_available=false`.
- `POST /api-keys/{key_id}/reveal` is Owner/Admin/Developer-only and tenant-scoped. It reveals only an active, non-expired, non-revoked key on a non-deleted app with encrypted secret, returns `Cache-Control: no-store`, and writes an audit event without the secret. Revoked, expired, deleted, or hash-only keys are forbidden.
- A hash-only reveal returns exactly `409 API key secret is unavailable`. The UI may fall back to the matching app’s just-issued response secret only for that exact 409 and matching key/app. Revoke, rotate, purge, app deletion, logout, organization change, or provider unmount clears the relevant fallback; polling prunes missing, revoked, expired, or mismatched keys. A page reload loses all volatile fallback data. Generic 409, 404, and 503 never use it.
- Inline Copy config stays hidden by default in `PartnerAppCard`. Backend-first reveal (then the narrowly scoped fallback) copies exactly three newline-delimited lines:

  ```text
  GATEWAY_URL=<current configured URL with only a trailing /api/v1 removed>
  GATEWAY_API_KEY=<fresh plaintext secret>
  AGENT_SLUG=<partner app slug>
  ```

  Preserve any deployment prefix before `/api/v1`; do not derive a different origin or strip internal path segments.
- Revoked keys have a confirmed purge action in each app card using the existing tenant-scoped purge endpoint. Active keys expose revoke; deletion never purges rows automatically.

## Admin UI behavior

- Replace the former global key banner with hidden per-app Copy config. Keep `copy_available` and the matching app/key association through polling. Plaintext must not enter local storage, URLs, logs, or `postMessage`.
- Add an app-name pencil editor with Save and Cancel. Trim the value and require 1–120 characters; send a name-only `PATCH`, preserving slug, keys, scopes, destinations, and policy. Polling must not overwrite an active name draft; reconcile remote data after Save/Cancel.
- Make delete confirmation explain the manual revoke prerequisite and retained history/mappings. A `409` leaves the app unchanged and directs the user to revoke all keys, including expired ones.

## Implementation surfaces

- Backend: `apps/control-api/app/models.py`, `control_routes.py`, `management_routes.py`, `key_management_routes.py`, `partner_auth.py`, encryption/settings helpers, and the next Alembic migration.
- Admin UI: `apps/admin-ui/src/hooks/useGatewayData.tsx`, `pages/PartnerAppsPage.tsx`, `components/PartnerAppCard.tsx`, `components/RevealedKeyBanner.tsx` (retire/replace), `pages/ApiKeysPage.tsx`, and API types.
- Contract/docs: `packages/protocol/openapi.yaml` for `copy_available`, reveal, no-store, and compatibility key responses; `docs/operations/partner-onboarding.md` for deletion, revoke-before-delete, encryption, reveal, Copy config, purge, and name editing.

## Validation and evidence

- Final `bash scripts/validate.sh`: **254 tests passed**, Ruff and Admin UI/SDK builds passed. Public Node SDK tests: **24 passed**. See [tester report](../../../plans/reports/tester-20261021-app-name-patch.md).
- Isolated restored PostgreSQL migration proof upgraded, downgraded, and upgraded again while preserving 46 apps, 78 keys, 4 phone numbers, 4 outbound grants, 1,036 calls, and 663 signals. Backup was taken at `/opt/.../backups/partner-apps-20261021T1140`.
- Add/retain behavior tests for delete `409` with any unrevoked key (expired included), zero mutation/audit on rejection, revoke-then-delete `204`, idempotence, app-first lock races, `populate_existing` rotation reread, tenant/RBAC guards, auth rejection, slug reservation, retained rows, and active-call completion.
- Add key tests for configured Fernet persistence/reveal after refresh, optional unset hash-only behavior, metadata-only lists, compatibility plaintext create/rotate responses, exact 409 fallback, no-store and secret-free audit, and revoked-key purge.
- Add Admin UI/browser checks for hidden inline Copy config, exact three-line clipboard output with preserved URL prefix, lifecycle/poll cleanup, name Save/Cancel and draft preservation, revoke-before-delete messaging, and confirmed revoked-key purge.
- Final isolated PostgreSQL concurrency proof: simultaneous rotation returned `[201, 409]`, with one replacement and one active key; delete-before-issue returned `[204, 404]` with no issued key; issue-before-delete returned `[201, 409]` with app retained. Disposable database removed after the check.
- Live API proof on owned fixtures passed encrypted issuance/reveal/no-store/metadata, token authentication, rotation, active-key deletion `409` without app/key/audit mutation, explicit revoke then idempotent deletion, deleted-app auth/update rejection, and revoked-key purge.
- Live dashboard proof passed name Save/Cancel, whitespace rejection, persisted rename after reload, disabled delete while an unrevoked key exists, and hidden Copy configuration after reload. Native Chrome copy/paste verified the actual URL, test key prefix, and matching slug; the single-line scratch input normalizes newlines, so exact newline formatting is source-verified by the copy helper's newline join. Temporary paste was cleared and all owned test keys revoked/purged.
- Four phone assignments remained identical. Exact digests of **1,036 CallRecords and 663 CallSignals** stayed unchanged. Eighteen prior owned disabled fixtures had no unrevoked keys and were removed idempotently. No existing active key was revoked or rotated.
- Before and after deployment: zero active calls/connections, ARI connected, AudioSocket listening. Only API/Admin UI services recreated; no PBX change or carrier call made in this task. Health returned `ok`; migration is `0007_partner_app_logical_delete (head)`.

## Risks and recovery

- Losing or changing `GATEWAY_API_KEY_ENCRYPTION_KEY` prevents encrypted-key Copy config but does not invalidate hash authentication; restore the deployment secret or deliberately replace affected keys. Never log or expose the encryption key.
- App-first locking and the `populate_existing` reread are required to prevent a delete/create/rotate race from bypassing revoke-before-delete. Roll back the migration/deployment using the recorded backup if the invariant fails.
- Existing live connections are not forcibly torn down; active calls follow the current lifecycle. Immediate session cutoff remains a separate change.

## Progress

- [x] Final deletion, concurrency, encryption, reveal, UI, and purge design recorded.
- [x] Focused test/build and isolated migration/backup evidence recorded above.
- [x] Finish final Admin UI build and root-owned live proof.
- [x] Update plan result and move to `docs/plans/completed/` after live validation.

## Result

Deployed on 2026-10-21 at `http://118.107.77.136:15173`.

- API image: `sha256:3b7ade64cb1fd6bbd484331369bf1d4addf6277d921fb1595446f452951ef759`
- Admin UI image: `sha256:c53ffb9a55f545f945a006c39772bb8faf9c46b2a869355360bd6d5dd534bfb9`
- [Screenshot](../../../plans/reports/assets/gateway-partner-app-name-edit-20261021.png): hidden test key, name editor and revoke prerequisite.
- Legacy hash-only keys cannot be recovered; persistent Copy configuration requires deliberate new issuance or rotation. No automatic replacement was performed.
