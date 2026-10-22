# Native AudioSocket repair and live validation — 2026-10-21

Status: repaired, deployed and validated.

## Cause and repair

The deployed Asterisk 21.10.2 made a single read from a nonblocking socket for
its three-byte AudioSocket header. EAGAIN caused channel teardown. The prior
four-number loop had two `media_failed` calls with matching native errors.

The reviewed [patch](../../integrations/freepbx/asterisk/res_audiosocket-21.10.2-header-read.patch)
returns a standard null frame when no header byte is available, accumulates
fragmented headers, and fails closed if a partial header stalls beyond the
existing payload reader's 5 ms poll budget. It changes no codec, wire format,
caller-ID selection, SIP routing, RTP exposure or Asterisk core binary.

[Build and recovery recipe](../../integrations/freepbx/asterisk/README.md).
[Regression report](tester-20261021-native-audiosocket-header-read.md).
[Review](reviewer-20261021-native-audiosocket.md).

## Build, backup and deployment

- Original base image: `sha256:34e65b7a0a02ad9da67315c12bcfd0368a89c3f6d185abf498ae8a48687f0daa`.
- Original module: `b6bd53069490ca972007762b08cc32308b64db4a3f19d7c240c360e27a971e61`.
- Restricted backup: `/opt/asterisk-ai-agent-gateway/backups/audiosocket-20261021T1100/`.
  Includes original res/chan modules, source archive, Compose and image/settings metadata.
- Source archive SHA-256: `9624e807a1138cabed14431a326c9870e53fc132738dbbd61314abc027785d94`.
- ABI build-option sum: `da6642af068ee5e6490c5b1d2cc1d238`, identical to the core.
- Undefined symbols match the original except the expected core-exported `ast_null_frame`.
  Only libc is a dynamic dependency; compiler/CPU options match the original build.
- Derived image: `gateway-freepbx:21.10.2-audiosocket-20261021`,
  `sha256:a3d9f8612a88d8bcc9f4469f06a5ea3c6cf8bc79cd7feaf53e7f5ff796874e23`.
- Deployed module: `bf41d5a079e28f9827527b29908080004ffa390532f9fad753ae477820946b0f`,
  owner `asterisk:asterisk`, mode `755`.
- All three AudioSocket modules loaded `Running` in an isolated Asterisk with no
  production volumes/network, then in the recreated production service.
- Only the FreePBX Compose image reference changed. Existing `/etc` and `/var`
  volumes retained; recreation began with zero native channels and Gateway calls/connections.
  The module is part of the derived image and survives recreation.

Rollback: restore the backed-up Compose image reference and recreate only
`freepbx`, retaining both existing volumes. Original image is tagged
`freepbx:before-audiosocket-20261021`. No live rollback was needed.

## Native and local proof

The C runner verifies the pristine hash and exact baseline/patched receive
function bodies, compiles with warnings as errors, reproduces the original
idle-EAGAIN error, and passes the repaired nonblocking socket cases. It ran on
macOS and matching Linux/GCC. Cases include idle then PCM, fragmented header
and payload, bounded partial-header stall, explicit/clean hangup, malformed
frames and truncated data. A deliberately modified body is rejected.

Probe Python syntax and Ruff, shell syntax, and `git diff --check` passed.
Post-review probe hardening closes only its own fixture session if originate
acceptance is lost, checks call cleanup after disconnection, and rejects clean
WebSocket EOF/protocol errors during event, media and disabled-route waits.
Seven real local WebSocket closure/error/healthy-absence checks passed; these
checks placed no telephone calls. Final bounded review found no remaining
concerns in that scope.
The earlier routing feature's full 234-test Python/repository gate, 61 focused
Python tests, 24 Node SDK tests and UI build remain separate prior evidence;
no product Python/TypeScript changed during this native repair.

## Live owned-number tests

Four existing DID-to-app routes passed with PCM. Two temporary outbound apps
used every caller number through internal echo, eight calls, all passed.

Five four-number SIP loop batches produced 20 calls with observed non-silent
PCM in both directions and the selected exact inbound caller ID.

| Source | Owned destination | Expected inbound app | Final result |
| --- | --- | --- | --- |
| 842444562933 | 842444562943 | ava-voice-agent | Passed |
| 842444562943 | 842444562952 | vindynamics-2 | Passed |
| 842444562952 | 842444563065 | vindynamics-3 | Passed |
| 842444563065 | 842444562933 | vindynamics-1 | Passed |

The initial repaired batch had 50 TX/RX packets on both native legs. Several
later one-second startup samples had 49 RX with 50 TX and zero *reported* loss.
A deliberately strict 50-packet assertion therefore failed one fourth-batch
row despite non-silent PCM in both directions. This was not a channel teardown.
The final probe sends two seconds and requires at least one second of native
RTP in each direction; all four passed. Final native counts were TX 100/RX 100
except one RX 99; reported TX/RX loss was zero on every leg. This is a bounded
media check, not packet-perfect or sustained quality proof. Strict RTP and RTCP
counter details are in the [native inventory](researcher-20261021-native-audiosocket-build.md).

## Operator-owned external handset

The user explicitly authorized dialing their handset from all four sources.
The personal destination is kept only in temporary raw artifacts, not this report.

- Initial four calls answered and delivered non-silent handset audio to Gateway.
  Each native leg transmitted 100 packets and received about 255 packets.
  The user did not hear the immediate two-second test tone. Those local send
  counters alone were insufficient to claim audible outbound delivery.
- A diagnostic call from 842444562933 delayed the Gateway tone and also played
  a native Asterisk English prompt. The user explicitly confirmed hearing both.
- Delayed-tone calls from 842444562943 and 842444563065 were explicitly confirmed
  clear by the user. The first 842444562952 retry returned BUSY; a subsequent
  answered retry was explicitly confirmed clear.
- All four source numbers therefore have handset listening confirmation and
  observed handset-to-Gateway PCM across these attempts. Native selected caller
  ID was verified; the number displayed on the handset was not separately confirmed.
- Early-tone audibility remains a startup-timing observation. No network or
  provider configuration was changed, and greeting-at-answer latency was not
  characterized. This does not prove every carrier/network or sustained audio quality.

The external probe reports `requires_handset_confirmation` instead of treating
successful writes as human listening proof. A silent user is recorded separately
from missing audio; confirmation above comes from the user's actual responses.

## Final cleanup and health

- 38 test keys revoked; 18 fixture apps disabled, preserving their call history.
- All temporary outbound grants removed; the four existing inbound mappings
  and the user's current four outbound assignments match the pre-repair snapshot.
- 61 terminal durable call records: zero `media_failed`; terminal reasons were
  `completed`, `normal_hangup`, and the one observed `busy`.
- Zero Gateway calls/connections, zero native channels/calls; ARI connected and
  AudioSocket listener healthy.
- Zero new AudioSocket header/payload/read/write errors from the native log
  boundary at `2026-10-21T11:14:24Z` through final cleanup.

Raw evidence: `/tmp/gateway-telephony-proof-20261021/gateway-audiosocket-repaired-*.jsonl`
and `handset/` on the workstation; corresponding
`/tmp/gateway-audiosocket-{repaired,external}-*.jsonl` on the server. Handset raw
artifacts contain the operator's destination and must not be committed.

Unresolved limits: startup audio latency, handset caller-ID display, sustained
quality/load and other external networks were not validated. No unresolved
AudioSocket teardown occurred in the completed repair tests.
