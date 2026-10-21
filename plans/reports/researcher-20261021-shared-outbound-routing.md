# Shared outbound caller ID and FreePBX route research — 2026-10-21

**Status:** DONE_WITH_CONCERNS

## Outcome

An ARI originate `callerId` value does not guarantee either the provider trunk or
the on-wire caller number on this FreePBX 17 deployment.

- FreePBX selects outbound routes from the dialed extension/context and route
  sequence/dial pattern. It does not select a route from `CALLERID(number)`.
- The generated outbound caller-ID macro can replace the ARI caller ID with the
  selected trunk's configured Outbound Caller ID, a user/extension caller ID,
  a route override, an emergency caller ID, or a forced trunk caller ID.
- A provider can still normalize or reject the resulting SIP identity after
  FreePBX. Provider acceptance remains a separate, unverified boundary.

## Native deployment evidence

The read-only BMO probe returned four routes and four PJSIP trunks. Sensitive
values were intentionally omitted.

The probe used native `Core::getAllRoutes()`,
`getRoutePatternsByID()`, `getRouteTrunksByID()`, `listTrunks(false)`,
`getTrunkDetails()`, and `getTrunkRoutesByID()`; it performed no writes.

- Trunks `1`, `2`, `3`, and `4`: `tech=pjsip`, enabled, configured
  `outcid` present, `keepcid=off`, and one outbound-route association each.
  The PJSIP `match` field is present; `from_user` is not set on the current
  trunks.
- Routes `2`, `3`, `4`, and `5` have sequence values `0`, `1`, `2`,
  and `3`. Each has one `X.` pattern, no route-level Outbound Caller ID,
  and one trunk association: route 2 → trunk 2, route 3 → trunk 1, route 4 →
  trunk 3, route 5 → trunk 4.
- Asterisk readback shows `from-internal` includes
  `from-internal-additional`; that context includes `outbound-allroutes`.
  `outbound-allroutes` includes `outrt-2`, then `outrt-3`, `outrt-4`,
  and `outrt-5`. A number matching `X.` therefore enters the first matching
  route in this order; later routes are native dialplan alternatives/fallback
  behavior, not caller-ID-based provider selection.

## Caller-ID override proof

FreePBX source and generated dialplan agree:

- `/var/www/html/admin/modules/core/functions.inc.php:2070-2104`
  publishes `OUTCID_<trunk_id>`, `OUTKEEPCID_<trunk_id>`, and
  `FORCEDOUTCID_<trunk_id>` globals from the native `trunks` row.
- `.../functions.inc.php:2281-2287` applies a route Outbound Caller ID as
  `TRUNKCIDOVERRIDE` when configured and no higher-priority override exists.
  The current routes have no route-level Outbound Caller ID.
- `.../functions.inc.php:3076-3090` generates
  `macro-outbound-callerid`: it sets `TRUNKOUTCID` from the selected trunk,
  applies it to `CALLERID(all)` when present, then applies user CID and
  `TRUNKCIDOVERRIDE`; `FORCEDOUTCID` wins over the override for
  `keepcid=all`.
- Live `dialplan show macro-outbound-callerid` confirms the deployed order:
  trunk CID at priority 30, user CID at 31, override/forced CID at 32, then
  fallback at 34.
- `/var/www/html/admin/modules/core/functions.inc/drivers/PJSip.class.php:690-697`
  maps native `from_user` to the PJSIP endpoint's SIP From user. If an
  operator configures it later, it is another trunk-level identity constraint;
  it is currently absent on all four trunks.

Therefore, setting only ARI `callerId` before
`Local/<destination>@from-internal/n` is insufficient on this PBX: the
FreePBX route macro will normally replace it with the selected trunk's
configured `outcid` before `Dial()`.

## Read-only inherited-override probe

The live PBX was probed without changing native configuration or reloading.
Each run used a unique ARI app and two ephemeral Local channel IDs, with
`Local/s@macro-outbound-callerid/n`, `ARG1=2`, and a synthetic `callerId`.
The override run passed the inherited variable in the ARI JSON body, not as a
query parameter:

```json
{"variables":{"ARG1":"2","__ARG1":"2","__TRUNKCIDOVERRIDE":"999999920261021"}}
```

The no-override run emitted a `TRUNKOUTCID` varset whose value matched the
sanitized BMO `list_trunks` value for trunk 2. Its `ChannelCallerId` events
contained both the initial synthetic caller ID and the native trunk CID. The
override run emitted `__TRUNKCIDOVERRIDE` varsets whose value matched exactly
`999999920261021`, and its `ChannelCallerId` events contained that synthetic
override after the native trunk CID. This proves the `__` variable inherited
across the Local pair and was consumed by priority 32 of the deployed native
macro; it does not prove the provider's eventual SIP identity.

