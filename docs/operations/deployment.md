# Deployment

The pilot uses Docker Compose at `/opt/asterisk-ai-agent-gateway` and binds
dashboard/API to loopback until TLS termination is configured.

```bash
docker compose build api admin-ui
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:18080/api/v1/system/health
docker compose exec api alembic current
```

## Dashboard exposure

`GATEWAY_ADMIN_BIND` controls the interface the dashboard port binds to. It
defaults to `127.0.0.1`, so a fresh deployment is reachable only through a
tunnel:

```bash
ssh -i ~/.ssh/id_ed25519 -L 15173:127.0.0.1:15173 root@<gateway-host>
```

Open `http://localhost:15173`. It reverse-proxies REST and WSS to the API.

The pilot host binds publicly instead (`GATEWAY_ADMIN_BIND=0.0.0.0`,
`GATEWAY_ADMIN_PORT=15173`), serving the dashboard at
`http://<gateway-host>:15173`. Port 80/443 on that host belongs to FreePBX, so
the gateway must not claim them. `GATEWAY_WEB_ORIGIN` must match the URL the
browser uses, because the origin middleware rejects every other origin.

Public binding over plain HTTP puts the `gateway_session` cookie on the wire in
cleartext. Terminate TLS in front of the dashboard before the pilot carries real
tenant traffic, and set `GATEWAY_COOKIE_SECURE=true` once it does.
Back up PostgreSQL before migration. Roll back by restoring that backup and the
matching previous image, not by running a downgrade under active writers.
