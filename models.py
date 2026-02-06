"""
Pydantic models for IRS Form 990 PDF Extractor API
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class Page1Fields(BaseModel):
    """Fields extracted from Page 1 of Form 990"""
    employer_identification_number: Optional[str] = Field(None, description="Item D: EIN")
    gross_receipts: Optional[str] = Field(None, description="Item G: Gross receipts")
    total_contributions: Optional[str] = Field(None, description="Row 8 Current Year: Total contributions")
    total_revenue: Optional[str] = Field(None, description="Row 12 Current Year: Total revenue")
    grants_and_similar_amounts_paid: Optional[str] = Field(None, description="Row 13 Current Year")
    salaries_compensation_benefits: Optional[str] = Field(None, description="Row 15 Current Year")
    professional_fundraising_fees: Optional[str] = Field(None, description="Row 16a Current Year")
    total_fundraising_expenses: Optional[str] = Field(None, description="Row 16b inset")
    total_assets: Optional[str] = Field(None, description="Row 20 Current Year")
    total_liabilities: Optional[str] = Field(None, description="Row 21 Current Year")
    net_assets_or_fund_balances: Optional[str] = Field(None, description="Row 22 Current Year")


class PartVIIIFields(BaseModel):
    """Fields extracted from Part VIII - Statement of Revenue"""
    federated_campaigns: Optional[str] = Field(None, description="Row 1a")
    membership_dues: Optional[str] = Field(None, description="Row 1b")
    fundraising_events: Optional[str] = Field(None, description="Row 1c")
    related_organizations: Optional[str] = Field(None, description="Row 1d")
    government_grants: Optional[str] = Field(None, description="Row 1e")
    all_other_contributions: Optional[str] = Field(None, description="Row 1f")
    noncash_contributions: Optional[str] = Field(None, description="Row 1g")
    contributions_total: Optional[str] = Field(None, description="Row 1h Column A")
    program_service_revenue_total: Optional[str] = Field(None, description="Row 2g Column A")
    investment_income: Optional[str] = Field(None, description="Row 3 Column A")
    tax_exempt_bond_income: Optional[str] = Field(None, description="Row 4 Column A")
    royalties: Optional[str] = Field(None, description="Row 5 Column A")
    gross_rents_real: Optional[str] = Field(None, description="Row 6a Column i")
    gross_rents_personal: Optional[str] = Field(None, description="Row 6a Column ii")
    rental_expenses_real: Optional[str] = Field(None, description="Row 6b Column i")
    rental_expenses_personal: Optional[str] = Field(None, description="Row 6b Column ii")
    rental_income_real: Optional[str] = Field(None, description="Row 6c Column i")
    rental_income_personal: Optional[str] = Field(None, description="Row 6c Column ii")
    net_rental_income: Optional[str] = Field(None, description="Row 6d Column A")
    gross_sales_securities: Optional[str] = Field(None, description="Row 7a Column i")
    gross_sales_other: Optional[str] = Field(None, description="Row 7a Column ii")
    cost_basis_securities: Optional[str] = Field(None, description="Row 7b Column i")
    cost_basis_other: Optional[str] = Field(None, description="Row 7b Column ii")
    gain_loss_securities: Optional[str] = Field(None, description="Row 7c Column i")
    gain_loss_other: Optional[str] = Field(None, description="Row 7c Column ii")
    net_gain_loss: Optional[str] = Field(None, description="Row 7d Column A")
    fundraising_gross_income: Optional[str] = Field(None, description="Row 8a inset")
    fundraising_8a_other: Optional[str] = Field(None, description="Row 8a Column ii")
    fundraising_direct_expenses: Optional[str] = Field(None, description="Row 8b Column ii")
    fundraising_net_income: Optional[str] = Field(None, description="Row 8c Column A")
    gaming_gross_income: Optional[str] = Field(None, description="Row 9a Column ii")
    gaming_direct_expenses: Optional[str] = Field(None, description="Row 9b Column ii")
    gaming_net_income: Optional[str] = Field(None, description="Row 9c Column A")
    inventory_gross_sales: Optional[str] = Field(None, description="Row 10a Column ii")
    inventory_cost_of_goods: Optional[str] = Field(None, description="Row 10b Column ii")
    inventory_net_income: Optional[str] = Field(None, description="Row 10c Column A")
    other_revenue_total: Optional[str] = Field(None, description="Row 11e Column A")
    total_revenue: Optional[str] = Field(None, description="Row 12 Column A")


class PartIXFields(BaseModel):
    """Fields extracted from Part IX - Statement of Functional Expenses"""
    grants_domestic_organizations: Optional[str] = Field(None, description="Row 1 Column A")
    professional_fundraising_services: Optional[str] = Field(None, description="Row 11e Column A")
    affiliate_payments: Optional[str] = Field(None, description="Row 21 Column A")
    total_functional_expenses_a: Optional[str] = Field(None, description="Row 25 Column A")
    total_functional_expenses_b: Optional[str] = Field(None, description="Row 25 Column B")
    total_functional_expenses_c: Optional[str] = Field(None, description="Row 25 Column C")
    total_functional_expenses_d: Optional[str] = Field(None, description="Row 25 Column D")
    joint_costs: Optional[str] = Field(None, description="Row 26 Column A")


class ExtractionResult(BaseModel):
    """Complete extraction result from a Form 990 PDF"""
    filename: str
    extraction_date: datetime = Field(default_factory=datetime.now)
    page1: Page1Fields = Field(default_factory=Page1Fields)
    part_viii: PartVIIIFields = Field(default_factory=PartVIIIFields)
    part_ix: PartIXFields = Field(default_factory=PartIXFields)
    raw_text: Optional[str] = None
    extraction_method: str = "pdfplumber"
    confidence_score: Optional[float] = None
    errors: List[str] = Field(default_factory=list)


class ExtractionResponse(BaseModel):
    """API response for extraction endpoint"""
    success: bool
    message: str
    data: Optional[ExtractionResult] = None


class HealthResponse(BaseModel):
    """API health check response"""
    status: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.now)


# V2 Models with Confidence Scoring

class FieldWithConfidence(BaseModel):
    """Field value with confidence score and metadata"""
    value: Optional[str]
    confidence: float = Field(description="Confidence score 0.0-1.0")
    warnings: List[str] = Field(default_factory=list)
    source: str = Field(default="unknown", description="Extraction source: table, text_pattern, ocr")


class Page1FieldsV2(BaseModel):
    """Page 1 fields with confidence scores"""
    employer_identification_number: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    gross_receipts: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    total_contributions: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    total_revenue: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    grants_and_similar_amounts_paid: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    salaries_compensation_benefits: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    professional_fundraising_fees: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    total_fundraising_expenses: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    total_assets: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    total_liabilities: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    net_assets_or_fund_balances: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))


class PartVIIIFieldsV2(BaseModel):
    """Part VIII fields with confidence scores"""
    # Row 1: Contributions
    federated_campaigns: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    membership_dues: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    fundraising_events: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    related_organizations: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    government_grants: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    all_other_contributions: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    noncash_contributions: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    contributions_total: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 2: Program Service Revenue
    program_service_revenue_total: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 3: Investment Income
    investment_income: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 4: Tax-exempt bond income
    tax_exempt_bond_income: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 5: Royalties
    royalties: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 6: Rental Income
    gross_rents_real: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    gross_rents_personal: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    rental_expenses_real: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    rental_expenses_personal: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    rental_income_real: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    rental_income_personal: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    net_rental_income: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 7: Capital Gains/Losses
    gross_sales_securities: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    gross_sales_other: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    cost_basis_securities: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    cost_basis_other: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    gain_loss_securities: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    gain_loss_other: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    net_gain_loss: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 8: Fundraising Events
    fundraising_gross_income: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    fundraising_8a_other: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    fundraising_direct_expenses: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    fundraising_net_income: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 9: Gaming
    gaming_gross_income: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    gaming_direct_expenses: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    gaming_net_income: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 10: Inventory Sales
    inventory_gross_sales: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    inventory_cost_of_goods: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    inventory_net_income: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 11: Other Revenue
    other_revenue_total: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))

    # Row 12: Total Revenue
    total_revenue: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))


class PartIXFieldsV2(BaseModel):
    """Part IX fields with confidence scores"""
    grants_domestic_organizations: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    professional_fundraising_services: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    affiliate_payments: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    total_functional_expenses_a: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    total_functional_expenses_b: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    total_functional_expenses_c: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    total_functional_expenses_d: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))
    joint_costs: FieldWithConfidence = Field(default_factory=lambda: FieldWithConfidence(value=None, confidence=0.0, source="none"))


class ExtractionResultV2(BaseModel):
    """Enhanced extraction result with confidence scoring"""
    filename: str
    extraction_date: datetime = Field(default_factory=datetime.now)
    page1: Page1FieldsV2 = Field(default_factory=Page1FieldsV2)
    part_viii: PartVIIIFieldsV2 = Field(default_factory=PartVIIIFieldsV2)
    part_ix: PartIXFieldsV2 = Field(default_factory=PartIXFieldsV2)

    # Enhanced metadata
    overall_confidence: float = Field(description="Overall extraction confidence 0.0-1.0")
    pass_threshold: bool = Field(description="Whether confidence meets minimum threshold")
    validation_report: str = Field(default="", description="Cross-validation results")
    extraction_method: str = Field(default="pdfplumber", description="PDF extractor used")
    form_start_page: int = Field(default=1, description="Page where Form 990 starts")
    document_type: str = Field(default="unknown", description="Document classification")

    # Optional fields
    raw_text: Optional[str] = None
    errors: List[str] = Field(default_factory=list)


class ExtractionResponseV2(BaseModel):
    """API response for v2 extraction endpoint"""
    success: bool
    message: str
    data: Optional[ExtractionResultV2] = None
    confidence: Optional[float] = None