The probe produced `Dial` events only for Local peers: both sides had Local
channel names and neither side had a PJSIP channel name. The live
`macro-outbound-callerid` context contains no `Dial()` application, so this
was Local channel setup rather than a carrier attempt. The macro exited before
`StasisStart`; all probe channels self-destroyed, cleanup DELETEs returned
404, and the post-probe Asterisk count was `0 active channels` and `0 active
calls`.

## Current inbound trunk context

The four current PJSIP trunk endpoints are `842444562933`, `842444562943`,
`842444562952`, and `842444563065`; each generated endpoint has
`context=from-pstn`. `from-pstn` includes `ext-did`, and `ext-did` includes
`ext-did-0002`. That context contains exact extensions for all four numbers,
each ending in `Goto(from-ai-gateway-managed,<same-number>,1)`. The managed
context then runs `NoOp`, `Set(AI_GATEWAY_DID=<same-number>)`,
`Stasis(asterisk-ai-gateway)`, and `Hangup`.

There are no active `from-pstn-custom`, `ext-did-custom`, or
`ext-did-post-custom` contexts in the current dialplan; their include targets
are declared but absent. Current inbound calls therefore use the native DID
lookup into the managed Gateway context, rather than a legacy custom context.

## Recommended narrow integration

Treat an outbound-app assignment as an authorization for a permitted caller
number and a requested presentation identity. Keep provider/trunk choice under
native PBX route ownership.

1. Store the exact assigned number per app in the Gateway, allowing many apps to
   reference the same number while retaining the existing one-to-one inbound
   DID route. Validate the originate request against that assignment and pass
   the exact number as ARI `callerId`; never accept an arbitrary caller ID.
2. Keep the existing outward context contract
   `Local/<destination>@<context>/n`. For the current deployment, the context
   must be an outward-routing context such as `from-internal`; inbound trunk
   contexts do not select outbound routes.
3. Do not expose a public trunk selector or infer a provider from the caller
   number. Current native route order sends an `X.` destination to the first
   matching route/trunk, so provider choice remains the operator's route
   configuration.
4. Before claiming caller-ID fidelity, require an operator-approved native
   policy. The least invasive policy is a dedicated Gateway outbound route/trunk
   whose route Outbound Caller ID is empty, trunk Outbound Caller ID is empty,
   `keepcid` is not `all`, and the provider accepts the assigned numbers.
   The current PBX does not meet the empty-trunk-CID part: all four trunks have
   `outcid` configured.
5. If exact caller-ID preservation is required despite existing trunk CIDs,
   use a fixed, reviewed Gateway dialplan seam that sets a validated
   `TRUNKCIDOVERRIDE` immediately before the native outbound macro, and reject
   trunks with `keepcid=all` or emergency-CID policy that would force another
   identity. This seam must be read back and applied as managed PBX state; do not
   use arbitrary partner-supplied dialplan or a public trunk ID.
6. If provider selection itself is a requirement, add an explicit operator-owned
   mapping to a fixed route/trunk context. Caller ID alone cannot safely express
   that selection.

## Validation boundaries

No trunk, route, DID, caller, or reload operation was performed. The evidence is
source inspection, BMO readback of non-secret fields, Asterisk dialplan
readback, and an internal ARI Local-only macro probe. No carrier/PSTN call was
attempted, so SIP provider acceptance, number verification, and actual
transmitted P-Asserted-Identity/From behavior remain unverified.

## Unresolved questions

- Should the product promise only a requested caller ID, or a verified
  on-wire number after native FreePBX and provider policy?
- Will operators provision a dedicated Gateway outbound route/trunk with empty
  native Outbound Caller ID, or is a managed `TRUNKCIDOVERRIDE` seam approved?
- If provider selection becomes necessary, which operator-owned route/trunk
  mapping is authoritative?

**Status:** DONE_WITH_CONCERNS
**Summary:** Current FreePBX route selection is destination/order based, while native trunk and route caller-ID settings can overwrite ARI callerId. Shared outbound-number assignments should authorize caller ID only until an explicit native policy provides deterministic presentation.
**Concerns/Blockers:** Current trunks all have native Outbound Caller ID values, so ARI callerId alone cannot be presented as guaranteed provider caller ID.

