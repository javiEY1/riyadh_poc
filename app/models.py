from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field


NOT_FOUND = "NOT FOUND IN CONTRACT"


class ContractClassification(BaseModel):
    primary_type: Literal[
        "Services – Advisory",
        "Services – Operational",
        "Goods",
        "Fuel Supply",
        "Digital – SaaS",
        "Mixed",
    ] = "Mixed"
    sub_type: str = NOT_FOUND


class Party(BaseModel):
    name: str
    role: Literal["Buyer/Client", "Supplier/Vendor"]
    registered_address: str = NOT_FOUND
    jurisdiction: str = NOT_FOUND


class Jurisdictions(BaseModel):
    supplier_jurisdiction: str = NOT_FOUND
    buyer_jurisdiction: str = NOT_FOUND
    service_delivery_locations: List[str] = []


class ContractDetails(BaseModel):
    title: str = NOT_FOUND
    effective_date: str = NOT_FOUND
    term_duration: str = NOT_FOUND
    renewal_provisions: str = NOT_FOUND
    estimated_value: str = NOT_FOUND
    payment_currency: str = NOT_FOUND
    language: Literal["English", "Arabic", "Other"] = "Other"
    expiration_date: str = NOT_FOUND


class NatureOfSupply(BaseModel):
    description: str = NOT_FOUND
    verbatim_scope: str = NOT_FOUND
    scope_section_reference: str = NOT_FOUND


class ClauseExtraction(BaseModel):
    code: str
    title: str
    text: str = NOT_FOUND
    reference: str = NOT_FOUND


class ConfidenceRow(BaseModel):
    section: str
    field: str
    value: str
    confidence_score: float
    confidence_level: Literal["High", "Medium", "Low"]


class EvidenceRow(BaseModel):
    section: str
    field: str
    value: str
    snippet: str
    highlight_terms: List[str] = Field(default_factory=list)
    rationale: str = ""


class ExtractionResult(BaseModel):
    contract_classification: ContractClassification
    parties: List[Party]
    jurisdictions: Jurisdictions
    contract_details: ContractDetails
    nature_of_supply: NatureOfSupply
    clause_groups: Dict[str, List[ClauseExtraction]]
    ocr_used: bool = False
    confidence_table: List[ConfidenceRow] = Field(default_factory=list)
    evidence_table: List[EvidenceRow] = Field(default_factory=list)
    overall_confidence: float = 0.0
