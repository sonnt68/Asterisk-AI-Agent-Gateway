# Durable call history handoff

## Delivered

- Added `CallRecord` and composite-key `CallSignal` models plus migration
  `migrations/versions/0003_call_history.py`.
- Added `CallHistoryStore` with async `start(call)`, `record(call, snapshot)`,
  `recover_interrupted()`, and `flush_pending()` methods. SQLAlchemy work runs
  through `asyncio.to_thread`; initial writes are strict, later failures retry,
  log, queue, and preserve live cleanup.
- Added deterministic, idempotent sanitized CDR import in
  `app/call_history_import.py`, with `python -m app.call_history_import
  --file PATH --organization-id UUID`. Imported records have no partner app,
  `source="imported"`, `history_complete=False`, no caller fields, and no
  invented answered/ended timeline.
- Captured organization/app/direction/source/create time on `ActiveCall`, and
  persist inbound before activation and outbound before ARI originate.
- Durable status transitions are attempted before WebSocket status delivery;
  originate HTTP failure is persisted as terminal `originate_failed` without a
  premature `call.status` notification.

## Root wiring

The global registry accepts an optional store:

```python
store = CallHistoryStore()
registry.history_store = store
await store.recover_interrupted()
```

Call `await registry.flush_history()` on shutdown and periodically if desired.

## Validation

- `pytest -q`: 183 passed, four existing `aiohttp.BasicAuth` deprecation warnings.
- Focused persistence/history/signal/origination suites: 66 passed.
- Targeted Ruff and compileall passed.
- Alembic SQLite upgrade reached `0003_call_history` head.
- Pure parser check grouped 1,882 source rows into 779 imported summaries; all
  records were unassigned and `history_complete=False`.

## Unresolved questions

- Deployment/import execution remains intentionally unattempted; no live
  database or source mutation was performed.
