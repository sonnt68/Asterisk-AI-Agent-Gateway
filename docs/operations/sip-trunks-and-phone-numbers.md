# SIP trunks and phone numbers

This is the internal operator guide for the deployment-bound FreePBX
management surfaces. It covers the supported PJSIP trunk subset and exact
phone-number mappings for inbound routing and optional shared outbound caller
numbers. It does not provision a carrier, purchase or port a DID, or establish
reliable media for every carrier or external-handset call. The bounded live
validation result is recorded below.

## Authority and access

FreePBX is authoritative for PJSIP trunk configuration, SIP passwords, and the
managed inbound DID route. The Gateway stores the exact DID string, one inbound
Partner App owner, optional same-organization outbound Partner App assignments,
its label and enabled state, and whether the managed route has been applied. It
does not mirror the PBX trunk inventory or offer a per-DID trunk selector: this
FreePBX deployment matches inbound DIDs globally.

The management boundary is the organization named by
`FREEPBX_OPERATOR_ORGANIZATION_ID`. Only an Owner or Admin of that exact
organization can use the management API. The value is an explicit deployment
binding, not a value inferred from a tenant, trunk label, or DID.

The Admin UI exposes the `/sip-trunks` and `/call-routing` pages only when the
authenticated user can manage the bound organization. `/phone-numbers` remains
a compatibility route to Call Routing. The corresponding control API surfaces
are:

- `GET /api/v1/asterisk/provisioning` for bridge capability and pending state;
- `GET/POST /api/v1/asterisk/trunks` and
  `PATCH /api/v1/asterisk/trunks/{trunk_id}` for the trunk subset;
- `GET/POST /api/v1/phone-numbers` and
  `PATCH /api/v1/phone-numbers/{phone_id}` for exact mappings and outbound
  assignments; and
- `POST /api/v1/asterisk/apply` for the guarded PBX reload and readback.

These are operator/browser surfaces. Shared outbound selection also adds the
optional `caller_number` field to `outbound.originate`; the Python and Node
SDK source exposes it without a package release or version bump. See
[partner call control](../partner/call-control.md) for the selection contract.

## Setup and prerequisites

Install and configure the private PHP bridge using the
[FreePBX bridge README](../../integrations/freepbx/README.md). That README is
the authority for the deployment copy path, bridge configuration file,
permissions, source allowlist, token, persistent state and lock paths, and
FreePBX BMO bootstrap. Do not put bridge secrets or real phone numbers in this
guide.

The control API reads these deployment values:

```text
FREEPBX_BRIDGE_URL
FREEPBX_BRIDGE_TOKEN
FREEPBX_OPERATOR_ORGANIZATION_ID
```

All three are required before the control API reports the management bridge as
configured. Keep the URL on the deployment's private network path and keep the
token in deployment secrets. For production SIP password entry, prefer HTTPS
or a trusted network path. The UI warns that the current pilot admin URL may
be plain HTTP; this is an existing readiness limitation, not a new API block.
If a browser is reached through an SSH tunnel, `GATEWAY_WEB_ORIGIN` must still
match the browser's origin because cookie-authenticated writes reject every
other origin. An SSH credential probe of the private bridge path does not by
itself prove browser TLS or origin configuration. This guide does not invent a
hostname.

The phone-number table is the additive `0005_phone_numbers` migration. Shared
outbound grants use additive migration `0006_outbound_phone_apps`. Before any
deployment, take a restricted database backup, restore it into an isolated
database, and rehearse both migrations there. Use the matching application
image and restore the backup rather than running a downgrade if the rehearsal
or rollout fails.

## FAQ: what the dashboard manages

Once the one-time PBX integration is installed, the Gateway/Admin UI is enough
for routine supported operations: edit the common PJSIP trunk fields, manage
exact inbound numbers and their Partner App owner, manage shared outbound
assignments, and run the guarded Apply/readback flow. These changes do not
require an operator to edit the PBX directly.

The one-time and deployment-owned prerequisites remain outside the dashboard:
ARI endpoint and credentials, the Asterisk/AudioSocket integration, the private
FreePBX bridge installation and source/token policy, outbound dialplan
route/context and trunk selection, SIP/RTP network and firewall/NAT settings,
and carrier account, number, or route activation. Apply manages the Gateway's
approved FreePBX state; it does not install Asterisk modules, create provider
routes, or activate PSTN service. See the [FreePBX bridge README](../../integrations/freepbx/README.md)
and [native AudioSocket repair README](../../integrations/freepbx/asterisk/README.md)
for deployment-owned setup.

## SIP trunks

The UI and bridge expose a common PJSIP subset:

- display name, provider host, port, and an active FreePBX transport;
- `authentication`: `none` or `outbound` (username/password);
- `registration`: `none` or `send`;
- username and auth username;
- source IP/CIDR match values;
- from domain, from user, contact user, outbound caller ID, and codec choices;
  and
- enabled/disabled state.

