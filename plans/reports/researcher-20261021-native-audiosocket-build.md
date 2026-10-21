# Native AudioSocket build inventory — 2026-10-21

## Live image and persistence

The running service is `freepbx-docker-freepbx-1`, Compose project
`freepbx-docker`, service `freepbx`. Its labels identify the owner as
`/opt/freepbx-docker/docker-compose.yaml` and working directory
`/opt/freepbx-docker`. The image is `escomputers/freepbx:17-nofail2ban` at
digest `sha256:34e65b7a0a02ad9da67315c12bcfd0368a89c3f6d185abf498ae8a48687f0daa`.

The image uses Debian Bookworm slim and was built from the host repository at
commit `c22e294c135cfabfd12f4a6f5f2f036270684528`. The source Dockerfile on the
host matches its committed copy (SHA-256
`0a4c6dacb3d7d7d51e74928e018b20efafe5f36a42b1bbb08c2aaf96ab7fa2a3`).

Persistent mounts are the named volumes `freepbx-docker_var_data` at `/var`
and `freepbx-docker_etc_data` at `/etc`. The postfix secret is a read-only bind
at `/run/secrets/postfix_sasl_passwd`. The Asterisk installation and module
directory are in the image layer, not in either persistent volume.

## Asterisk and module provenance

Read-only live commands reported:

- `Asterisk 21.10.2`, built on x86_64 by GCC Debian 12.2.0-14+deb12u1.
- `/usr/sbin/asterisk` is the executable; its SHA-256 is
  `d830e30643588de4278a1e3f100c6d235ca8adc49d71f853043c9b31854974f1` and
  ELF Build ID is `f04a4ecb2f4a0dd078c7a4e6e0813658201474a4`.
- The module directory is `/usr/lib64/asterisk/modules`.
- `res_audiosocket.so` is loaded and running. Its current SHA-256 is
  `b6bd53069490ca972007762b08cc32308b64db4a3f19d7c240c360e27a971e61` and
  Build ID is `612b93223e44e8d15c307f9c8341346dd99a1790`.
- The companion `app_audiosocket.so` and `chan_audiosocket.so` are also loaded;
  their hashes are `b3dac608121dddf7a5d268b252af12df4bb5ecca1038ec57010579123a48a434`
  and `4a31c5b94d1be29a8d6c600c81f7678f128fa67627ca4d9f503b4df17d9c74d1`.
- The core and AudioSocket modules embed `AST_BUILDOPTS=OPTIONAL_API`,
  `AST_BUILDOPTS_ALL=OPTIONAL_API`, and
  `AST_BUILDOPT_SUM=da6642af068ee5e6490c5b1d2cc1d238`.
- `res_audiosocket.so` is an unstripped x86-64 shared object with GCC 12.2
  debug information. `ldd` reports only `libc.so.6` as a dynamic dependency;
  Asterisk symbols are resolved from the running core. The core links the
  bundled `libasteriskpj.so.2` and normal Bookworm system libraries.
- The compiler target is generic x86-64 (`-march=x86-64`, `-mtune=generic`),
  with `BUILD_NATIVE` disabled. Do not build with host-specific CPU flags.

The image history records the exact Asterisk build recipe:

```text
./configure --libdir=/usr/lib64 --with-pjproject-bundled --with-jansson-bundled
make menuselect.makeopts
menuselect/menuselect --disable BUILD_NATIVE --enable format_mp3 menuselect.makeopts
make -j"$(nproc)"
make install
make samples
ldconfig
```

The backup source archive is the Asterisk 21.10.2 tree, SHA-256
`9624e807a1138cabed14431a326c9870e53fc132738dbbd61314abc027785d94`.
Its pristine `res/res_audiosocket.c` SHA-256 is
`a9ff97eca61dad09148ccb67de5584c0c6854d8cc748f916d6585d055f6c62da`.
The current source reads the three-byte frame header once and returns on
`read() == -1`; payload reads already poll/retry `EAGAIN`. This is the exact
source seam implicated by the observed header `EAGAIN`.

## Safest matching build

Use a disposable build container from the immutable running image digest, with
no PBX volumes, host network, Docker socket, or privileges. Copy the verified
source archive into it, extract it under `/usr/src`, apply only the reviewed
`res_audiosocket.c` patch, and run the exact configure and menuselect commands
above. A minimal module build may target `res/res_audiosocket.so` after the
configure/menuselect steps; retain the complete build output until ABI checks
finish. Reusing the running image supplies the matching Bookworm toolchain and
development libraries without relying on a mutable host compiler.

Before accepting the module, compare all of the following with the running
core/module:

1. `strings` reports the exact `AST_BUILDOPT_SUM` above.
2. `file`, architecture, owner/mode, and `readelf -d` match; the only NEEDED
   library for `res_audiosocket.so` should remain `libc.so.6`.
3. `nm -D --undefined-only` has the same unresolved Asterisk symbol set as the
   original module. A changed source line should change the Build ID/hash; that
   is expected. A changed build-option sum or symbol set is a hard stop.
4. A disposable Asterisk process loads the module and reports it `Running`
   before any deployment. Do not use the live PBX for this check.

Do not copy a rebuilt `.so` into the running container as the deployment
method. That changes an ephemeral layer and disappears on recreation. Build a
derived image from the pinned digest, `COPY` the one verified module to
`/usr/lib64/asterisk/modules/res_audiosocket.so`, preserve `asterisk:asterisk`
ownership and executable mode, and tag it with a content-specific local tag.
Keep the original image tag/digest and module files as rollback evidence.

