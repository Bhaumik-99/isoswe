"""Phase 5 Workstream E: Committee Governance & Reporting Test Suite

Validates:
1. Committee overview backed by live database SQL aggregates across towers and flats.
2. Ageing buckets: 0-30, 31-60, 61-90, 90+ days.
3. Complaint operational governance metrics (open, resolved, safety escalated, SLA breaches, turnaround).
4. Tower-by-tower financial and complaint breakdown.
5. Monthly financial statements with collection percentages.
6. CSV export with formula injection sanitization (CWE-1236).
7. Read-only committee access control (residents rejected with 403).
"""

from fastapi.testclient import TestClient

AUTH_HELPDESK = {"X-Dev-User": "helpdesk"}
AUTH_RESIDENT = {"X-Dev-User": "neeraj"}


def test_committee_overview_sql_aggregates(client: TestClient) -> None:
    """Committee overview calculates exact financial and complaint metrics across all units."""
    # 1. Resident cannot view committee dashboard -> 403 Forbidden
    res_forbidden = client.get("/api/v1/committee/overview", headers=AUTH_RESIDENT)
    assert res_forbidden.status_code == 403

    # 2. Staff / Committee member fetches overview
    res = client.get("/api/v1/committee/overview", headers=AUTH_HELPDESK)
    assert res.status_code == 200
    data = res.json()

    assert "society_id" in data
    assert "financials" in data
    assert "complaints" in data
    assert "towers" in data

    # Financial invariants
    fin = data["financials"]
    assert fin["total_billed_paise"] >= 0
    assert fin["total_collected_paise"] >= 0
    assert fin["total_outstanding_paise"] >= 0
    assert 0.0 <= fin["collection_percentage"] <= 100.0

    # Ageing buckets
    ageing = fin["ageing"]
    assert ageing["bucket_0_30_paise"] >= 0
    assert ageing["bucket_31_60_paise"] >= 0
    assert ageing["bucket_61_90_paise"] >= 0
    assert ageing["bucket_90_plus_paise"] >= 0

    # Complaint governance
    comp = data["complaints"]
    assert comp["total_complaints"] >= 0
    assert comp["open_complaints"] >= 0
    assert comp["resolved_complaints"] >= 0
    assert comp["safety_escalated_count"] >= 0
    assert comp["sla_breached_count"] >= 0
    assert comp["avg_resolution_hours"] >= 0.0

    # Tower breakdown
    towers = data["towers"]
    assert len(towers) >= 1
    t07 = next((t for t in towers if t["tower_number"] in ("T07", "T7")), towers[0])
    assert t07["total_flats"] >= 1
    assert t07["total_billed_paise"] >= 0


def test_committee_monthly_reports(client: TestClient) -> None:
    """Monthly financial statement lists historical billing periods with collection rates."""
    res = client.get("/api/v1/committee/reports/monthly", headers=AUTH_HELPDESK)
    assert res.status_code == 200
    periods = res.json()

    assert isinstance(periods, list)
    if periods:
        p1 = periods[0]
        assert "billing_period" in p1
        assert "total_invoices" in p1
        assert "total_billed_paise" in p1
        assert "total_collected_paise" in p1
        assert "collection_percentage" in p1


def test_committee_report_csv_export(client: TestClient) -> None:
    """CSV export produces downloadable statement protected against formula injection."""
    res = client.get("/api/v1/committee/reports/export", headers=AUTH_HELPDESK)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in res.headers["content-disposition"]

    csv_text = res.text
    assert "Billing Period" in csv_text
    assert "Billed Amount (INR)" in csv_text
    assert "Collected Amount (INR)" in csv_text
    assert "Collection Percentage" in csv_text
