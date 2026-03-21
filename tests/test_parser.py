from app.models import NOT_FOUND
from app.parser import parse_contract


SAMPLE_CONTRACT = """
MASTER SERVICE AGREEMENT
This Master Service Agreement is made effective date: 01 January 2026.
Between Alpha Aviation LLC (Buyer) and Beta Tech Solutions Ltd (Supplier).

1. Scope of Services
Supplier shall provide software subscription services, support, and implementation deliverables.
Services will be performed in United Arab Emirates and Saudi Arabia.

2. Fees and Payment Terms
Buyer shall pay Supplier USD 120,000 annually.
Invoices shall be issued monthly in USD.

3. Tax
"Taxes" means all applicable taxes including VAT.
The Buyer may withhold tax where required by law.

4. Intellectual Property
Supplier grants Buyer a non-exclusive software licence.

5. Governing Law and Dispute Resolution
This Agreement is governed by the laws of United Arab Emirates.
Disputes shall be resolved by arbitration.

6. Term and Renewal
The term is 24 months from the effective date and auto-renews for 12 months unless terminated.
"""


def test_parser_returns_required_sections() -> None:
    result = parse_contract(SAMPLE_CONTRACT)
    assert result.contract_details.title != NOT_FOUND
    assert result.contract_classification.primary_type in {
        "Digital – SaaS",
        "Mixed",
        "Services – Operational",
        "Services – Advisory",
        "Goods",
        "Fuel Supply",
    }
    assert result.clause_groups["Tax-related clauses"][0].code == "TAX001"
    assert result.clause_groups["Governing and dispute"][0].code == "GOV001"
    assert len(result.parties) >= 1


def test_supplier_party_is_entity_name() -> None:
    contract = """
    CONSULTING AGREEMENT
    This Agreement is entered into by and between Alpha Holdings LLC (the Buyer)
    and Beta Advisory Services Ltd (the Supplier), effective date: 05 March 2026.
    Supplier shall provide legal consulting services.
    """
    result = parse_contract(contract)
    suppliers = [p for p in result.parties if p.role == "Supplier/Vendor"]
    assert suppliers
    assert suppliers[0].name == "Beta Advisory Services Ltd"
    assert "agreement is entered" not in suppliers[0].name.lower()
