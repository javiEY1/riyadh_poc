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
    assert "confidence_table" in data
    assert "evidence_table" in data
    assert "overall_confidence" in data
    assert data["contract_details"]["effective_date"] != "NOT FOUND IN CONTRACT"


def test_export_json_and_excel() -> None:
    payload = b"""
    Service Agreement
    Effective date: 10 Feb 2026
    Between Orion LLC (Buyer) and Nova Systems Ltd (Supplier)
    Scope of Services: Supplier provides software services in UAE.
    Payment terms: Fees shall be paid in USD. Invoices are monthly.
    Governing law: United Arab Emirates.
    """
    extract_response = client.post("/extract", files={"file": ("contract.txt", payload, "text/plain")})
    assert extract_response.status_code == 200
    extracted = extract_response.json()

    json_export = client.post("/export?format=json", json=extracted)
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")
    assert b"confidence_table" in json_export.content

    excel_export = client.post("/export?format=excel", json=extracted)
    assert excel_export.status_code == 200
    assert excel_export.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert excel_export.content[:2] == b"PK"
