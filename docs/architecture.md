# Architecture

## Runtime Boundaries

```text
PSTN/SIP -> FreePBX/Asterisk -> ARI + AudioSocket -> gateway -> partner WSS
              ^          |
              |          +-> managed DID context
              |
Dashboard/admin UI -> control API -> PostgreSQL / Redis
                           |
                           +-> private PHP BMO bridge -> FreePBX
```

`apps/gateway` owns Asterisk lifecycle, transport adapters, call-state
transitions, and partner realtime delivery. `apps/control-api` owns browser and
management APIs, the local exact-DID mapping, and PBX apply state. The
`integrations/freepbx` PHP bridge is a private, source-restricted seam over the
FreePBX BMO methods; it is not a general Asterisk or shell proxy. `apps/admin-ui`
is a separate browser client. Shared partner contracts live only in
`packages/protocol`.

The MVP has one configured Asterisk and one deployment-bound FreePBX inventory.
The gateway has no multi-PBX routing layer, tenant-level trunk mirror, or
per-DID trunk selector: FreePBX globally matches an inbound DID. FreePBX remains
the authority for PJSIP trunk configuration and the generated inbound route;
the Gateway stores the exact DID, organization and single inbound Partner App
ownership, enabled state, optional outbound Partner App assignments, and whether
the managed route has been applied. The gateway will use AudioSocket first; an
ExternalMedia RTP adapter may be added behind the same transport boundary when
required.

Managed inbound routing follows the existing call lifecycle. A nonempty
`AI_GATEWAY_AGENT` set by an existing dialplan route selects that agent first.
If it is absent, the managed FreePBX context sets `AI_GATEWAY_DID`; the Gateway
resolves an exact local mapping only when the mapping is enabled and applied,
the Partner App is enabled and owned by the same organization, and a matching
live connection exists. Missing or invalid state fails closed by releasing the
channel. Reassigning a stored DID changes this local lookup for new calls and
does not require a PBX reload.

Outbound caller-number routing is a separate local policy. One exact number has
one inbound owner, while many Partner Apps in the same organization may be
assigned to that number for outbound use. For `outbound.originate`, the Gateway
considers only assignments whose number and Partner App are enabled and belong
to the connection's organization. With no assignments it preserves the legacy
native default; one eligible number is selected automatically; more than one
eligible number requires the exact `caller_number` field; and assignments with
no eligible number are rejected. The existing `calls:originate` scope and
destination allowlist remain required. Assignment changes are local and affect
new calls without a PBX reload; disabling a number or app prevents new calls
that would use it while existing calls continue. The current source passes a
selected number to ARI as `callerId` and `__TRUNKCIDOVERRIDE`. The
[2026-10-21 operator validation](operations/sip-trunks-and-phone-numbers.md#live-validation--2026-10-21)
observed native macro consumption and bounded carrier signaling/caller-ID
behavior, but external-handset delivery and reliable media for every PSTN call
remain unverified.

## Dependency Direction

- Browser code calls the control API; it never calls Asterisk directly.
- The control API calls only the narrow private FreePBX bridge for the approved
  trunk/DID operations; the browser never receives the bridge token or native
  FreePBX credentials.
- Partner code calls REST and WSS endpoints; it never receives Asterisk
  credentials.
- Asterisk traffic enters gateway adapters; it never reaches the dashboard.
- PostgreSQL and Redis are private implementation dependencies, not partner
  interfaces.
- SIP passwords remain in FreePBX and are accepted only for an authorized
  management operation. They are never returned or logged by the Gateway.

## Versioned Contracts

REST contracts are rooted at `/api/v1` and described by
`packages/protocol/openapi.yaml`. Realtime messages and servers are described
by `packages/protocol/asyncapi.yaml`. SIP trunk and phone-number management
routes remain browser/operator surfaces. The optional `caller_number` field on
`outbound.originate` is a backward-compatible partner contract addition; the
current Python and Node SDK source exposes it without a package release or
version bump. Existing clients continue to work when one eligible outbound
number is configured. Contract changes must update their schema and
corresponding executable tests together.
