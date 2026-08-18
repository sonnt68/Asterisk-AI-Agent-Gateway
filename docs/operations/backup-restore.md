# Backup and restore

Create a restricted backup before every schema migration:

```bash
docker compose exec -T postgres sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > backup.sql
chmod 600 backup.sql
test -s backup.sql
```

Restore only in a maintenance window after stopping API writers. Validate the
backup and target database explicitly, restore with `ON_ERROR_STOP=1`, deploy
the matching API, then check migration head, health, login and a call fixture.
Redis contains ephemeral leases only and is not durable tenant authority.
