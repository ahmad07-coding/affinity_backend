"""EIN (Employer Identification Number) Extractor"""
import re
from typing import Optional, List, Any
from .base_field_extractor import BaseFieldExtractor, FieldExtractionResult


class EINExtractor(BaseFieldExtractor):
    """Extracts and validates EIN (format: XX-XXXXXXX)"""

    def __init__(self):
        super().__init__()
        self.expected_section = "Header"
        self.expected_type = "ein"

    def extract(self, text: str, tables: List[Any], page_metadata: List[Any]) -> FieldExtractionResult:
        """Extract EIN using multiple strategies"""

        strategies = [
            lambda: self._extract_from_table(tables),
            lambda: self._extract_with_pattern(text),
            lambda: self._extract_with_spacing_fix(text),
        ]

        return self._extract_with_fallback(strategies, "employer_identification_number")

    def _extract_from_table(self, tables: List[Any]) -> Optional[FieldExtractionResult]:
        """Strategy 1: Extract from header table"""
        # Look for table with "Employer identification" label
        for table in tables:
            if hasattr(table, 'rows'):
                for row in table.rows:
                    if row and len(row) > 0:
                        first_cell = row[0].text if hasattr(row[0], 'text') else str(row[0])
                        if re.search(r'Employer identification', first_cell, re.IGNORECASE):
                            # EIN should be in next cell or same row
                            for cell in row[1:]:
                                cell_text = cell.text if hasattr(cell, 'text') else str(cell)
                                ein_match = re.search(r'\b(\d{2}-\d{7})\b', cell_text)
                                if ein_match:
                                    value = ein_match.group(1)
                                    is_valid, conf_adj, errors = self.validate(value)
                                    return FieldExtractionResult(
                                        field_name="employer_identification_number",
                                        value=value,
                                        confidence=0.95 * conf_adj,
                                        source="table",
                                        validation_errors=errors
                                    )
        return None

    def _extract_with_pattern(self, text: str) -> Optional[FieldExtractionResult]:
        """Strategy 2: Pattern match with context"""
        # Pattern 1: Standard EIN format with hyphen
        ein_matches = re.findall(r'\b(\d{2}-\d{7})\b', text)
        if ein_matches:
            value = ein_matches[0]
            is_valid, conf_adj, errors = self.validate(value)
            return FieldExtractionResult(
                field_name="employer_identification_number",
                value=value,
                confidence=0.85 * conf_adj,
                source="text_pattern",
                validation_errors=errors
            )

        # Pattern 2: EIN without hyphen near "Address change"
        ein_section = re.search(r'Address change[^\n]*(\d{9})', text, re.IGNORECASE)
        if ein_section:
            digits = ein_section.group(1)
            value = f"{digits[:2]}-{digits[2:]}"
            is_valid, conf_adj, errors = self.validate(value)
            return FieldExtractionResult(
                field_name="employer_identification_number",
                value=value,
                confidence=0.80 * conf_adj,
                source="text_pattern",
                validation_errors=errors
            )

        return None

    def _extract_with_spacing_fix(self, text: str) -> Optional[FieldExtractionResult]:
        """Strategy 3: Fix spacing artifacts from OCR"""
        # Pattern: "3 9 - 0 8 0 6 2 5 1" → "39-0806251"
        spacing_pattern = r'(\d)\s+(\d)\s*-\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)'
        match = re.search(spacing_pattern, text)
        if match:
            value = f"{match.group(1)}{match.group(2)}-{match.group(3)}{match.group(4)}{match.group(5)}{match.group(6)}{match.group(7)}{match.group(8)}{match.group(9)}"
            is_valid, conf_adj, errors = self.validate(value)
            return FieldExtractionResult(
                field_name="employer_identification_number",
                value=value,
                confidence=0.70 * conf_adj,  # Lower confidence due to OCR repair
                source="text_pattern_ocr_fixed",
                validation_errors=errors,
                metadata={"ocr_spacing_fixed": True}
            )

        return None

    def validate(self, value: str) -> tuple[bool, float, List[str]]:
        """Validate EIN format"""
        errors = []
        confidence = 1.0

        if not value:
            return False, 0.0, ["EIN is empty"]

        # Check format: XX-XXXXXXX
        if not re.match(r'^\d{2}-\d{7}$', value):
            errors.append("EIN must match format XX-XXXXXXX")
            return False, 0.0, errors

        # Check not all zeros
        if value.replace('-', '') == '000000000':
            errors.append("EIN cannot be all zeros")
            confidence *= 0.5

        # Check not sequential
        digits = value.replace('-', '')
        if digits == '123456789' or digits == '987654321':
            errors.append("EIN appears to be test/sequential number")
            confidence *= 0.7

        is_valid = len(errors) == 0
        return is_valid, confidence, errors
