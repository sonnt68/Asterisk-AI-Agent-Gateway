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

## Current Limit

Authentication, key issuance, and authorization endpoints do not exist in
Phase 01. This document defines their required security boundary; it does not
claim that it is enforced yet.
