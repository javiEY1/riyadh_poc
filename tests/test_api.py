from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_extract_from_text_upload() -> None:
    payload = b"""
    Service Agreement
    Effective date: 10 Feb 2026
    Between Orion LLC (Buyer) and Nova Systems Ltd (Supplier)
    Scope of Services: Supplier provides software services in UAE.
    Payment terms: Fees shall be paid in USD. Invoices are monthly.
    Governing law: United Arab Emirates.
    """
    response = client.post("/extract", files={"file": ("contract.txt", payload, "text/plain")})
    assert response.status_code == 200
    data = response.json()
    assert "contract_details" in data
    assert "clause_groups" in data
    assert data["contract_details"]["effective_date"] != "NOT FOUND IN CONTRACT"
