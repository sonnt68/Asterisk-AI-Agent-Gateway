# Connect one Asterisk

## Requirements

- Asterisk 18+ with ARI, Stasis, `chan_audiosocket` and `app_audiosocket` loaded.
- Private reachability: gateway to ARI 8088 and Asterisk to AudioSocket 8090.
- A dedicated least-privilege ARI account. Never give it to a partner.

Set the ARI variables, `ASTERISK_DOCKER_NETWORK`, and
`AUDIOSOCKET_ADVERTISE_HOST` in deployment secrets. The advertised host must
resolve from the Asterisk network.

```asterisk
[from-asterisk-ai-gateway]
exten => s,1,NoOp(Asterisk AI Gateway)
 same => n,Set(AI_GATEWAY_AGENT=support-agent)
 same => n,Stasis(asterisk-ai-gateway)
 same => n,Hangup()

[from-internal-custom]
exten => 9898,1,Goto(from-asterisk-ai-gateway,s,1)
```

The gateway creates the bridge and native `AudioSocket/.../c(slin)` leg via
ARI. Do not put partner URLs, API keys, or AudioSocket calls in the dialplan.

`GATEWAY_MEDIA_SAMPLE_RATE` (default 8000) sets both that channel format and
the rate advertised to partners in `call.started`; the two are derived from
one value precisely so they cannot drift. Leave it at 8000 unless the
endpoints on both sides are genuinely wideband — the trunk is 8 kHz either
way, so a higher rate only adds a resample at each boundary, and a
non-integer ratio there is audible.

If native AudioSocket cannot be used, set `GATEWAY_MEDIA_TRANSPORT=externalmedia`
and `EXTERNAL_MEDIA_ADVERTISE_HOST` to a private address resolvable by Asterisk.
The fallback uses RTP/UDP PCMU on Asterisk, which is advertised to partners as
`pcm_mulaw` at 8 kHz. Open only the required private UDP path; do not expose it
to partners or the public internet.

Verify `ari show apps`, dashboard readiness, `call.started`, binary audio and
`call.ended`. Active call/media gauges must return to zero after hangup.
