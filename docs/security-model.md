# Security Model

## Trust Boundaries

1. **Asterisk to gateway:** a private network or VPN boundary. ARI credentials
   are gateway-only secrets.
2. **Control API to FreePBX:** a private, bearer-token and source-restricted
   PHP bridge over the tested FreePBX BMO methods. The bridge has a fixed
   operation set and must not expose a Docker socket, arbitrary shell, raw SQL,
   or a generic GraphQL/command proxy.
3. **Browser to control API:** an authenticated operator boundary. SIP trunk
   management and phone-number routing are available only to an Owner or Admin
   whose organization is exactly `FREEPBX_OPERATOR_ORGANIZATION_ID`; ordinary
   tenant membership is not sufficient for the shared PBX inventory.
4. **Gateway to partner:** authenticated REST and short-lived, scoped realtime
   sessions. Partners never receive ARI, SIP, AudioSocket, RTP, Docker, or
   host credentials.

## Credential Rules

- API keys are shown in plaintext only when issued.
- Persisted API-key records store a hash, prefix, scope set, expiry, revocation
  state, and audit metadata, never the plaintext key.
- Do not log credentials, raw authorization headers, or unredacted Asterisk
  configuration.
- FreePBX SIP passwords stay in FreePBX. Trunk responses expose only the
  supported common fields and a `password_set` indicator; password values are
  never returned or logged. An edit with no new password preserves the existing
  secret.
- `FREEPBX_BRIDGE_TOKEN` is a deployment secret. Keep the bridge URL private.
  For production SIP password entry, prefer HTTPS or a trusted network path.
  The current pilot admin URL may be plain HTTP and the UI warns about that
  readiness limitation; this is not a new API block. If a browser is reached
  through an SSH tunnel, `GATEWAY_WEB_ORIGIN` must match the browser's origin
  because cookie-authenticated writes reject every other origin. An SSH
  credential probe of the private bridge path does not prove browser TLS or
  origin configuration, and this document does not invent a host name.
- `.env` is local-only. Use `.env.example` for non-secret configuration names.

## Enforced controls

- Argon2id browser passwords; signed, time-bounded, HttpOnly, SameSite session
  cookies; configured-Origin checks on cookie-authenticated writes.
- Tenant-scoped RBAC on management resources and scope/destination checks on
  call control.
- HMAC-hashed API secrets, one-time plaintext reveal, expiry and revocation.
- Five-minute realtime tokens checked against live key revocation at WSS
  handshake.
- Redis token exchange limits per key, organization and source IP. The default
  is 60 requests/minute and is configurable for an approved traffic profile.
- Bounded partner audio queues use drop-oldest behavior with drop metrics.
- FreePBX bridge requests use an explicit private source allowlist and bearer
  token; the bridge ignores forwarded source headers and denies its configured
  Docker gateway source. Managed writes use a lock and atomic state/dialplan
  updates.
- PBX Apply is guarded by zero active channels, uses the fixed native FreePBX
  reload, and marks managed routes applied only after exact DID, dialplan, and
  Asterisk readback. Drift or failed readback leaves the change pending.

## Managed DID boundary

- The Gateway validates an exact string of an optional `+` followed by 1 to 32
  digits. It does not normalize or reinterpret the value, and the local
  `phone_numbers` table enforces global exact-number uniqueness.
- A mapping stores one inbound Partner App, optional outbound Partner App
  assignments, the Gateway organization, label, enabled state, and local
  `pbx_applied` state. One exact number can have only one inbound owner, while
  multiple same-organization apps can receive outbound caller-number grants.
  FreePBX remains authoritative for the SIP trunk and managed inbound DID
  route; the Gateway does not mirror the PBX trunk inventory or expose a
  per-DID trunk choice.
- Managed inbound resolution requires an enabled, applied mapping, an enabled
  app owned by the same organization, and its matching live connection. A
  nonempty legacy `AI_GATEWAY_AGENT` takes precedence over `AI_GATEWAY_DID`.
  Missing or invalid managed state fails closed, and disabling a mapping stops
  new managed calls while existing calls continue.
- Reassigning a stored DID changes the local mapping used by new calls and does
  not require a PBX reload. Adding or changing PBX-managed configuration stays
  pending until an explicit Apply operation.
- Outbound resolution filters assignments by the connection's organization and
  requires both the phone number and assigned Partner App to be enabled. No
  assignments preserve the native default; one eligible number is selected
  automatically; more than one requires an exact `caller_number` value; and
  assigned rows with no eligible number are rejected. The requested value must
  be one of that Partner App's enabled assignments. The existing
  `calls:originate` scope and destination allowlist remain enforced.
- Outbound assignment changes are local policy changes for new calls and do not
  trigger a PBX reload. The source path forwards a selected number as ARI
  caller-ID inputs. The [2026-10-21 operator validation](operations/sip-trunks-and-phone-numbers.md#live-validation--2026-10-21)
  observed native FreePBX override consumption and bounded carrier
  signaling/caller-ID behavior; external-handset delivery and reliable media
  for every PSTN call remain unverified.

## Call-history destination metadata

- `called_number` and `routing_context` are nullable destination metadata for
  the internal CMS detail view. Outbound records take the already validated
  destination extension and route context; inbound records take only the
  supplied dialplan extension and context, with missing or malformed values
  left null.
- The browser-only `/api/v1/call-history/{call_id}` detail response exposes
  these fields behind the existing authenticated, organization-scoped browser
  access checks. Partner GET/list/signals responses, realtime messages, and
  both SDKs remain unchanged.
- Imported rows and older gateway rows remain null unless a restricted,
  post-backup review proves the same call UUID in `appArgs` and an exact
  `Local/<extension>@<context>` endpoint log match. Do not infer values from
  time, number, status, or ownership.
- This boundary stores dialed destination metadata only. Caller numbers,
  audio, transcripts, and customer ownership inference remain excluded.

Public production still requires TLS termination, private ARI connectivity,
MFA/SSO policy, approved traffic SLOs and a caller-PII retention decision.
The SIP management surface additionally requires provider-specific review:
outbound route/carrier activation, DID purchase or porting, and PSTN call
behavior are deployment responsibilities and are not proven by a successful
bridge request or local Apply.

## Commands that reach past call control

`playback.start`, `channel.set_var`, and `dialplan.continue` each pass a
partner-chosen string to Asterisk, so each is validated in
`apps/control-api/app/media_policy.py` before ARI is called:

- Media URIs are restricted to `sound:` and `recording:` with a strict name
  charset and no `..`. `file:` and `http:` are refused because ARI would
  otherwise read host files or fetch attacker-controlled audio.
- Channel variable names must match `AI_[A-Z0-9_]{1,60}`. The prefix confines a
  partner to its own namespace; rejecting `(` blocks dialplan functions
  (`CHANNEL`, `CDR`, `SHELL`, `FILE`), which execute rather than assign.
- Playback ids are minted by the gateway and tracked per call, so a partner can
  only stop a playback its own call started.
- `dialplan.continue` reuses the destination allowlist that governs transfers.

Deliberately **not** exposed to partners: bridge composition, arbitrary
`execute_application` (Asterisk application execution is code execution), and
call recording, which needs a retention and consent design before it can be a
partner capability.
