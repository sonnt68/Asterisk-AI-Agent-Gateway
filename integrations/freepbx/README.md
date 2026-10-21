# FreePBX provisioner bridge

`index.php` is a private JSON POST endpoint for the deployed FreePBX 17 BMO
surface. The deployment copies this directory, including its hidden
`.htaccess`, to
`/var/www/html/gateway-provisioner/` and keeps the bearer token in
`/etc/asterisk/gateway-provisioner.json`. The state and lock paths must be on
the persistent `/var` mount. The PHP process must be able to write the managed
dialplan and state paths, but it must not have Docker socket access.

Copy the complete directory, including the hidden `.htaccess` file. Its
directory-scoped rewrite rule forwards the Authorization header to PHP on the
tested Apache image. Source and bearer checks run before the programmatic
FreePBX bootstrap (`freepbx_auth=false`). Verify an authenticated HTTP request
as well as the CLI probe; CLI success alone does not exercise Apache header
forwarding or the web bootstrap.

The configuration must include a strong `bearer_token`, private
`allowed_cidrs`, and an explicit `denied_cidrs` entry for the Docker gateway
(the pilot uses `172.18.0.1/32`). Requests use `REMOTE_ADDR`; forwarded headers
are ignored. The endpoint accepts only:

```json
{"operation":"status","payload":{}}
```

Supported operations are `status`, `list_trunks`, `save_trunk`, `save_did`, and
`apply`. Save operations never reload Asterisk. `apply` rejects any active PBX
channel, calls the fixed FreePBX `Framework::doReload(false)`, and returns
success only after exact DID and dialplan readback. Trunk deletion and arbitrary
commands are intentionally absent.

The managed context is generated in
`/etc/asterisk/extensions_gateway_managed.conf` and included once from
`extensions_custom.conf`. It sets `AI_GATEWAY_DID` and enters
`Stasis(asterisk-ai-gateway)`; it does not set `AI_GATEWAY_AGENT`.

For a read-only native probe after copying the bridge into an isolated
container path, run `php tests/freepbx/native_read_probe.php /etc/freepbx.conf
/path/to/copied/integrations/freepbx`.
It exercises the BMO bootstrap, active PJSIP transport lookup, active-channel
readback, reload-needed state, sanitized trunk listing, and registration status;
it does not save, reload, or delete PBX state.
