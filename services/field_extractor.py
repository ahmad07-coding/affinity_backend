"""
Field Extractor Service - Fixed for Accurate Form 990 Extraction
Properly distinguishes between row labels, OCR noise, and actual values
Returns null for empty fields, never returns row numbers as values
"""
import re
from typing import Optional, Dict, Any, List
import logging

from models import Page1Fields, PartVIIIFields, PartIXFields, ExtractionResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FieldExtractor:
    """
    Fixed field extractor for IRS Form 990
    - Correctly extracts EIN and Gross Receipts from OCR text
    - Returns null for empty form fields (not row numbers)
    - Validates amounts to ensure they're real values
    """
    
    # Minimum length for a valid amount (to filter out OCR noise)
    MIN_AMOUNT_LENGTH = 4
    
    def extract_all_fields(self, full_text: str, pages_data: List[dict], filename: str) -> ExtractionResult:
        """Extract all fields from the combined text"""
        errors = []
        
        logger.info(f"Starting extraction for {filename}")
        logger.debug(f"Full text length: {len(full_text)} chars")
        
        # Extract Page 1 fields
        try:
            page1 = self._extract_page1_fields(full_text, pages_data)
        except Exception as e:
            logger.error(f"Error extracting Page 1 fields: {e}")
            page1 = Page1Fields()
            errors.append(f"Page 1 extraction error: {str(e)}")
        
        # Extract Part VIII fields
        try:
            part_viii = self._extract_part_viii_fields(full_text)
        except Exception as e:
            logger.error(f"Error extracting Part VIII fields: {e}")
            part_viii = PartVIIIFields()
            errors.append(f"Part VIII extraction error: {str(e)}")
        
        # Extract Part IX fields
        try:
            part_ix = self._extract_part_ix_fields(full_text)
        except Exception as e:
            logger.error(f"Error extracting Part IX fields: {e}")
            part_ix = PartIXFields()
            errors.append(f"Part IX extraction error: {str(e)}")
        
        # Calculate confidence
        confidence = self._calculate_confidence(page1, part_viii, part_ix)
        
        return ExtractionResult(
            filename=filename,
            page1=page1,
            part_viii=part_viii,
            part_ix=part_ix,
            raw_text=full_text[:5000] if len(full_text) > 5000 else full_text,
            confidence_score=confidence,
            errors=errors
        )
    
    def _extract_page1_fields(self, text: str, pages_data: List[dict]) -> Page1Fields:
        """Extract fields from Page 1 - Header and Part I Summary"""
        fields = Page1Fields()
        
        # === HEADER FIELDS ===
        
        # Extract EIN (Item D) - look for "39-0806251" format near "Address change" or "Employer identification"
        fields.employer_identification_number = self._extract_ein(text)
        
        # Extract Gross Receipts (Item G)
        fields.gross_receipts = self._extract_gross_receipts(text)
        
        # === PART I SUMMARY FIELDS (Rows 8-22) ===
        # These are in the "Current Year" or "End of Year" columns
        # Based on OCR analysis, these fields are currently EMPTY in the test PDF
        # We need to look for actual monetary amounts, not row numbers
        
        # For rows 8-19 (Revenue/Expenses section - Current Year column)
        fields.total_contributions = self._extract_current_year_value(text, "8", "Contributions and grants")
        fields.total_revenue = self._extract_current_year_value(text, "12", "Total revenue")
        fields.grants_and_similar_amounts_paid = self._extract_current_year_value(text, "13", "Grants and similar amounts paid")
        fields.salaries_compensation_benefits = self._extract_current_year_value(text, "15", "Salaries.*compensation.*employee benefits")
        fields.professional_fundraising_fees = self._extract_current_year_value(text, "16a", "Professional fundraising fees")
        fields.total_fundraising_expenses = self._extract_inset_value(text, "16b", "Total fundraising expenses")
        
        # For rows 20-22 (Assets section - End of Year column)
        fields.total_assets = self._extract_end_of_year_value(text, "20", "Total assets")
        fields.total_liabilities = self._extract_end_of_year_value(text, "21", "Total liabilities")
        fields.net_assets_or_fund_balances = self._extract_end_of_year_value(text, "22", "Net assets or fund balances")
        
        return fields
    
    def _extract_ein(self, text: str) -> Optional[str]:
        """
        Extract EIN (Employer Identification Number)
        Format: XX-XXXXXXX (e.g., 39-0806251)
        """
        # Pattern 1: Standard EIN format with hyphen
        ein_matches = re.findall(r'\b(\d{2}-\d{7})\b', text)
        if ein_matches:
            logger.info(f"Found EIN: {ein_matches[0]}")
            return ein_matches[0]
        
        # Pattern 2: EIN without hyphen (9 consecutive digits, not part of larger number)
        # Look near "Address change" which is where EIN typically appears in OCR
        ein_section = re.search(r'Address change[^\n]*(\d{9})', text, re.IGNORECASE)
        if ein_section:
            digits = ein_section.group(1)
            formatted = f"{digits[:2]}-{digits[2:]}"
            logger.info(f"Found EIN (no hyphen): {formatted}")
            return formatted
        
        return None
    
    def _extract_gross_receipts(self, text: str) -> Optional[str]:
        """
        Extract Gross Receipts (Item G)
        With layout=True, the $ and amount may be separated by whitespace.
        """
        # Pattern 1: "Gross receipts $" followed by amount (flexible whitespace)
        match = re.search(r'[Gg]ross\s+receipts\s*\$\s*([\d,]+(?:\.\d{2})?)', text)
        if match:
            amount = match.group(1)
            if self._is_valid_monetary_amount(amount):
                logger.info(f"Found Gross Receipts: {amount}")
                return amount

        # Pattern 2: "Gross receipts" anywhere on line with $ and amount
        match = re.search(r'[Gg]ross\s+receipts[^\n]*?\$\s*([\d,]+(?:\.\d{2})?)', text)
        if match:
            amount = match.group(1)
            if self._is_valid_monetary_amount(amount):
                logger.info(f"Found Gross Receipts (alt): {amount}")
                return amount

        # Pattern 3: Fallback - find the last large number on the "Gross receipts" line
        match = re.search(r'[Gg]ross\s+receipts[^\n]*', text)
        if match:
            line = match.group(0)
            amounts = re.findall(r'([\d,]{4,}(?:\.\d{2})?)', line)
            valid = [a for a in amounts if self._is_valid_monetary_amount(a)]
            if valid:
                logger.info(f"Found Gross Receipts (fallback): {valid[-1]}")
                return valid[-1]

        return None
    
    def _extract_current_year_value(self, text: str, row_num: str, description: str) -> Optional[str]:
        """
        Extract value from Current Year column for a specific row.
        Each row looks like: label ... prior_year_value current_year_value
        We need the LAST valid monetary amount on the line.
        """
        line_pattern = rf'{row_num}\s+{description}[^\n]*'
        match = re.search(line_pattern, text, re.IGNORECASE)
        if match:
            valid_amounts = self._find_amounts_in_text(match.group(0))
            if valid_amounts:
                amount = valid_amounts[-1]
                logger.info(f"Found Row {row_num} Current Year: {amount}")
                return amount

        return None
    
    def _extract_inset_value(self, text: str, row_num: str, description: str) -> Optional[str]:
        """Extract value from an inset field (like 16b Total fundraising expenses)"""
        # Strategy 1: Match line with row number + description
        line_pattern = rf'{row_num}\s+{description}[^\n]*'
        match = re.search(line_pattern, text, re.IGNORECASE)
        if match:
            valid = self._find_amounts_in_text(match.group(0))
            if valid:
                return valid[-1]

        # Strategy 2: Match by description alone (no row number)
        desc_pattern = rf'{description}[^\n]*'
        match = re.search(desc_pattern, text, re.IGNORECASE)
        if match:
            valid = self._find_amounts_in_text(match.group(0))
            if valid:
                return valid[-1]

        return None
    
    def _extract_end_of_year_value(self, text: str, row_num: str, description: str) -> Optional[str]:
        """
        Extract value from End of Year column for rows 20-22
        Same logic as current year but for assets section
        """
        return self._extract_current_year_value(text, row_num, description)
    
    def _is_valid_monetary_amount(self, value: str) -> bool:
        """
        Check if a value is a valid monetary amount
        Allows '0' or '0.00' but filters out row codes like '1', '25'
        """
        if not value:
            return False
            
        # Clean value
        clean = value.replace(',', '').replace('.', '')
        
        # Explicitly allow zero
        if clean == '0' or value == '0.00':
            return True
            
        if not clean.isdigit():
            return False
            
        # Filter small integers that look like row codes (1-99)
        # Real amounts are usually larger or have decimals (though decimals are removed in 'clean')
        # If length is small, ensure it's not a row code
        if len(clean) < self.MIN_AMOUNT_LENGTH:
            # If it's a small number, assume it's a row code unless context proves otherwise
            return False
            
        try:
            num = int(clean)
            if num < 100: return False
        except ValueError:
            return False
            
        return True
    
    # Regex that captures normal amounts (4+ digit chars) AND standalone zeros
    AMOUNT_RE = r'([\d,]{4,}(?:\.\d{2})?|\b0(?:\.00)?\b)'

    # How many lines ahead to check when amounts aren't on the matched line
    LOOKAHEAD_LINES = 3

    def _normalize_spaces(self, text: str) -> str:
        """Collapse multiple spaces into single spaces for consistent matching."""
        return re.sub(r'  +', ' ', text)

    def _find_amounts_in_text(self, text_block: str) -> List[str]:
        """Find all valid monetary amounts in a text block (handles zeros too)."""
        amounts = re.findall(self.AMOUNT_RE, text_block)
        return [a for a in amounts if self._is_valid_monetary_amount(a)]

    def _get_subsequent_lines(self, text: str, match_end: int, count: int = 3) -> List[str]:
        """Get the next N lines after a regex match position."""
        remaining = text[match_end:]
        lines = []
        for m in re.finditer(r'\n([^\n]*)', remaining):
            lines.append(m.group(1))
            if len(lines) >= count:
                break
        return lines

    def _find_amounts_with_lookahead(self, text: str, match: re.Match, take: str = "first") -> Optional[str]:
        """Try to find amounts on matched line, then fall back to subsequent lines.
        take='first' returns first valid amount, take='last' returns last."""
        valid = self._find_amounts_in_text(match.group(0))
        if valid:
            return valid[0] if take == "first" else valid[-1]
        # Fallback: check subsequent lines
        for next_line in self._get_subsequent_lines(text, match.end(), self.LOOKAHEAD_LINES):
            valid = self._find_amounts_in_text(next_line)
            if valid:
                return valid[0] if take == "first" else valid[-1]
        return None

    def _extract_column_values(self, text: str, pattern: str) -> List[str]:
        """Extract all valid amounts from matching line (+ subsequent lines), for rows with multiple columns."""
        line_pattern = rf'{pattern}[^\n]*'
        match = re.search(line_pattern, text, re.IGNORECASE)
        if match:
            amounts = self._find_amounts_in_text(match.group(0))
            if amounts:
                return amounts
            # Fallback: check subsequent lines
            for next_line in self._get_subsequent_lines(text, match.end(), self.LOOKAHEAD_LINES):
                amounts = self._find_amounts_in_text(next_line)
                if amounts:
                    return amounts
        return []

    def _extract_part_viii_fields(self, text: str) -> PartVIIIFields:
        """Extract Part VIII Revenue Statement fields"""
        fields = PartVIIIFields()

        # Find Part VIII section using specific header to avoid matching
        # "Part VIII" references in row descriptions on other pages
        part_match = re.search(
            r'Part VIII\s+Statement of Revenue(.*?)(?:Part IX\s+Statement of Functional|$)',
            text, re.DOTALL | re.IGNORECASE
        )
        section = self._normalize_spaces(part_match.group(1) if part_match else text)

        # Helper to try multiple patterns for Part VIII fields.
        # Uses word boundaries to avoid e.g. "3" matching "13".
        # Column A (Total revenue) is the FIRST column in Part VIII.
        def extract_p8(row_code, label):
            # Pattern 1: row code + label (e.g. "1a Federated campaigns")
            val = self._find_first_valid_amount(section, rf"\b{row_code}\b.*{label}")
            if val: return val

            # Pattern 2: label followed by row code and amount
            val = self._find_first_valid_amount(section, rf"{label}.*\b{row_code}\b")
            if val: return val

            # Pattern 3: label only (for lines where row code is separated)
            if label:
                val = self._find_first_valid_amount(section, label)
                return val
            return None

        # Helper for rows with Column i / Column ii sub-columns
        def extract_p8_columns(row_code, label):
            vals = self._extract_column_values(section, rf"\b{row_code}\b.*{label}")
            if not vals:
                vals = self._extract_column_values(section, rf"{label}.*\b{row_code}\b")
            if not vals and label:
                vals = self._extract_column_values(section, label)
            return vals

        # === Row 1: Contributions ===
        fields.federated_campaigns = extract_p8("1a", "Federated campaigns")
        fields.membership_dues = extract_p8("1b", "Membership dues")
        fields.fundraising_events = extract_p8("1c", "Fundraising events")
        fields.related_organizations = extract_p8("1d", "Related organizations")
        fields.government_grants = extract_p8("1e", "Government grants")
        fields.all_other_contributions = extract_p8("1f", "All other contributions")
        fields.noncash_contributions = extract_p8("1g", "Noncash contributions")

        # contributions_total: line looks like "h Total. Add lines 1a-1f ... 43,437,498"
        fields.contributions_total = (
            self._find_first_valid_amount(section, r"Total.*Add lines 1a") or
            extract_p8("1h", r"Total.*lines 1a")
        )

        # === Row 2g: Program service revenue total ===
        # Text may say "Total. Add lines 2a-2f" or "Total program service revenue"
        fields.program_service_revenue_total = (
            self._find_first_valid_amount(section, r"Total.*Add lines 2a") or
            self._find_first_valid_amount(section, r"Total.*program service revenue") or
            extract_p8("2g", "Total")
        )

        # === Row 3: Investment income ===
        fields.investment_income = extract_p8("3", "Investment income")

        # === Row 4: Tax-exempt bond income ===
        fields.tax_exempt_bond_income = extract_p8("4", "Income from investment of tax.exempt bond")

        # === Row 5: Royalties ===
        fields.royalties = extract_p8("5", "Royalties")

        # === Rows 6a-6d: Rental income ===
        vals_6a = extract_p8_columns("6a", "Gross rents")
        if len(vals_6a) >= 1: fields.gross_rents_real = vals_6a[0]
        if len(vals_6a) >= 2: fields.gross_rents_personal = vals_6a[1]

        vals_6b = extract_p8_columns("6b", "Less.*rental expenses")
        if len(vals_6b) >= 1: fields.rental_expenses_real = vals_6b[0]
        if len(vals_6b) >= 2: fields.rental_expenses_personal = vals_6b[1]

        vals_6c = extract_p8_columns("6c", "Rental income or")
        if len(vals_6c) >= 1: fields.rental_income_real = vals_6c[0]
        if len(vals_6c) >= 2: fields.rental_income_personal = vals_6c[1]

        fields.net_rental_income = extract_p8("6d", "Net rental income")

        # === Rows 7a-7d: Gain/loss from sales ===
        # Text may say "Gross amount from sales of" or just "securities" on the line
        vals_7a = extract_p8_columns("7a", "Gross amount from sale")
        if not vals_7a:
            vals_7a = extract_p8_columns("7a", "assets other than inventory")
        if len(vals_7a) >= 1: fields.gross_sales_securities = vals_7a[0]
        if len(vals_7a) >= 2: fields.gross_sales_other = vals_7a[1]

        vals_7b = extract_p8_columns("7b", "Less.*cost")
        if len(vals_7b) >= 1: fields.cost_basis_securities = vals_7b[0]
        if len(vals_7b) >= 2: fields.cost_basis_other = vals_7b[1]

        vals_7c = extract_p8_columns("7c", "Gain or")
        if len(vals_7c) >= 1: fields.gain_loss_securities = vals_7c[0]
        if len(vals_7c) >= 2: fields.gain_loss_other = vals_7c[1]

        fields.net_gain_loss = extract_p8("7d", "Net gain")

        # === Rows 8a-8c: Fundraising events ===
        # Text may say "income from fundraising events" or just "fundraising"
        fields.fundraising_gross_income = extract_p8("8a", "income from fundraising")
        if not fields.fundraising_gross_income:
            fields.fundraising_gross_income = extract_p8("8a", "Fundraising events")
        vals_8a = extract_p8_columns("8a", "income from fundraising")
        if len(vals_8a) >= 2: fields.fundraising_8a_other = vals_8a[1]

        fields.fundraising_direct_expenses = extract_p8("8b", "Less.*direct expenses")
        fields.fundraising_net_income = (
            extract_p8("8c", "Net income.*fundraising") or
            extract_p8("8c", "Net income")
        )

        # === Rows 9a-9c: Gaming ===
        fields.gaming_gross_income = (
            extract_p8("9a", "income from gaming") or
            extract_p8("9a", "Gaming activities")
        )
        fields.gaming_direct_expenses = extract_p8("9b", "Less.*direct expenses")
        fields.gaming_net_income = (
            extract_p8("9c", "Net income.*gaming") or
            extract_p8("9c", "Net income")
        )

        # === Rows 10a-10c: Sales of inventory ===
        fields.inventory_gross_sales = (
            extract_p8("10a", "Gross sales of inventory") or
            extract_p8("10a", "sales of inventory")
        )
        fields.inventory_cost_of_goods = extract_p8("10b", "Less.*cost of goods")
        fields.inventory_net_income = (
            extract_p8("10c", "Net income.*sales") or
            extract_p8("10c", "Net income")
        )

        # === Row 11e: Other revenue total ===
        fields.other_revenue_total = (
            self._find_first_valid_amount(section, r"Total.*Add lines 11a.11d") or
            extract_p8("11e", "Total")
        )

        # === Row 12: Total revenue ===
        fields.total_revenue = (
            self._find_first_valid_amount(section, r"\b12\b\s+Total revenue") or
            self._find_first_valid_amount(section, "Total revenue")
        )

        return fields
    
    def _extract_part_ix_fields(self, text: str) -> PartIXFields:
        """Extract Part IX Functional Expenses fields"""
        fields = PartIXFields()

        # Find Part IX section using specific header
        part_match = re.search(
            r'Part IX\s+Statement of Functional(.*?)(?:Part X\s|$)',
            text, re.DOTALL | re.IGNORECASE
        )
        section = self._normalize_spaces(part_match.group(1) if part_match else text)

        def extract_p9(row_code, label):
            # Part IX: Column A (Total) is the FIRST column
            # Use word boundaries to avoid e.g. "7" matching "17"
            val = self._find_first_valid_amount(section, rf"\b{row_code}\b.*{label}")
            if val: return val

            # Try label + row code
            val = self._find_first_valid_amount(section, rf"{label}.*\b{row_code}\b")
            if val: return val

            # Try label only (relaxed) - only if label is non-empty
            if label:
                return self._find_first_valid_amount(section, label)
            return None

        # === Rows 1-4: Grants and benefits ===
        fields.grants_domestic_organizations = extract_p9("1", "Grants.*domestic organizations")


        fields.professional_fundraising_services = (
            extract_p9("11e", "Professional fundraising") or
            self._find_first_valid_amount(section, r"\be\b\s+Professional fundraising")
        )

        
        fields.affiliate_payments = extract_p9("21", "Payments.*affiliates")

        # === Row 25: Total functional expenses (Columns A, B, C, D) ===
        row25_pattern = r'\b25\b\s+Total functional expenses[^\n]*'
        match = re.search(row25_pattern, section, re.IGNORECASE)
        if not match:
            match = re.search(r'Total functional expenses[^\n]*', section, re.IGNORECASE)
        if match:
            valid_amounts = self._find_amounts_in_text(match.group(0))

            if len(valid_amounts) >= 1: fields.total_functional_expenses_a = valid_amounts[0]
            if len(valid_amounts) >= 2: fields.total_functional_expenses_b = valid_amounts[1]
            if len(valid_amounts) >= 3: fields.total_functional_expenses_c = valid_amounts[2]
            if len(valid_amounts) >= 4: fields.total_functional_expenses_d = valid_amounts[3]

        # === Row 26: Joint costs ===
        fields.joint_costs = extract_p9("26", "Joint costs")

        return fields
    
    def _find_last_valid_amount(self, text: str, pattern: str) -> Optional[str]:
        """Find the LAST valid amount matching a pattern (useful for totals at bottom)"""
        line_pattern = rf'{pattern}[^\n]*'
        last_amount = None
        for m in re.finditer(line_pattern, text, re.IGNORECASE):
            result = self._find_amounts_with_lookahead(text, m, take="last")
            if result:
                last_amount = result
        return last_amount

    def _find_valid_amount(self, text: str, pattern: str) -> Optional[str]:
        """Find the last valid monetary amount on the first line matching pattern.
        Falls back to subsequent lines if no amounts found on matched line."""
        line_pattern = rf'{pattern}[^\n]*'
        match = re.search(line_pattern, text, re.IGNORECASE)
        if match:
            return self._find_amounts_with_lookahead(text, match, take="last")
        return None

    def _find_first_valid_amount(self, text: str, pattern: str) -> Optional[str]:
        """Find the first valid monetary amount on the first line matching pattern.
        Falls back to subsequent lines if no amounts found on matched line.
        Used for Part VIII/IX where Column A (Total) is the leftmost column."""
        line_pattern = rf'{pattern}[^\n]*'
        match = re.search(line_pattern, text, re.IGNORECASE)
        if match:
            return self._find_amounts_with_lookahead(text, match, take="first")
        return None
    
    def _calculate_confidence(self, page1: Page1Fields, part_viii: PartVIIIFields,
                             part_ix: PartIXFields) -> float:
        """Calculate confidence based on key fields extracted across all sections"""
        key_fields = [
            page1.employer_identification_number,
            page1.gross_receipts,
            page1.total_revenue,
            page1.total_contributions,
            page1.total_assets,
            page1.net_assets_or_fund_balances,
            part_viii.contributions_total,
            part_viii.program_service_revenue_total,
            part_viii.total_revenue,
            part_ix.total_functional_expenses_a,
            part_ix.grants_domestic_organizations,
        ]

        filled = sum(1 for f in key_fields if f is not None)
        return filled / len(key_fields) if key_fields else 0.0
