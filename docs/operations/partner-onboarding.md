# Handing the gateway to a third party

Internal runbook. What a partner needs from us, what they must never get, and
the things that have actually gone wrong.

The whole design of the boundary is that a partner integrates with two
surfaces — one REST endpoint and one WebSocket — and nothing else. Everything
below exists to keep that true under pressure from a partner who is stuck and
would like ARI credentials to move faster.

## What you send

| Item | Where it comes from | Channel |
|---|---|---|
| Gateway base URL | the deployment | any |
| `agent_slug` | you choose it; globally unique | any |
| API key (`agw_live_…`) | dashboard issue or app-card Copy config | **secret channel only** |
| Granted scopes | the partner app | any |
| Destination allowlist | the partner app | any |
| Integration guide | `docs/partner/integration-guide.html` | any |
| AI-coding skill | `python3 scripts/build_partner_skill.py` → `dist/…zip` | any |

Only the key is sensitive. The rest can go in a normal email or ticket, and
should — a partner who has the allowlist in writing raises fewer tickets.

### The key

Create and explicit rotate responses still include plaintext `key` for API
compatibility. Treat it as a secret handoff. For a newly issued hash-only key,
the response may live only in ephemeral React state until refresh or logout
for the handoff fallback; never persist it in browser storage, logs or URLs,
and never commit it. Send it through a secret channel with an expiry (a
password manager share, not chat or email). The gateway always stores an HMAC
hash for authentication. When the deployment has the optional dedicated
`GATEWAY_API_KEY_ENCRYPTION_KEY`, newly issued and replacement keys also keep a
Fernet-encrypted secret for deliberate recovery; ciphertext is never returned
by a list response or logged.

Existing hash-only keys, and keys issued while that optional setting is unset,
cannot be recovered. Use deliberate Issue or Rotate to replace one; Copy
configuration never rotates a key automatically. The app-card action is
available only when the key is active and non-expired, its Partner App is
enabled and not deleted, and `copy_available` is true.

The app card's Copy config action calls the tenant-scoped
`POST /api/v1/api-keys/{key_id}/reveal` endpoint as an Owner, Admin or
Developer. It returns the plaintext only for an eligible key and sends
`Cache-Control: no-store` and `Pragma: no-cache`. The browser copies exactly
these three lines, using the deployment's actual base URL with `/api/v1`
removed:

```text
GATEWAY_URL=<deployment-base-url-without-/api/v1>
GATEWAY_API_KEY=<fresh-plaintext-key>
GATEWAY_AGENT_SLUG=<partner-app-agent_slug>
```

Tell the partner in the same message: the key goes in the `Authorization`
header of the token endpoint and nowhere else — never a URL or a log line.

Use the dashboard's Partner Apps card to issue or rotate a key. After refresh,
copyable active keys expose Copy config; hash-only or unavailable keys
require a deliberate new issue or Rotate action. A revoked key can be
permanently deleted from its app card only after revocation, and the
`api_key.deleted` audit event remains the durable record of that deletion.

## Before you create anything

Agree these first; changing them later means the partner reworks code.

### Defaults for a new app and key

When the REST create-app request omits `scopes`, the new app defaults to
`calls:read`, `media:stream`, and `calls:originate`. The REST default does not
add `calls:hangup`. When a REST key request omits `scopes`, the key receives the
intersection of that default set and the app's current scopes. An explicit
list, including `[]` or a restricted list, remains exact after normalization
and must still be a subset of the app scopes. Destination policy and the
existing command-scope checks remain in force.

The dashboard's new-app form retains `calls:hangup` alongside
`calls:read`, `media:stream`, and `calls:originate`; a key issued from that
dashboard inherits the app's scopes. Existing apps and keys are not upgraded,
and no key is rotated automatically.

1. **`agent_slug`** — globally unique across all partners, and one live
   connection per slug. Include the partner's name in it. Two of their
   environments (staging and production) need **two slugs**, or their staging
   worker knocks production off the air. This is the single most common
   onboarding mistake.
2. **Scopes** — grant what the use case needs today. `calls:originate` and
   `calls:transfer` are the two worth deliberating over; the rest are
   comparatively inert. A key's scopes can be narrower than the partner app's,
   never wider.
3. **Destination allowlist** — exact `context:extension` pairs, or a prefix
   rule ending in `*`. Outbound PSTN needs a prefix rule because the callee
   differs per call; `from-internal:84*` is the shape on FreePBX. Only a
   trailing asterisk is a wildcard, so feature codes like `*43` stay exact,
   and a prefix needs two literal characters minimum.

   Pick the context before you write the entry. Outbound origination dials
   `Local/<extension>@<context>`, so the context has to be one that routes a
   number *outward* — `from-internal` carries the FreePBX outbound routes.
   The inbound trunk context is the wrong answer even though it is the
   obvious-sounding one: see the incident below. Write the rules down for the
   partner — `command-denied` with no explanation is how support tickets
   start.
4. **Sample rate** — `GATEWAY_MEDIA_SAMPLE_RATE`, 8000 unless both ends are
   genuinely wideband. See the caution below before raising it.

## What they never get

ARI credentials, SIP credentials, AudioSocket endpoints, RTP ranges, Docker
access, host access, database access, Asterisk channel IDs.

