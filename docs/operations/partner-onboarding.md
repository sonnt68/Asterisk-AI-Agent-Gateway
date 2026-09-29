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
| API key (`agw_live_…`) | dashboard, at creation time | **secret channel only** |
| Granted scopes | the partner app | any |
| Destination allowlist | the partner app | any |
| Integration guide | `docs/partner/integration-guide.html` | any |
| AI-coding skill | `python3 scripts/build_partner_skill.py` → `dist/…zip` | any |

Only the key is sensitive. The rest can go in a normal email or ticket, and
should — a partner who has the allowlist in writing raises fewer tickets.

### The key

Shown once, at creation. We store an HMAC hash and a prefix, so a lost key is
replaced, never recovered. Send it through a secret channel with an expiry
(a password manager share, not chat, not email, never a commit).

Tell the partner in the same message: it goes in the `Authorization` header of
the token endpoint and nowhere else — never a URL, never a log line.

Use the dashboard's API Keys page to choose a partner app and issue a key.
The plaintext is shown once. Revoke a key before permanently deleting its
record; deletion remains visible as an `api_key.deleted` audit event.

## Before you create anything

Agree these first; changing them later means the partner reworks code.

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

**Two workers on one slug.** A partner deploying without draining gets
`agent-in-use` and reads it as our outage. Set the expectation at handover:
drain in-flight calls before the old process exits.

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

Rotation: create the replacement, have them switch and confirm registration,
then revoke the old key. Calls in progress are not interrupted.

Offboarding: revoke the key first — that blocks new tokens and new sessions
immediately — then disable the partner app. Existing calls finish; they do not
get cut mid-sentence.
