# Native AudioSocket repair review — 2026-10-21

## Scope

Read-only review of the matching-version Asterisk 21.10.2 repair and its native
build/test artifacts:

- `integrations/freepbx/asterisk/res_audiosocket-21.10.2-header-read.patch`
- `integrations/freepbx/asterisk/test-res-audiosocket-header-read.c`
- `integrations/freepbx/asterisk/run-test-res-audiosocket-header-read.sh`
- `integrations/freepbx/asterisk/Dockerfile`
- `integrations/freepbx/asterisk/README.md`

The comparison sources were the pinned Asterisk 21.10.2
`res/res_audiosocket.c` and upstream commit
[035ad4d](https://github.com/asterisk/asterisk/commit/035ad4d).

## Review result

The patch is a bounded 21.10.2 repair and preserves the native AudioSocket
protocol, exported function signatures, companion module ABI, payload loop,
codec behavior, caller-ID/routing behavior, and Gateway media code.

The header reader now accumulates all three bytes. An empty nonblocking
`EAGAIN` returns the existing `ast_null_frame` without consuming stream data,
so the channel thread can service outbound audio and retry on its normal wait
schedule. Once a partial header has been consumed, the reader waits one 5 ms
poll budget and fails closed if the remainder does not arrive. This preserves
framing and avoids both silent byte loss and an indefinite channel-thread
block. `EINTR`, clean EOF, explicit hangup, malformed headers, and incomplete
payloads retain error/hangup distinctions consistent with the surrounding
AudioSocket callers.

Returning `AST_FRAME_NULL` on an idle read is an intentional public behavior
change. The in-tree application and channel callers already handle it, and
the native README records the requirement for out-of-tree callers. No C
signature or wire-format change was introduced.

## Validation evidence

- The source-extracted harness compiles with `-std=c11 -Wall -Wextra -Werror`
  and passes both baseline and patched modes through
  `run-test-res-audiosocket-header-read.sh`. Coverage includes idle EAGAIN,
  fragmented headers and payloads, stalled partial headers, clean/partial EOF,
  explicit hangup, invalid kind/length, and incomplete payload.
- Root-run build used the pinned base image
  `escomputers/freepbx@sha256:34e65b7a0a02ad9da67315c12bcfd0368a89c3f6d185abf498ae8a48687f0daa`.
  The base intentionally contains `/usr/src/asterisk.tar.gz`; the Dockerfile
  verified archive SHA-256
  `9624e807a1138cabed14431a326c9870e53fc132738dbbd61314abc027785d94` and
  pristine `res/res_audiosocket.c` SHA-256
  `a9ff97eca61dad09148ccb67de5584c0c6854d8cc748f916d6585d055f6c62da`.
- Root-run ABI/build gates passed: exact build-option sum, unchanged undefined
  Asterisk symbols after excluding the expected `ast_null_frame` import, one
  `libc.so.6` dependency, and core export of `ast_null_frame`.
- Root-run isolated derived image loaded `res_audiosocket.so`,
  `chan_audiosocket.so`, and `app_audiosocket.so` as `Running` with no network
  or production volumes. The replacement module hash was
  `bf41d5a079e28f9827527b29908080004ffa390532f9fad753ae477820946b0f`, with
  `asterisk:asterisk` ownership and mode `755`.
- The Asterisk README documents the pinned build command, zero-call deployment
  gate, derived-image persistence, loaded-module/readback checks, and rollback.

## Boundaries

This was a source/build review; root owns deployment and the post-repair live
four-number SIP rerun. No Gateway workaround, live PBX mutation, or remote
operation was performed by this reviewer.

**Status:** DONE

**Summary:** Matching-version AudioSocket repair, framing tests, ABI checks,
isolated module load, and deployment recipe are correct against the reviewed
scope. No unresolved correctness or security finding remains.

**Unresolved questions:** None within the reviewed native patch/build scope.
