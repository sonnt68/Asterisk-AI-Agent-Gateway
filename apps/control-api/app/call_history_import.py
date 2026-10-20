"""Import sanitized legacy CDR summaries into an operator organization.

The importer intentionally accepts only the exported summary fields. It does
not copy caller numbers, gateway markers, or partner ownership into history.
"""

import argparse
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import CallRecord, Organization

LEGACY_NAMESPACE = uuid5(NAMESPACE_URL, "asterisk-ai-agent-gateway:legacy-cdr")
DEFAULT_TIMEZONE = UTC


@dataclass(frozen=True, slots=True)
class ImportResult:
    groups: int
    inserted: int
    skipped: int


def _timezone(name: object) -> tzinfo:
    if str(name).upper() in {"ICT", "UTC+7", "GMT+7"}:
        return timezone(timedelta(hours=7))
    return DEFAULT_TIMEZONE


def _parse_time(value: object, timezone: tzinfo) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Legacy CDR row has no calldate")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(UTC)


def _integer(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _group_key(row: dict[str, object], index: int) -> str:
    for name in ("linkedid", "uniqueid"):
        value = row.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise ValueError(f"Legacy CDR row {index} has neither linkedid nor uniqueid")


def _status(rows: list[dict[str, object]]) -> tuple[str, bool, str]:
    dispositions = {str(row.get("disposition", "")).strip().upper() for row in rows}
    if "ANSWERED" in dispositions:
        return "completed", True, "completed"
    if "BUSY" in dispositions:
        return "busy", False, "busy"
    if "NO ANSWER" in dispositions or "NOANSWER" in dispositions:
        return "no_answer", False, "no_answer"
    return "failed", False, "imported_unknown"


def _summary(
    key: str,
    rows: list[dict[str, object]],
    organization_id: str,
    source_timezone: tzinfo,
) -> CallRecord:
    timestamps = [_parse_time(row.get("calldate"), source_timezone) for row in rows]
    created_at = min(timestamps)
    status, answered, reason = _status(rows)
    duration = max((_integer(row.get("duration")) for row in rows), default=0)
    talk = max((_integer(row.get("billsec")) for row in rows), default=0)
    return CallRecord(
        call_id=str(uuid5(LEGACY_NAMESPACE, f"{organization_id}:{key}")),
        organization_id=organization_id,
        partner_app_id=None,
        agent_slug=None,
        direction="unknown",
        source="imported",
        status=status,
        terminal=True,
        answered=answered,
        reason=reason,
        hangup_cause=None,
        dial_status=None,
        sequence=0,
        created_at=created_at,
        updated_at=created_at,
        answered_at=None,
        ended_at=None,
        duration_seconds=duration,
        talk_seconds=talk,
        history_complete=False,
    )


def import_legacy_json(
    path: str | Path,
    organization_id: str,
    *,
    session_factory: Callable[[], Session] | None = None,
) -> ImportResult:
    """Import grouped legacy summaries idempotently for one operator org."""
    source_path = Path(path)
    with source_path.open(encoding="utf-8") as handle:
        document = json.load(handle)
    if not isinstance(document, dict) or not isinstance(document.get("records"), list):
        raise ValueError("Legacy CDR export must contain a records array")
    rows = [row for row in document["records"] if isinstance(row, dict)]
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[_group_key(row, index)].append(row)
    timezone = _timezone(document.get("timezone"))
    factory = session_factory or SessionLocal
    inserted = 0
    skipped = 0
    with factory() as session:
        if session.get(Organization, organization_id) is None:
            raise ValueError("Organization does not exist")
        for key, grouped_rows in groups.items():
            record = _summary(key, grouped_rows, organization_id, timezone)
            existing = session.get(CallRecord, record.call_id)
            if existing:
                if existing.organization_id != organization_id or existing.source != "imported":
                    raise ValueError(f"Legacy call id collision: {record.call_id}")
                skipped += 1
                continue
            session.add(record)
            inserted += 1
        session.commit()
    return ImportResult(len(groups), inserted, skipped)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import sanitized legacy CDR summaries")
    parser.add_argument("--file", required=True, help="Path to the sanitized JSON export")
    parser.add_argument("--organization-id", required=True, help="Operator organization UUID")
    args = parser.parse_args(argv)
    result = import_legacy_json(args.file, args.organization_id)
    print(f"groups={result.groups} inserted={result.inserted} skipped={result.skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
