"""
Hybrid Field Extractor - Uses V2 infrastructure with V1 fallback + Enhancements
Combines new components (dual extraction, document analysis) with proven field extraction
Plus enhanced patterns for commonly missed fields
"""
import logging
from services.field_extractor import FieldExtractor
from services.extractors.pdfplumber_extractor import PDFPlumberExtractor
from services.extractors.pdfminer_extractor import PDFMinerExtractor
from services.extractors.extractor_combiner import ExtractorCombiner
from services.document_analyzer import DocumentAnalyzer
from services.confidence_scorer import ConfidenceScorer
from services.validators.cross_validator import CrossValidator
from services.field_extractor_enhanced import (
    extract_row_7a_enhanced,
    extract_total_revenue_enhanced,
    extract_page1_enhanced,
    extract_part8_enhanced
)
from services.field_extractor_precise import apply_precise_fixes
from models import ExtractionResultV2, Page1FieldsV2, PartVIIIFieldsV2, PartIXFieldsV2, FieldWithConfidence
import os
import re

logger = logging.getLogger(__name__)


class HybridFieldExtractor(FieldExtractor):
    """
    Hybrid extractor that uses:
    - V2 dual extraction (pdfplumber + pdfminer.six)
    - V2 document analysis (Form 990 detection)
    - V1 field extraction (proven regex patterns)
    - V2 confidence scoring
    """

    def extract_all_fields_v2_hybrid(self, filepath: str):
        """
        Enhanced extraction using V2 infrastructure but V1 field extraction
        Best of both worlds!
        """
        filename = os.path.basename(filepath)
        logger.info(f"Starting hybrid extraction for {filename}")

        # Step 1: Dual extraction (V2)
        plumber = PDFPlumberExtractor()
        pdfminer = PDFMinerExtractor()
        combiner = ExtractorCombiner()
        extraction = combiner.extract_with_best_method(filepath, [plumber, pdfminer])
        logger.info(f"Selected extractor: {extraction.extractor_name}")

        # Step 2: Document analysis (V2)
        analyzer = DocumentAnalyzer()
        form_start_page = analyzer.detect_form_990_start(extraction.pages)
        page_metadata = [analyzer.analyze_page(p) for p in extraction.pages]
        avg_ocr_quality = sum(p.ocr_quality_score for p in page_metadata) / len(page_metadata) if page_metadata else 0.5
        logger.info(f"Form 990 starts at page {form_start_page}, OCR quality: {avg_ocr_quality:.2f}")

        # Step 3: Extract Form 990 text only
        form_990_pages = extraction.pages[form_start_page-1:]
        form_990_text = "\n".join([p['text'] for p in form_990_pages])

        # Step 4: Use existing field extraction (V1) - PROVEN TO WORK
        page1_fields = self._extract_page1_fields(form_990_text, form_990_pages)
        part8_fields = self._extract_part_viii_fields(form_990_text)
        part9_fields = self._extract_part_ix_fields(form_990_text)

        # DEBUG: Log V1 extraction results
        logger.info(f"[DEBUG V1] Total Revenue (Page 1): {page1_fields.total_revenue}")
        logger.info(f"[DEBUG V1] Grants Paid: {page1_fields.grants_and_similar_amounts_paid}")
        logger.info(f"[DEBUG V1] Net Assets: {page1_fields.net_assets_or_fund_balances}")
        logger.info(f"[DEBUG V1] Total Contributions: {page1_fields.total_contributions}")

        # Step 4.1: Apply precise fixes for accuracy issues (prevents row confusion)
        apply_precise_fixes(page1_fields, part8_fields, part9_fields, form_990_text, self)

        # DEBUG: Log after precise fixes
        logger.info(f"[DEBUG PRECISE] Total Revenue (Page 1): {page1_fields.total_revenue}")
        logger.info(f"[DEBUG PRECISE] Grants Paid: {page1_fields.grants_and_similar_amounts_paid}")
        logger.info(f"[DEBUG PRECISE] Net Assets: {page1_fields.net_assets_or_fund_balances}")

        # Step 4.5: Apply enhancements for commonly missed fields
        # Extract Part VIII section for enhanced extraction
        part8_match = re.search(
            r'Part VIII\s+Statement of Revenue(.*?)(?:Part IX\s+Statement of Functional|$)',
            form_990_text, re.DOTALL | re.IGNORECASE
        )
        part8_section = part8_match.group(1) if part8_match else form_990_text

        # Enhance Page 1 fields (for fragmented text like 2022 PDF)
        page1_enhancements = extract_page1_enhanced(form_990_text, self)
        if not page1_fields.total_contributions and page1_enhancements.get('total_contributions'):
            page1_fields.total_contributions = page1_enhancements['total_contributions']
        if not page1_fields.total_revenue and page1_enhancements.get('total_revenue'):
            page1_fields.total_revenue = page1_enhancements['total_revenue']
        if not page1_fields.total_assets and page1_enhancements.get('total_assets'):
            page1_fields.total_assets = page1_enhancements['total_assets']
        if not page1_fields.total_liabilities and page1_enhancements.get('total_liabilities'):
            page1_fields.total_liabilities = page1_enhancements['total_liabilities']
        if not page1_fields.net_assets_or_fund_balances and page1_enhancements.get('net_assets_or_fund_balances'):
            page1_fields.net_assets_or_fund_balances = page1_enhancements['net_assets_or_fund_balances']

        # Enhance Part VIII fields
        part8_enhancements = extract_part8_enhanced(part8_section, self)

        # Row 7a: Gross sales (Securities vs Other) - COMMONLY MISSING
        if not part8_fields.gross_sales_securities and part8_enhancements.get('gross_sales_securities'):
            part8_fields.gross_sales_securities = part8_enhancements['gross_sales_securities']
        if not part8_fields.gross_sales_other and part8_enhancements.get('gross_sales_other'):
            part8_fields.gross_sales_other = part8_enhancements['gross_sales_other']

        # Row 12: Total revenue - Fix if it looks like a year
        if part8_fields.total_revenue:
            clean_rev = part8_fields.total_revenue.replace(',', '').replace('.', '')
            if len(clean_rev) == 4 and (clean_rev.startswith('19') or clean_rev.startswith('20')):
                # It's a year, not revenue! Replace with enhanced extraction
                if part8_enhancements.get('total_revenue'):
                    part8_fields.total_revenue = part8_enhancements['total_revenue']
        elif part8_enhancements.get('total_revenue'):
            part8_fields.total_revenue = part8_enhancements['total_revenue']

        # Row 1h: Contributions total
        if not part8_fields.contributions_total and part8_enhancements.get('contributions_total'):
            part8_fields.contributions_total = part8_enhancements['contributions_total']

        # Row 2g: Program service revenue total
        if not part8_fields.program_service_revenue_total and part8_enhancements.get('program_service_revenue_total'):
            part8_fields.program_service_revenue_total = part8_enhancements['program_service_revenue_total']

        # DEBUG: Log after enhancements
        logger.info(f"[DEBUG ENHANCED] Total Revenue (Page 1): {page1_fields.total_revenue}")
        logger.info(f"[DEBUG ENHANCED] Grants Paid: {page1_fields.grants_and_similar_amounts_paid}")
        logger.info(f"[DEBUG ENHANCED] Net Assets: {page1_fields.net_assets_or_fund_balances}")

        # Step 5: Convert to V2 format with confidence
        def make_field_with_confidence(value, source="text_pattern"):
            """Convert V1 field to V2 format with confidence"""
            if value is None:
                return FieldWithConfidence(value=None, confidence=0.0, source="none", warnings=["Field not found"])

            # Base confidence on extraction source and OCR quality
            base_confidence = 0.85 if source == "text_pattern" else 0.75
            final_confidence = base_confidence * (0.5 + (avg_ocr_quality * 0.5))

            return FieldWithConfidence(
                value=value,
                confidence=final_confidence,
                source=source,
                warnings=[]
            )

        # DEBUG: Log V1 values before V2 conversion
        logger.info(f"[DEBUG PRE-V2] Total Revenue (Page 1): {page1_fields.total_revenue}")
        logger.info(f"[DEBUG PRE-V2] Grants Paid: {page1_fields.grants_and_similar_amounts_paid}")
        logger.info(f"[DEBUG PRE-V2] Net Assets: {page1_fields.net_assets_or_fund_balances}")
        logger.info(f"[DEBUG PRE-V2] Total Contributions: {page1_fields.total_contributions}")

        page1_v2 = Page1FieldsV2(
            employer_identification_number=make_field_with_confidence(page1_fields.employer_identification_number),
            gross_receipts=make_field_with_confidence(page1_fields.gross_receipts),
            total_contributions=make_field_with_confidence(page1_fields.total_contributions),
            total_revenue=make_field_with_confidence(page1_fields.total_revenue),
            grants_and_similar_amounts_paid=make_field_with_confidence(page1_fields.grants_and_similar_amounts_paid),
            salaries_compensation_benefits=make_field_with_confidence(page1_fields.salaries_compensation_benefits),
            professional_fundraising_fees=make_field_with_confidence(page1_fields.professional_fundraising_fees),
            total_fundraising_expenses=make_field_with_confidence(page1_fields.total_fundraising_expenses),
            total_assets=make_field_with_confidence(page1_fields.total_assets),
            total_liabilities=make_field_with_confidence(page1_fields.total_liabilities),
            net_assets_or_fund_balances=make_field_with_confidence(page1_fields.net_assets_or_fund_balances),
        )

        part8_v2 = PartVIIIFieldsV2(
            # Row 1: Contributions breakdown
            federated_campaigns=make_field_with_confidence(part8_fields.federated_campaigns),
            membership_dues=make_field_with_confidence(part8_fields.membership_dues),
            fundraising_events=make_field_with_confidence(part8_fields.fundraising_events),
            related_organizations=make_field_with_confidence(part8_fields.related_organizations),
            government_grants=make_field_with_confidence(part8_fields.government_grants),
            all_other_contributions=make_field_with_confidence(part8_fields.all_other_contributions),
            noncash_contributions=make_field_with_confidence(part8_fields.noncash_contributions),
            contributions_total=make_field_with_confidence(part8_fields.contributions_total),

            # Row 2: Program Service Revenue
            program_service_revenue_total=make_field_with_confidence(part8_fields.program_service_revenue_total),

            # Row 3: Investment Income
            investment_income=make_field_with_confidence(part8_fields.investment_income),

            # Row 4: Tax-exempt bond income
            tax_exempt_bond_income=make_field_with_confidence(part8_fields.tax_exempt_bond_income),

            # Row 5: Royalties
            royalties=make_field_with_confidence(part8_fields.royalties),

            # Row 6: Rental Income (Real Estate vs Personal Property)
            gross_rents_real=make_field_with_confidence(part8_fields.gross_rents_real),
            gross_rents_personal=make_field_with_confidence(part8_fields.gross_rents_personal),
            rental_expenses_real=make_field_with_confidence(part8_fields.rental_expenses_real),
            rental_expenses_personal=make_field_with_confidence(part8_fields.rental_expenses_personal),
            rental_income_real=make_field_with_confidence(part8_fields.rental_income_real),
            rental_income_personal=make_field_with_confidence(part8_fields.rental_income_personal),
            net_rental_income=make_field_with_confidence(part8_fields.net_rental_income),

            # Row 7: Capital Gains/Losses (Securities vs Other)
            gross_sales_securities=make_field_with_confidence(part8_fields.gross_sales_securities),
            gross_sales_other=make_field_with_confidence(part8_fields.gross_sales_other),
            cost_basis_securities=make_field_with_confidence(part8_fields.cost_basis_securities),
            cost_basis_other=make_field_with_confidence(part8_fields.cost_basis_other),
            gain_loss_securities=make_field_with_confidence(part8_fields.gain_loss_securities),
            gain_loss_other=make_field_with_confidence(part8_fields.gain_loss_other),
            net_gain_loss=make_field_with_confidence(part8_fields.net_gain_loss),

            # Row 8: Fundraising Events
            fundraising_gross_income=make_field_with_confidence(part8_fields.fundraising_gross_income),
            fundraising_8a_other=make_field_with_confidence(part8_fields.fundraising_8a_other),
            fundraising_direct_expenses=make_field_with_confidence(part8_fields.fundraising_direct_expenses),
            fundraising_net_income=make_field_with_confidence(part8_fields.fundraising_net_income),

            # Row 9: Gaming
            gaming_gross_income=make_field_with_confidence(part8_fields.gaming_gross_income),
            gaming_direct_expenses=make_field_with_confidence(part8_fields.gaming_direct_expenses),
            gaming_net_income=make_field_with_confidence(part8_fields.gaming_net_income),

            # Row 10: Inventory Sales
            inventory_gross_sales=make_field_with_confidence(part8_fields.inventory_gross_sales),
            inventory_cost_of_goods=make_field_with_confidence(part8_fields.inventory_cost_of_goods),
            inventory_net_income=make_field_with_confidence(part8_fields.inventory_net_income),

            # Row 11: Other Revenue
            other_revenue_total=make_field_with_confidence(part8_fields.other_revenue_total),

            # Row 12: Total Revenue
            total_revenue=make_field_with_confidence(part8_fields.total_revenue),
        )

        part9_v2 = PartIXFieldsV2(
            grants_domestic_organizations=make_field_with_confidence(part9_fields.grants_domestic_organizations),
            professional_fundraising_services=make_field_with_confidence(part9_fields.professional_fundraising_services),
            affiliate_payments=make_field_with_confidence(part9_fields.affiliate_payments),
            total_functional_expenses_a=make_field_with_confidence(part9_fields.total_functional_expenses_a),
            total_functional_expenses_b=make_field_with_confidence(part9_fields.total_functional_expenses_b),
            total_functional_expenses_c=make_field_with_confidence(part9_fields.total_functional_expenses_c),
            total_functional_expenses_d=make_field_with_confidence(part9_fields.total_functional_expenses_d),
            joint_costs=make_field_with_confidence(part9_fields.joint_costs),
        )

        # DEBUG: Log V2 field values
        logger.info(f"[DEBUG V2] Total Revenue (Page 1): {page1_v2.total_revenue.value}")
        logger.info(f"[DEBUG V2] Grants Paid: {page1_v2.grants_and_similar_amounts_paid.value}")
        logger.info(f"[DEBUG V2] Net Assets: {page1_v2.net_assets_or_fund_balances.value}")
        logger.info(f"[DEBUG V2] Total Contributions: {page1_v2.total_contributions.value}")

        # Step 6: Cross-validation (V2)
        validator = CrossValidator()
        page1_dict = {
            'total_contributions': page1_fields.total_contributions,
            'total_revenue': page1_fields.total_revenue,
            'total_assets': page1_fields.total_assets,
            'total_liabilities': page1_fields.total_liabilities,
            'net_assets_or_fund_balances': page1_fields.net_assets_or_fund_balances,
        }
        part8_dict = {
            'contributions_total': part8_fields.contributions_total,
            'total_revenue': part8_fields.total_revenue,
        }
        part9_dict = {
            'total_functional_expenses_a': part9_fields.total_functional_expenses_a,
            'total_functional_expenses_b': part9_fields.total_functional_expenses_b,
            'total_functional_expenses_c': part9_fields.total_functional_expenses_c,
            'total_functional_expenses_d': part9_fields.total_functional_expenses_d,
        }
        validation_result = validator.validate_all(page1_dict, part8_dict, part9_dict)

        # Step 7: Calculate confidence using V1 method but enhanced
        v1_confidence = self._calculate_confidence(page1_fields, part8_fields, part9_fields)

        # Boost confidence based on OCR quality and validation
        validation_bonus = 0.1 if validation_result.passed else 0.0
        ocr_bonus = (avg_ocr_quality - 0.5) * 0.1  # Up to +0.05 for high quality
        overall_confidence = min(1.0, v1_confidence + validation_bonus + ocr_bonus)

        # Build field confidences for detailed scoring
        scorer = ConfidenceScorer()
        field_confidences = {
            'employer_identification_number': scorer.calculate_field_confidence(
                'employer_identification_number',
                page1_fields.employer_identification_number,
                'text_pattern',
                1.0 if page1_fields.employer_identification_number else 0.0,
                1.0,
                avg_ocr_quality,
                []
            ),
            'total_revenue': scorer.calculate_field_confidence(
                'total_revenue',
                page1_fields.total_revenue,
                'text_pattern',
                1.0 if page1_fields.total_revenue else 0.0,
                validation_result.confidence_adjustment,
                avg_ocr_quality,
                []
            ),
        }

        doc_confidence = scorer.calculate_overall_confidence(field_confidences, validation_result)
        overall_confidence = doc_confidence.overall_score

        # Validation report
        validation_report = f"Validation: {len(validation_result.errors)} errors, {len(validation_result.warnings)} warnings"
        if validation_result.errors:
            validation_report += "\nErrors: " + "; ".join(validation_result.errors)
        if validation_result.warnings:
            validation_report += "\nWarnings: " + "; ".join(validation_result.warnings)

        logger.info(f"Hybrid extraction complete: confidence={overall_confidence:.2f}")

        return ExtractionResultV2(
            filename=filename,
            page1=page1_v2,
            part_viii=part8_v2,
            part_ix=part9_v2,
            overall_confidence=overall_confidence,
            pass_threshold=overall_confidence >= 0.70,
            validation_report=validation_report,
            extraction_method=extraction.extractor_name,
            form_start_page=form_start_page,
            document_type=page_metadata[0].layout_type if page_metadata else "unknown",
            raw_text=form_990_text[:5000] if len(form_990_text) > 5000 else form_990_text,
            errors=doc_confidence.critical_failures if overall_confidence < 0.70 else []
        )
