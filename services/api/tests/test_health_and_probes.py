"""Health Endpoints and Diagnostics Test Suite

Mandatory Tests:
11. Health endpoint behaves correctly (liveness and readiness checks)
"""

from fastapi.testclient import TestClient


def test_liveness_endpoint_behaves_correctly(client: TestClient) -> None:
    """Requirement 13.11: GET /health/live returns process uptime and ok status."""
    res = client.get("/health/live")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "version" in data


def test_readiness_endpoint_behaves_correctly(client: TestClient) -> None:
    """Requirement 13.11: GET /health/ready returns database health."""
    res = client.get("/health/ready")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["database"] == "healthy"


def test_me_endpoint_returns_user_profile_and_memberships(client: TestClient) -> None:
    """Verifies that GET /api/v1/me returns verified profile and active memberships."""
    res = client.get("/api/v1/me", headers={"Authorization": "Bearer dev-token-neeraj"})
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["email"] == "neeraj.kulkarni@example.com"
    assert len(data["roles"]) >= 1
    assert data["roles"][0]["role"] == "RESIDENT"
    assert len(data["memberships"]) >= 1
    assert data["memberships"][0]["flat_number"] == "1203"
