# Pilot Asterisk 21.10.2 AudioSocket repair

The pilot's nonblocking AudioSocket reader treated an empty `read()` returning
EAGAIN as fatal. Two of four owned-number SIP loops ended as `media_failed`
immediately after answer, with matching native header-read errors.

This matching-version patch changes only header reads. An idle socket returns
`ast_null_frame` without consuming bytes, allowing the channel to keep sending.
Partial headers accumulate; a partial header that stalls for the existing
payload reader's 5 ms poll budget fails closed instead of blocking indefinitely
or discarding bytes and retrying a desynchronized stream. Payload framing,
codec, caller ID, routing and Gateway audio writes remain unchanged.

This is a local repair against the pinned 21.10.2 source. It is not a claim that
upstream commit 035ad4d alone applies to this older source. Upstream references:
[21.10.2 source](https://github.com/asterisk/asterisk/blob/21.10.2/res/res_audiosocket.c),
[partial-header read offset](https://github.com/asterisk/asterisk/commit/4ba7014),
[bounded idle polling](https://github.com/asterisk/asterisk/commit/035ad4d).
The public C function may now return the standard null frame on an idle read;
in-tree channel/application callers support it. Out-of-tree consumers must
handle `AST_FRAME_NULL` as a no-op. No C signature or wire format changes.

## Build

Build on the pilot Linux amd64 host, from this directory:

```bash
docker build --progress plain -t gateway-freepbx:21.10.2-audiosocket-20261021 .
```

The Dockerfile pins the existing base, verifies the source archive and C source
hashes, retains its configure/compiler options, disables host-native CPU flags,
and builds only `res_audiosocket.so`. It checks the exact build-option sum and
undefined symbols. The only new imported core symbol is `ast_null_frame`, which
must be exported by the unchanged core. The final image replaces one module;
it retains the original image entrypoint and FreePBX installation.

Before rollout, run the source-level regression runner and load all three
AudioSocket modules in a disposable Asterisk process with no production
volumes or network. A source test is not proof that the native module loads.

In the isolated builder, run this directory's regression script with the
actual patched source path. It verifies the pristine source hash, compares
both compiled function bodies with the source, and rejects body drift:

```bash
CC=gcc ./run-test-res-audiosocket-header-read.sh \
  --source /usr/src/gateway-audiosocket/asterisk-21.10.2/res/res_audiosocket.c
```

The patch and Asterisk-derived C regression functions are GPL-2.0-only,
following their original source license; they do not inherit the Gateway's
MIT license. The pinned upstream source retains its original copyright.

## Deploy and recover

The pilot Compose owner is `/opt/freepbx-docker/docker-compose.yaml`. Preserve
the current image, exact native module, source archive and Compose file in a
restricted backup. Keep the original `/etc` and `/var` volumes. Confirm zero
active channels/calls and no actual Partner App sessions before recreation.

Set only the `freepbx` service image to the verified derived image, and recreate
only that service from the existing project:

```bash
docker compose up -d --no-deps --force-recreate freepbx
```

Verify native version, module hash, loaded AudioSocket modules, all four managed
DID routes, Gateway ARI/AudioSocket readiness and bidirectional PCM through each
owned number. Repeat the four-number batch to exercise the intermittent race.
Remove only test-owned keys, grants, apps and channels.

Rollback: restore the backed-up Compose image reference and recreate only
`freepbx` with the same command and existing volumes. Do not downgrade the
Gateway database or remove volumes. A derived image persists the replacement
across container recreation; copying a module into a running container does
not provide that persistence.