The last one is easy to leak by accident in a support conversation. Partners
correlate on the gateway `call_id`; a channel ID in their data model is a
boundary violation that will not surface until something depends on it.

If a partner's problem genuinely cannot be solved through the two public
surfaces, that is a gap in the gateway to fix on our side — not a reason to
hand over a credential.

## Cautions from real incidents

**A fixed sample rate in partner code.** We used to advertise a flat 16 kHz,
and the SDKs exported it as a constant, so partners hardcoded it. When the
model's own rate does not divide evenly into the wire rate — 24 kHz into
16 kHz is 1.5× — most anti-alias filters silently fall back to linear
interpolation and alias. Nothing errors. The call just sounds boomy and
distant. Measured: 56% of speech energy in the 300–3400 Hz band versus 68% on
the 8 kHz path.

The rate is now announced per call in `call.started`. When a partner reports
bad audio with no errors, ask what rate they send before anything else.

**Two workers on one slug.** The gateway keeps the most recent registration
per slug. A partner deploying without draining sees the old worker closed
with `4409` (`session-superseded`) and its in-flight calls hung up, and reads
it as our outage. Before 2026-10 the second worker was refused with
`agent-in-use` instead, which left a stale or forgotten process holding the
slug until someone found it. Set the expectation at handover: drain in-flight
calls before the new process registers, and give staging its own slug.

**Retry storms on the token endpoint.** 60 requests per minute per key, per
org, per IP. The public SDK connection flows retry authentication failures
three times after the initial attempt (four attempts total), with one shared
budget for token HTTP `401`/`403`, WebSocket handshake `401`/`403`, and close
`4401`. Each retry mints a fresh token after 1, 2, then 4 seconds, capped by
the configured max backoff; the budget resets only when `session.ready`
arrives. `reconnect=False`/`false` disables the flow, and `close()` stops
pending retries; Python task cancellation also stops them. After the budget,
Python raises `AuthenticationError`; a Node initial `start()` rejects, while a
later reconnect emits it on `error` and stops the client. Retrying a revoked
key never helps. Direct `realtime_token()`/`realtimeToken()` helpers remain
single requests. The 1/2/4-second sequence assumes authentication-only failures:
transport failures share the same backoff and can increase delays up to the cap.

**An allowlist entry naming a context that cannot dial out.** A partner asked
for `from-trunk:84*` because `from-trunk` is where their inbound calls arrive,
and it reads like "the context my trunk uses". Outbound is the other
direction. The gateway originates `Local/<extension>@<context>`, so the
context must contain a route that sends the number to the trunk; a FreePBX
inbound context matches DIDs and has no outbound route, so `Local/84…@from-trunk`
matches no extension.

Allowlisting it anyway converts a clear `outbound-failed` at the boundary into
a call that Asterisk accepts and then drops with nothing useful in the
partner's logs. Confirm the context dials by hand before you add the entry:

```
asterisk -rx 'channel originate Local/84901234567@from-internal application Echo'
```

If that does not ring, no allowlist entry will make it ring.

**Audio frames disappearing.** The partner-bound queue holds 100 frames and
drops the oldest when a consumer stalls, on purpose, so live audio stays live.
The fix is on their side: consume faster. More buffering moves the problem.

## Verifying before you call it done

Run through this with the partner on a real call, not a staging simulation:

- [ ] They mint a token and register; `session.ready` arrives.
- [ ] A call produces `call.started`, and they log the `media` block they
      received — confirm it matches what the deployment advertises.
- [ ] Audio flows both ways and the caller confirms it sounds clean.
- [ ] Each granted command is exercised once. An ungranted one returns
      `command-denied` — confirm they handle it rather than crashing.
- [ ] Every destination they will use is accepted by the allowlist.
- [ ] `call.ended` releases their call-local state; active call and media
      gauges return to zero after hangup.
- [ ] They restart a worker mid-call and observe the call ending, so the
      behaviour is known before it happens in production.

## Rotation and offboarding

### Editing the app card

An authorized Owner, Admin or Developer can choose **Edit name** on a Partner
App card, change the display name, then **Save** or **Cancel**. Save trims
surrounding whitespace and accepts 1–120 characters after trimming. It changes
only the display name: `agent_slug`, API keys, scopes, destination policy,
call history and phone-number references remain unchanged. Cancel discards the
unsaved text. A logically deleted app cannot be edited.

Rotation: create the replacement, have them switch and confirm registration,
then revoke the old key. Use Copy config on the replacement when
`copy_available` is true; otherwise perform a deliberate replacement again
after configuring the optional encrypted-secret setting. Calls in progress are
not interrupted.

Offboarding: an Owner or Admin can Delete partner app only after every API-key
row is explicitly revoked, including expired keys. If any key is still
unrevoked, the endpoint returns `409` and leaves the app, keys and audit log
unchanged; revoke those keys first. Once the precondition holds, the logical
delete removes the app from the dashboard, marks it disabled and clears
recoverable ciphertext while retaining key rows, call history, phone-number
references and outbound assignments. The app's slug remains reserved, and the
app cannot be edited or issue, rotate or reveal keys after deletion. Existing
calls finish; the gateway does not forcibly tear down an active call.
