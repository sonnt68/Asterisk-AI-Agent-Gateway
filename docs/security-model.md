# Security Model

## Trust Boundaries

1. **Asterisk to gateway:** a private network or VPN boundary. ARI credentials
   are gateway-only secrets.
2. **Gateway to partner:** authenticated REST and short-lived, scoped realtime
   sessions. Partners never receive ARI, SIP, AudioSocket, RTP, Docker, or
   host credentials.
3. **Browser to control API:** an authenticated tenant-scoped management
   boundary. Dashboard APIs must enforce organization membership and role
   checks when they are introduced.

## Credential Rules

- API keys are shown in plaintext only when issued.
- Persisted API-key records store a hash, prefix, scope set, expiry, revocation
  state, and audit metadata, never the plaintext key.
- Do not log credentials, raw authorization headers, or unredacted Asterisk
  configuration.
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

Public production still requires TLS termination, private ARI connectivity,
MFA/SSO policy, approved traffic SLOs and a caller-PII retention decision.
