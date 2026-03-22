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


def test_template_upload_list_and_match() -> None:
    payload = b"""
    MASTER SERVICE AGREEMENT TEMPLATE
    Between [BUYER NAME] (Buyer) and [SUPPLIER NAME] (Supplier).
    Effective date: [DATE].
    Scope of Services: Advisory and consulting services in Saudi Arabia.
    Payment terms: Fees in SAR. Invoices monthly.
    Governing law: Kingdom of Saudi Arabia.
    """
    upload_res = client.post(
        "/templates",
        files={"file": ("template.txt", payload, "text/plain")},
        data={"name": "Advisory Template"},
    )
    assert upload_res.status_code == 200
    tpl_data = upload_res.json()
    assert "template_id" in tpl_data
    assert tpl_data["template_name"] == "Advisory Template"

    list_res = client.get("/templates")
    assert list_res.status_code == 200
    tpls = list_res.json()
    assert any(t["name"] == "Advisory Template" for t in tpls)

    detail_res = client.get(f"/templates/{tpl_data['template_id']}")
    assert detail_res.status_code == 200
    assert "result" in detail_res.json()

    contract = b"""
    SERVICE AGREEMENT
    Between Riyadh Air LLC (Buyer) and Acme Consulting Ltd (Supplier).
    Effective date: 01 Jan 2026.
    Scope of Services: Advisory and consulting services in Saudi Arabia.
    Payment terms: Fees in SAR. Invoices monthly.
    Governing law: Kingdom of Saudi Arabia.
    """
    extract_res = client.post("/extract", files={"file": ("contract.txt", contract, "text/plain")})
    assert extract_res.status_code == 200
    extracted = extract_res.json()

    match_res = client.post("/templates/match", json=extracted)
    assert match_res.status_code == 200
    matches = match_res.json()
    assert len(matches) >= 1
    assert "similarity" in matches[0]
    assert "template_name" in matches[0]
    assert matches[0]["similarity"] > 0

    compare_res = client.post(
        f"/templates/{tpl_data['template_id']}/compare",
        json=extracted,
    )
    assert compare_res.status_code == 200
    diff = compare_res.json()
    assert "overall_similarity" in diff
    assert "fields" in diff
    assert len(diff["fields"]) > 0
    assert diff["template_name"] == "Advisory Template"
    first_field = diff["fields"][0]
    assert "contract_value" in first_field
    assert "template_value" in first_field
    assert "similarity" in first_field
    assert "status" in first_field

    del_res = client.delete(f"/templates/{tpl_data['template_id']}")
    assert del_res.status_code == 200
    assert del_res.json() == {"deleted": tpl_data["template_id"]}

    assert client.get(f"/templates/{tpl_data['template_id']}").status_code == 404
    assert client.delete(f"/templates/{tpl_data['template_id']}").status_code == 404
