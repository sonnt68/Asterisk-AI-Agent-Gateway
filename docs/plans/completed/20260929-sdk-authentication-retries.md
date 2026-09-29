# Execution Plan: SDK Authentication Retries

Date: 2026-09-29

## Status

Completed locally; package publication remains out of scope.

## Outcome

The public Python and Node SDKs retry authentication failures with a fresh
realtime token: one initial attempt plus three retries, delayed 1/2/4 seconds
and capped by the existing `max_backoff` setting. Token HTTP 401/403, WebSocket
handshake HTTP 401/403, and WebSocket close `4401` share one bounded budget.
Transport failures retain the same backoff, so mixed failures may delay later
auth retries beyond 1/2/4 seconds, up to the configured cap.

## Context

- Authority: explicit user request, with the settled contract of initial + 3
  retries, shared auth budget, reset only on `session.ready`, and cancellation
  safety.
- Current owners: [`sdks/python/asterisk_ai_gateway/client.py`](../../../sdks/python/asterisk_ai_gateway/client.py)
  and [`sdks/node/src/index.js`](../../../sdks/node/src/index.js).
- Current proof surfaces: [`tests/test_partner_sdk.py`](../../../tests/test_partner_sdk.py)
  and [`sdks/node/test/frames.test.js`](../../../sdks/node/test/frames.test.js).

## Scope

In scope:

- Public `sdks/python` and `sdks/node` clients, preserving direct
  `realtime_token`/`realtimeToken` as single-request primitives.
- Fresh-token auth retries, shared attempt accounting, capped backoff,
  `reconnect=False`/`false`, and close/cancellation guards.
- Loopback HTTP/WebSocket tests; no production credentials.

Out of scope:

- Gateway/server behavior, protocol changes, registry publication, release
  operations, or legacy package copies.

## Approach

1. Python: keep token exchange unchanged; in `stream()` classify token auth,
   `aiohttp` handshake 401/403, and close `4401` through one retry path. Keep
   one pending delay, use the existing backoff cap, reset the auth budget only
   when `session.ready` is decoded, and check closing state after an in-flight
   token response before opening a socket.
2. Node: keep `realtimeToken()` unchanged; normalize `ws` handshake
   `unexpected-response` 401/403 and close `4401` into the same private retry
   path. Make initial `start()` await auth retries and reject only after the
   budget is exhausted; after a socket has opened, report final failure through
   the `error` event. Track and clear one retry timer, guard late token
   responses, and reset only on `session.ready`.
3. Add real loopback HTTP/WebSocket tests for all three auth surfaces, fresh
   tokens, exact four-attempt bound, 1/2/4 plus `max_backoff`, reset-on-ready,
   `reconnect` disabled, cancellation during delay, and cancellation while a
   token request is in flight. Keep existing framing tests intact.

## Risks And Recovery

- `aiohttp` and `ws` expose handshake failures differently; verify their real
  status signals with loopback servers before finalizing classification.
- A close/error pair can otherwise schedule two reconnects; centralize timer
  ownership and assert one retry sequence in tests.
- If validation exposes an incompatible public event/error contract, stop and
  resolve that contract before editing; revert only the SDK changes, leaving
  unrelated staged work untouched.

## Progress

- [x] Inspect README, workflow, SDK clients, errors, tests, and package docs.
- [x] Record the bounded retry contract and implementation boundaries.
- [x] Implement Python and Node retry state machines.
- [x] Add loopback auth/reconnect tests and run focused validation.
- [x] Update canonical SDK docs and complete code review.

## Documentation Owning Surfaces

- Canonical package docs: [`sdks/python/README.md`](../../../sdks/python/README.md)
  and [`sdks/node/README.md`](../../../sdks/node/README.md); replace the current
  “authentication is never retried” statements with the bounded behavior.
- Synchronize auth passages in the partner authentication guide, bilingual
  integration/onboarding guides and distributable `sdks/skill` instructions.
  Preserve existing staged edits. Installed `.agents`/`.claude` skill copies
  and publication remain outside this change.

## Validation

- Focused proof: Python `pytest` auth tests and Node `npm --prefix sdks/node
  test` auth tests against loopback servers.
- Required assertions: no more than four auth attempts per session, fresh
  token per attempt, no retry with reconnect disabled, one final error path,
  reset only after `session.ready`, and no socket opened after close/cancel.
- Review: inspect the final diff for public API compatibility, duplicate timer
  prevention, and unchanged non-auth transport reconnect behavior.

Observed proof on 2026-09-29:

- Python focused SDK tests: 19 passed, including real 1/2/4-second delays and
  close during a held WebSocket handshake. Combined SDK/document/package
  selection: 36 passed.
- Node public SDK tests: 17 passed, including a standalone child process that
  remains alive for all four authentication attempts and emits one final error.
- Before unrelated concurrent CMS/API edits, `bash scripts/validate.sh` passed:
  115 tests, app/test lint, protocol YAML/JSON, shell syntax, admin UI build and
  legacy Node package build. At that point `ruff check .` also passed.
- Final SDK-scoped Ruff, Node syntax check and `git diff --check`: passed.
- Latest whole-repository lint is blocked by an unrelated import-order error
  in `tests/control-api/test_tenant_and_key_boundaries.py`, introduced by
  concurrent edits. Left untouched; this is not an SDK regression.
- Direct Node loopback checks: explicit restart grants a fresh four-attempt
  budget; `close()` clears the session identifier.
- Negative proof: before keeping post-open auth retry timers referenced, a
  standalone Node process exited after only one `4401` attempt. The new
  child-process regression now observes four token requests and the final
  `AuthenticationError`. Non-auth transport timer behavior remains unchanged.
- Independent review found a Python close/handshake race and two stale
  quickstarts. Added a post-handshake closing guard and a held-handshake
  regression; updated the quickstarts and clarified shared backoff throughout
  the auth guides. Follow-up review confirmed the code findings resolved.

## Result

Implementation, focused verification, documentation and review complete locally.
Remaining limitation: concurrent, out-of-scope test lint prevents a clean
whole-workspace validation at final handoff.
No production changes, credentials, package publication, commit or push.
