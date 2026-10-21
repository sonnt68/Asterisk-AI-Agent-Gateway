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

For deployment-bound FreePBX SIP trunk and inbound phone-number management,
follow the [SIP trunks and phone numbers runbook](sip-trunks-and-phone-numbers.md)
and the [private FreePBX bridge README](../../integrations/freepbx/README.md).
The bridge is the supported integration seam because the target FreePBX
deployment does not provide the stock trunk GraphQL surface. The Gateway uses
the narrow PHP BMO bridge; the browser and partners never call FreePBX or
receive its native credentials.

The control API is configured with the three deployment values
`FREEPBX_BRIDGE_URL`, `FREEPBX_BRIDGE_TOKEN`, and
`FREEPBX_OPERATOR_ORGANIZATION_ID`. Keep the bridge URL on the private path
defined by the deployment and keep the token in deployment secrets. The
configured organization is the shared-PBX authority boundary: only its Owner
and Admin members can manage trunks or phone-number mappings. Do not copy
secret values or invent a bridge host name in an operations note.

The managed FreePBX context sets `AI_GATEWAY_DID` and enters
`Stasis(asterisk-ai-gateway)`. It deliberately does not set
`AI_GATEWAY_AGENT`, so the existing nonempty `AI_GATEWAY_AGENT` route continues
to take precedence when an older dialplan sends a call directly to an agent.

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

For production SIP password entry, prefer HTTPS or a trusted network path. The
UI warns that the current pilot admin URL may be plain HTTP; this is an
existing readiness limitation, not a new API block. If a browser is reached
through an SSH tunnel, `GATEWAY_WEB_ORIGIN` still must match the browser's
origin because cookie-authenticated writes reject every other origin. An SSH
credential probe of the private bridge path does not by itself prove browser
TLS or origin configuration. Trunk inventory/configuration covers the
supported common PJSIP fields only; outbound route/carrier activation, DID
purchase or porting, and live PSTN call behavior are outside this connection
check and are not inferred from a successful bridge response.
