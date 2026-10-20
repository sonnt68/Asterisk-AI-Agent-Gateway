"""Numbered pages and historic agent options retain the same ownership scope."""

from datetime import UTC, datetime

import pytest
import test_call_history_api as history_api
from app.models import CallRecord
from sqlalchemy.orm import Session
from test_call_history_api import _add_call, _browser_client

history = history_api.history


def _set_agent(session, call_id, slug):
    session.get(CallRecord, call_id).agent_slug = slug


def test_agent_options_use_historic_slugs_in_current_organization(history):
    with Session(history.engine) as session:
        _set_agent(session, "00000000-0000-0000-0000-000000000102", "retired-sales")
        _set_agent(session, "00000000-0000-0000-0000-000000000201", "private-other-org")
        session.commit()
    with _browser_client(history, "owner") as client:
        response = client.get("/api/v1/call-history/agents")
    assert response.status_code == 200
    assert response.json() == {"items": ["retired-sales", "support-agent"]}
    assert history.client.get("/api/v1/call-history/agents").status_code == 401


def test_numbered_pages_count_only_filtered_owned_calls_and_keep_stable_ties(history):
    tie = datetime(2026, 10, 20, 10, tzinfo=UTC)
    ids = [f"00000000-0000-0000-0000-00000000030{n}" for n in range(1, 6)]
    with Session(history.engine) as session:
        for call_id in ids:
            _add_call(session, history.organization_id, history.app_one_id, call_id,
                      status="busy", direction="inbound", created_at=tie)
        _set_agent(session, "00000000-0000-0000-0000-000000000102", "sales-agent")
        session.commit()
    headers = {"Authorization": f"Bearer {history.partner_key}"}
    filters = {"agent_slug": "support-agent", "status": "busy", "direction": "inbound",
               "started_after": "2026-10-20T09:00:00Z", "started_before": "2026-10-20T11:00:00Z",
               "limit": 2}
    # Jump directly to the last page, without traversing previous cursors.
    last = history.client.get("/api/v1/partner/calls", headers=headers, params={**filters, "page": 3})
    assert last.status_code == 200
    assert {k: v for k, v in last.json().items() if k != "items"} == {
        "page": 3, "page_size": 2, "total": 5, "total_pages": 3, "next_cursor": None,
    }
    assert [row["call_id"] for row in last.json()["items"]] == ids[:1]
    first = history.client.get("/api/v1/partner/calls", headers=headers, params={**filters, "page": 1})
    assert [row["call_id"] for row in first.json()["items"]] == ids[:2:-1]
    # Filtering by a different app's agent never broadens key ownership.
    foreign = history.client.get("/api/v1/partner/calls", headers=headers,
                                 params={"page": 1, "agent_slug": "sales-agent"})
    assert foreign.json()["items"] == []
    assert foreign.json()["total"] == 0 and foreign.json()["total_pages"] == 1
    assert history.client.get("/api/v1/partner/calls", headers=headers,
                              params={**filters, "page": 99}).json()["items"] == []


def test_browser_numbered_totals_do_not_leak_imported_or_foreign_records(history):
    with _browser_client(history, "owner") as owner, _browser_client(history, "developer") as developer:
        all_calls = owner.get("/api/v1/call-history", params={"page": 1, "limit": 1})
        assigned = developer.get("/api/v1/call-history", params={"page": 1})
        filtered = owner.get("/api/v1/call-history", params={"page": 1, "agent_slug": "support-agent"})
    assert all_calls.json()["total"] == 3 and all_calls.json()["total_pages"] == 3
    assert assigned.json()["total"] == filtered.json()["total"] == 2
    assert history.imported_call not in {row["call_id"] for row in filtered.json()["items"]}


@pytest.mark.parametrize("params", [
    {"page": 0}, {"page": -1}, {"page": "invalid"}, {"page": 2147483648},
    {"page": 1, "cursor": "abc"}, {"agent_slug": ""}, {"agent_slug": "x" * 81},
])
def test_invalid_page_or_agent_filter_returns_422(history, params):
    with _browser_client(history, "owner") as client:
        assert client.get("/api/v1/call-history", params=params).status_code == 422
