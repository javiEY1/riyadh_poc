from fastapi.testclient import TestClient

from app.database import init_db_sync
from app.main import app


init_db_sync()
client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_get() -> None:
    response = client.get("/settings")
    assert response.status_code == 200
    assert "llm_enabled" in response.json()


def test_settings_post_empty_key() -> None:
    response = client.post("/settings", json={"openai_api_key": ""})
    assert response.status_code == 200
    assert response.json()["llm_enabled"] is False


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
    assert "document_id" in data
    assert "extraction_method" in data
    assert data["extraction_method"] == "regex"
    assert data["contract_details"]["effective_date"] != "NOT FOUND IN CONTRACT"


def test_documents_list() -> None:
    response = client.get("/documents")
    assert response.status_code == 200
    docs = response.json()
    assert isinstance(docs, list)
    assert len(docs) >= 1
    assert "filename" in docs[0]
    assert "extraction_method" in docs[0]


def test_documents_get_by_id() -> None:
    list_response = client.get("/documents")
    docs = list_response.json()
    assert len(docs) >= 1

    doc_id = docs[0]["id"]
    response = client.get(f"/documents/{doc_id}")
    assert response.status_code == 200
    doc = response.json()
    assert "result" in doc
    assert "confidence_table" in doc["result"]


def test_documents_not_found() -> None:
    response = client.get("/documents/999999")
    assert response.status_code == 404


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
