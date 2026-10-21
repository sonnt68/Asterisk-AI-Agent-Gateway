# Native AudioSocket header-read regression proof

## Outcome

- Replaced the fake framing harness with the pinned Asterisk 21.10.2 receive
  function twice: pristine baseline and patched implementation.
- The harness uses real nonblocking `socketpair` endpoints, `poll`, and delayed
  writer threads. The only Asterisk seams are frame/allocator/logger/poll
  stubs, including an external `ast_null_frame` definition.
- Added `run-test-res-audiosocket-header-read.sh`. It requires `--source`,
  reverses the repository patch to recover the pristine source, verifies the
  pinned pristine SHA-256, and compares both embedded function bodies with the
  source while normalizing only the harness function names.

## Evidence

Command:

```sh
integrations/freepbx/asterisk/run-test-res-audiosocket-header-read.sh \
  --source /tmp/asterisk-21.10.2/res/res_audiosocket.c
```

Result:

```text
AudioSocket source/body guard passed (pinned pristine hash and both functions match)
baseline: idle EAGAIN returned the known NULL/error result
patched: AudioSocket header and payload regression tests passed
```

The patched cases cover idle EAGAIN returning `ast_null_frame` without
consuming the next header, a one millisecond fragmented header, a stalled
partial header bounded by the five millisecond poll and failing closed,
fragmented PCM payload, clean EOF, explicit hangup, invalid kind/length, and
incomplete payload EOF. The baseline mode records the known idle-EAGAIN NULL
result before proving the next complete PCM frame still parses.

Additional checks passed:

- `sh -n integrations/freepbx/asterisk/run-test-res-audiosocket-header-read.sh`
- `cc -std=c11 -Wall -Wextra -Werror -pthread ...` on macOS and GCC
- runner with explicit pristine source:
  `--pristine-source /tmp/res_audiosocket-21.10.2.c`
- ten repeated patched harness runs
- negative guard check rejected a modified `f.samples` line with
  `patched receive function drifted from pinned source`

No Docker, deployment, PBX reload, carrier, or live call operation was run by
this tester. Root can run the same runner inside the exact Linux/GCC build
image with the source path from the build stage:

```sh
integrations/freepbx/asterisk/run-test-res-audiosocket-header-read.sh \
  --source /usr/src/gateway-audiosocket/asterisk-21.10.2/res/res_audiosocket.c
```

## Unresolved questions

- The exact image run remains root-owned; local macOS and GCC runs passed.
