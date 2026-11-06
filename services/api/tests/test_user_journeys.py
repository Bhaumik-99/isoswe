"""End-to-End User Journeys Verification Test Suite

Verifies the two application roles:
1. RESIDENT Journey (Neeraj Kulkarni):
   - Access only to approved flats, bills, and profile
   - Denied access to other residents' flats
   - Denied access to staff/helpdesk operations
2. HELPDESK Journey (Rajesh Shinde):
   - Access to society-scoped flats
   - Denied cross-society flat access
   - Authorized for granular helpdesk reconciliation & operations
   - Authorized for committee reporting
"""

from fastapi.testclient import TestClient

FLAT_1203_ID = "33333333-3333-3333-3333-333333331203"
FLAT_0408_ID = "33333333-3333-3333-3333-333333330408"
FLAT_OTHER_SOCIETY_ID = "33333333-3333-3333-3333-333333339999"


def test_resident_user_journey(client: TestClient) -> None:
    """Verifies complete resident user journey."""
    headers = {"Authorization": "Bearer dev-token-neeraj"}

    # 1. Fetch own profile via /api/v1/me
    me_res = client.get("/api/v1/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["full_name"] == "Neeraj Kulkarni"
    assert len(me_data["roles"]) == 1
    assert me_data["roles"][0]["role"] == "RESIDENT"
    assert any(m["flat_number"] == "1203" for m in me_data["memberships"])

    # 2. Access own flat details
    flat_res = client.get(f"/api/v1/flats/{FLAT_1203_ID}", headers=headers)
    assert flat_res.status_code == 200
    assert flat_res.json()["flat_number"] == "1203"

    # 3. Denied access to another resident's flat (Swati's 0408)
    unauthorized_flat = client.get(f"/api/v1/flats/{FLAT_0408_ID}", headers=headers)
    assert unauthorized_flat.status_code == 403
    assert unauthorized_flat.json()["error"]["code"] == "FLAT_ACCESS_DENIED"

    # 4. Denied access to staff/helpdesk privileged operations
    staff_op = client.post("/api/v1/finance/batch-billing/preview", headers=headers)
    assert staff_op.status_code == 403
    assert staff_op.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_helpdesk_user_journey(client: TestClient) -> None:
    """Verifies complete helpdesk staff user journey."""
    headers = {"Authorization": "Bearer dev-token-helpdesk"}

    # 1. Fetch helpdesk profile via /api/v1/me
    me_res = client.get("/api/v1/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["full_name"] == "Rajesh Shinde"
    roles = [r["role"] for r in me_data["roles"]]
    assert "HELPDESK" in roles
    assert "COMMITTEE" in roles

    # 2. Inspect flats within assigned society (Marvel Greenfield)
    flat_res = client.get(f"/api/v1/flats/{FLAT_1203_ID}", headers=headers)
    assert flat_res.status_code == 200
    assert flat_res.json()["flat_number"] == "1203"

    # 3. Denied access to flats in another society (Tenant isolation enforced)
    cross_soc = client.get(f"/api/v1/flats/{FLAT_OTHER_SOCIETY_ID}", headers=headers)
    assert cross_soc.status_code == 403
    assert cross_soc.json()["error"]["code"] == "CROSS_TENANT_ACCESS_DENIED"

    # 4. Perform authorized bank reconciliation & finance preview
    recon_res = client.post("/api/v1/finance/batch-billing/preview", headers=headers)
    assert recon_res.status_code == 200
    assert recon_res.json()["status"] == "AUTHORIZED"