## Persistent recreate and rollback

After the derived image is validated, change only the Compose `freepbx.image`
reference to the derived tag and run the existing project from
`/opt/freepbx-docker`:

```text
docker compose up -d --no-deps --force-recreate freepbx
```

This recreates only the FreePBX service while preserving `/var` and `/etc`.
Never use `down -v`, the repository `--clean-all` path, or a fresh named
volume. Startup runs the image entrypoint and FreePBX Asterisk starter, so the
module is loaded from the image at process start. Verify the new container
identity, Asterisk version, module hash/Build ID, `module show like audiosocket`,
and exact `AST_BUILDOPT_SUM`. If any check fails, restore the original image
reference and recreate with the same command; the persistent volumes and the
pre-change module backup remain intact.

## Validation limits

The current Compose file publishes SIP UDP 5060 and 55000 but does not declare
the Asterisk RTP range. The host's current nftables rules include a geo-filter
accept/drop rule for UDP 16384–32767 but no observed Docker PREROUTING DNAT for
that range; the repository `run.sh` contains an intended RTP DNAT setup. This
inventory does not attribute the previously observed owned-number loop results
to that boundary: the final passing loops recorded native PJSIP TX/RX 50/50
with zero loss, while the two failures logged native AudioSocket header
`EAGAIN`. External handset RTP remains a separate deployment check.

## RTP counter boundary — 2026-10-21

The live generated `/etc/asterisk/rtp_additional.conf` enables
`strictrtp=yes`, leaves `probation` unset, and `rtp show settings` reports
`Probation: 4 frames`. The pinned 21.10.2 source confirms the relevant order:

- `res/res_rtp_asterisk.c:8329-8447` evaluates Strict RTP learning and returns
  `ast_null_frame` while a new source is being qualified; the debug path says
  those packets are dropped and will switch after the remaining probation
  packets.
- `res/res_rtp_asterisk.c:7881-7885` increments `rxcount` only after that
  strict-source path returns and seeds the sequence number from the first
  accepted packet.
- `res/res_rtp_asterisk.c:101` sets the default RTCP report interval to 5000 ms;
  the live generated RTP config does not override it.
- `channels/pjsip/cli_commands.c:397-425` prints `pjsip show channelstats`
  directly from `ast_rtp_instance_get_stats()`.
- `res/res_rtp_asterisk.c:9259-9260` supplies `rxploss` from
  `expected_prior - received_prior`, while
  `calculate_lost_packet_statistics()` updates those prior counters only when
  an RTCP report is calculated (`res/res_rtp_asterisk.c:4688-4712`).

Therefore an observed `49 rx / 50 tx / 0 loss` during a short startup sample
is consistent with one packet being rejected during Strict RTP source learning
before `rxcount`, and the loss field still being zero before the first RTCP
interval. It is source-supported counter behavior, not proof that the network
dropped a packet. It also remains non-conclusive: sampling after a longer
steady stream and after RTCP has reported is needed to distinguish probation
from actual RTP loss. No additional call or native mutation was performed.

## Handset RTP path — 2026-10-21

The sanitized live endpoint readback for the tested number shows an available
SIP contact and these media settings: `allow=ulaw|alaw|gsm|g726|g722`,
`direct_media=false`, `rtp_symmetric=true`, `rewrite_contact=true`,
`force_rport=true`, `ice_support=false`, blank endpoint `media_address`, and
`media_use_received_transport=false`. The active UDP transport binds
`0.0.0.0:5060` and has an external media/signaling address configured. The
endpoint therefore remains anchored through Asterisk and must transcode the
AudioSocket signed-linear stream to the negotiated SIP codec; no static output
proves which codec, direction, remote RTP address, or remote RTP port was
actually negotiated on the handset call.

The observed native counters do not prove speaker delivery. In the pinned
source, `res/res_rtp_asterisk.c:3513-3516` increments `txcount` after
`ast_sendto()` returns a positive local send result. It does not observe the
handset's socket, decoder, speaker, or carrier path. Conversely, an RX count
and Gateway microphone audio prove that Asterisk received media, but do not
prove that the remote endpoint accepts Asterisk's destination for the reverse
direction.

`rtp_symmetric=true` does provide a concrete comedia behavior:
`res/res_rtp_asterisk.c:8480-8493` replaces the RTP destination with the source
address of an accepted incoming RTP packet and logs that it will send there.
Consequently, a tone sent before the first accepted handset RTP packet can use
the SDP destination; a delayed tone after observed handset RX is the useful
discriminator. The current endpoint settings make this hypothesis plausible,
but the completed calls left no active SDP or RTP socket to verify it.

The next bounded observation should capture, during one active call only,
`pjsip show channels`, the matching `pjsip show channelstats`, and sanitized
local/remote UDP socket endpoints from `ss -uapn` inside the PBX container.
Triggering a delayed Gateway tone after inbound mic RX and comparing it with
native Asterisk playback separates the paths: native playback also silent with
RX present points to remote RTP/NAT or handset decode; native playback audible
but Gateway audio silent points to the AudioSocket-to-PJSIP bridge/format path.
No calls, logging changes, reloads, or native mutations were performed here.

**Unresolved questions:** the reviewed AudioSocket fix body and its disposable
Asterisk load test are not part of this inventory; the active handset SDP,
remote RTP destination, and native playback comparison remain unobserved.