The inventory can also contain existing native FreePBX trunks with `inbound` or
`both` authentication, or `receive` registration. Those values are returned as
read-only inventory: the control API rejects edits for unsupported native modes
and the UI blocks the editor while preserving the current mode. This guide
does not authorize converting those trunks into the supported editor subset.

The bridge preserves unspecified settings on an edit and reports only a
boolean `password_set` indicator. Password values are accepted for a create or
replacement operation, never returned by the Gateway, and never logged. Trunk
deletion is not exposed; disable a trunk and apply the pending change instead.
Provider-specific trunk fields, outbound route selection, and carrier
activation are outside this common subset.

Saving a trunk writes the FreePBX configuration and leaves the native reload
pending. The UI shows bridge reachability and pending state. A successful save
does not by itself prove that the provider accepts registration or that an
outbound route can place a call; see [live validation](#live-validation--2026-10-21)
for the bounded provider evidence.

## Call Routing mappings

Create a mapping with an exact string matching an optional `+` followed by 1 to
32 digits. The Gateway does not normalize, format, or otherwise reinterpret
the value. The local database enforces global exact-number uniqueness.

The Add phone number form lets operators choose an unassigned numeric Outbound
Caller ID from the SIP trunk inventory, or enter a different DID manually.
Duplicate Caller IDs appear once with their source trunk names. Choosing a
number fills its exact value and an initial label; it does not bind inbound
routing to that trunk or prove that the caller ID is an assigned inbound DID.
Use the exact DID the provider sends, including its prefix. A trunk can carry
multiple DIDs, so manual entry remains available.

Each mapping selects exactly one inbound Partner App in the same organization
and stores a label and enabled state. It may also list zero or more outbound
Partner Apps from that organization. An outbound assignment grants the app
permission to use the exact number for new outbound calls; it does not change
inbound ownership. The number is immutable after creation. A mapping does not
select a trunk because FreePBX performs global DID matching. There is no delete
action in the UI or API.

The phone-number API returns `outbound_partner_apps` and
`outbound_partner_app_ids`. On create, send `outbound_partner_app_ids` to add
assignments. On PATCH, omitting the field preserves the current assignments;
send an empty array to clear them or a list to replace them. New assignments
must name enabled Partner Apps in the same organization. An existing disabled
assigned app remains visible so it can be removed, while a disabled app cannot
be newly assigned.

Changing the inbound Partner App assignment updates the local lookup used for
new calls and does not require a PBX reload. Outbound assignment changes also
take effect for new calls immediately and do not reload FreePBX. Disabling a
mapping makes the Gateway stop new inbound and outbound calls for that number;
existing calls continue. The managed FreePBX route remains present because
route deletion is not exposed, while the Gateway resolver enforces the disabled
state. For inbound resolution, a missing app or live connection, or a disabled
or unapplied mapping, fails closed.

For outbound calls, an app with no assignments keeps the legacy native default.
One eligible enabled number is selected automatically. More than one eligible
number requires the partner to send the exact `caller_number`; assignments
whose number or app is disabled are ineligible, and an app with assignments
but no eligible number is rejected. The existing `calls:originate` scope and
destination allowlist remain required. The source currently passes a selected
number to ARI as `callerId` and `__TRUNKCIDOVERRIDE`; the live validation below
observed native macro consumption and bounded caller-ID/signaling behavior.
It does not establish reliable carrier media or external-handset behavior.

Adding a mapping creates the managed FreePBX DID route and leaves the Gateway
state pending until Apply verifies it. The UI displays `Awaiting apply` until
the local `pbx_applied` state is set by verified readback. Follow the pending
state shown by the UI after any trunk or newly added DID route change. Local
inbound reassignment and outbound assignment changes do not need Apply.

## Apply and readback

Apply is explicit and covers all pending managed FreePBX state:

1. Confirm that no Gateway or PBX calls are active. The API and bridge reject
   Apply while active channels exist.
2. The private bridge checks its route state and generated dialplan, then calls
   the fixed native FreePBX `Framework::doReload(false)` operation.
3. It reads back the managed FreePBX DID, the generated dialplan, and the
   `from-ai-gateway-managed` Asterisk context. Every route must contain the
   exact number, `AI_GATEWAY_DID`, and
   `Stasis(asterisk-ai-gateway)`.
4. The Gateway marks `pbx_applied` only after the exact readback matches. A
   drift, unavailable readback, active-call rejection, or failed reload leaves
   the state pending and exposes an error for retry or recovery.

The bridge supports only `status`, `list_trunks`, `save_trunk`, `save_did`, and
`apply`. It uses a private bearer token, source CIDR checks and a lock; it has
no arbitrary shell, raw SQL, Docker socket, or generic command/GraphQL proxy.
The target FreePBX deployment's stock trunk GraphQL provider is absent, so the
tested BMO seam is the supported integration boundary.

## Native AudioSocket repair

The pilot now uses a derived FreePBX image with only the matching-version
`res_audiosocket.so` header-read repair from the [native repair README](../../integrations/freepbx/asterisk/README.md).
Asterisk remains `21.10.2`; the deployed image digest is
`sha256:a3d9f8612a88d8bcc9f4469f06a5ea3c6cf8bc79cd7feaf53e7f5ff796874e23`,
and the replacement module hash is
`sha256:bf41d5a079e28f9827527b29908080004ffa390532f9fad753ae477820946b0f`.
Compose changed only the `freepbx` service image. The restricted deployment
backup is `/opt/asterisk-ai-agent-gateway/backups/audiosocket-20261021T1100/`.

The deployment checks verified ABI, symbols and libc dependencies, loaded all
three AudioSocket modules in an isolated process, and passed the baseline and
patched C regressions on macOS and Linux. The repair changes only header reads:
an idle EAGAIN read becomes a null frame, while partial headers still use the
existing bounded poll behavior. It does not change payload framing, caller ID,
routing, Gateway audio writes, the Asterisk core, or the wire format. Final
four-number repeat results are recorded in the live validation below.

## Inbound call resolution

The generated managed context is included once from the FreePBX custom
dialplan. It sets `AI_GATEWAY_DID` and enters the existing Gateway Stasis app;
it does not set `AI_GATEWAY_AGENT`.

When an inbound channel enters the call lifecycle, a nonempty legacy
`AI_GATEWAY_AGENT` value is resolved first. If it is absent, the lifecycle reads
`AI_GATEWAY_DID`, finds an exact local mapping that is enabled and applied,
checks that its Partner App is enabled and owned by the same organization, and
requires the app's matching live connection. If any check fails, the channel is
released without routing. The inbound path does not select a trunk; the
optional outbound `caller_number` contract is described in
[partner call control](../partner/call-control.md).

## Live validation — 2026-10-21

The deployed API reached migration head `0006_outbound_phone_apps`. Focused
routing/migration/runtime/SDK validation passed (`61` tests), full repository
validation passed (`234` tests), Node SDK tests passed (`24`), and the Admin UI
production build passed. No SDK package or network setting changed; the later
native repair deployment changed only the `res_audiosocket.so` module while
keeping the Asterisk `21.10.2` core unchanged.

The deployed native FreePBX `macro-outbound-callerid` consumed
`__TRUNKCIDOVERRIDE` and preserved the selected caller ID through the local
macro path. Four internal DID probes reached the expected Partner Apps with
PCM audio. Eight internal outbound probes, covering two apps on each of four
numbers, selected the assigned caller ID and delivered PCM audio to `*43`.

Before the native repair, four carrier-owned number loops all showed signaling
up, the expected inbound Partner App, and exact inbound caller identity. In the
final four outbound
loops, two carried PCM audio and two ended with `CallRecord.answered=true` and
`reason=media_failed` within 0.1 seconds. The PBX logged
`res_audiosocket.c EAGAIN` (`Resource temporarily unavailable`) before
destroying AudioSocket on those failures. Passing calls used native PJSIP
transmit/receive with 50 frames and zero packet loss. After the native repair,
five four-number SIP batches (20 calls) observed non-silent PCM in both
directions, with no AudioSocket errors recurring after `11:14:24 UTC`. The
final database proof found 61 terminal records and zero `CallRecord` rows with
`media_failed`.

The final batch used a two-second tone and a 100-frame counter: all four calls
completed the test, both native legs transmitted 100 frames, three received
100 and one received 99, and every call reported transmit/receive packet loss
of zero. An earlier fourth-batch strict receive threshold recorded 49 frames
against a 50-frame threshold despite non-silent PCM in both directions; treat
that as a measurement-limit observation, not a silence result or a claim that
every strict counter reached 100.

The full internal four-DID and eight shared-outbound set passed. Post-run state
was zero Gateway calls, zero Gateway connections and zero native channels; the
four outbound grants and original inbound mappings remained present. The
A bounded external-handset listening check then covered all four source calls:
all answered and delivered non-silent microphone audio. The initial two-second
tone began before handset listening, so a delayed Gateway tone and native
prompt were used to confirm audibility across all four calls; one busy first
attempt required a retry. Handset-displayed Caller ID was not confirmed, and
no NAT or network setting changed. This resolves the bounded handset evidence
gap but does not establish every network path or an end-to-end PSTN media SLO.

## Rollout limits

Before a requested deployment, retain evidence for the backup, isolated
`0005_phone_numbers` and `0006_outbound_phone_apps` migrations,
zero-active-call preflight, Apply response, and exact FreePBX/Asterisk
readback. A local HTTP success, UI transition, or bridge reachability result is
not sufficient by itself; use the recorded live evidence and repeat the
carrier/handset checks for the deployment.

Carrier/PSTN account provisioning, outbound route activation, DID purchase or
porting, provider-specific trunk behavior, handset-displayed Caller ID, and
reliable media across every network remain deployment responsibilities. The
validation above records bounded signaling, caller-ID, media and handset
listening observations; it does not claim that all PSTN paths or SLOs passed.
