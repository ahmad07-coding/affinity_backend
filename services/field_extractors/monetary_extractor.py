"""Monetary Field Extractor for all currency values"""
import re
from typing import Optional, List, Any, Tuple
from .base_field_extractor import BaseFieldExtractor, FieldExtractionResult


class MonetaryExtractor(BaseFieldExtractor):
    """Extracts and validates monetary amounts from Form 990"""

    def __init__(self):
        super().__init__()
        self.expected_type = "currency"

    def extract_field(
        self,
        field_name: str,
        row_label: str,
        column_name: str,
        text: str,
        tables: List[Any],
        section: str = ""
    ) -> FieldExtractionResult:
        """
        Extract a specific monetary field

        Args:
            field_name: Name of the field (e.g., "total_revenue")
            row_label: Row label to search for (e.g., "Total revenue", "8")
            column_name: Column name (e.g., "Current Year", "(A)")
            text: Full text
            tables: List of normalized tables
            section: Section to search in (e.g., "Part VIII")

        Returns:
            FieldExtractionResult
        """
        self.expected_section = section

        strategies = [
            lambda: self._extract_from_table(field_name, row_label, column_name, tables),
            lambda: self._extract_from_text(field_name, row_label, column_name, text, section),
        ]

        return self._extract_with_fallback(strategies, field_name)

    def _extract_from_table(
        self,
        field_name: str,
        row_label: str,
        column_name: str,
        tables: List[Any]
    ) -> Optional[FieldExtractionResult]:
        """Strategy 1: Extract from normalized table"""
        from services.table_processor import TableProcessor

        processor = TableProcessor()

        for table in tables:
            if not hasattr(table, 'rows'):
                continue

            # Try to extract field from this table
            result = processor.extract_field_from_table(table, row_label, column_name)
            if result:
                value, cell_confidence = result
                value = self._normalize_monetary_value(value)

                if self._is_valid_monetary_amount(value):
                    is_valid, conf_adj, errors = self.validate(value)
                    return FieldExtractionResult(
                        field_name=field_name,
                        value=value,
                        confidence=cell_confidence * conf_adj * 0.95,  # Table-based is high confidence
                        source="table",
                        validation_errors=errors
                    )

        return None

    def _extract_from_text(
        self,
        field_name: str,
        row_label: str,
        column_name: str,
        text: str,
        section: str
    ) -> Optional[FieldExtractionResult]:
        """Strategy 2: Extract using text patterns"""
        # If section specified, extract that section first
        if section:
            section_text = self._extract_section(text, section)
            if section_text:
                text = section_text

        # Build pattern
        pattern = rf'{re.escape(row_label)}[^\n]*'
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            line_text = match.group(0)

            # Find all monetary amounts in line
            amounts = re.findall(r'([\d,]{4,}(?:\.\d{2})?)', line_text)
            valid_amounts = [a for a in amounts if self._is_valid_monetary_amount(a)]

            if valid_amounts:
                # For "Current Year" or single column, take last amount
                # For "Column A", take first amount
                if 'column a' in column_name.lower() or '(a)' in column_name.lower():
                    value = valid_amounts[0]
                else:
                    value = valid_amounts[-1]

                value = self._normalize_monetary_value(value)
                is_valid, conf_adj, errors = self.validate(value)

                return FieldExtractionResult(
                    field_name=field_name,
                    value=value,
                    confidence=0.75 * conf_adj,
                    source="text_pattern",
                    validation_errors=errors
                )

        return None

    def _extract_section(self, text: str, section: str) -> Optional[str]:
        """Extract a specific section from text"""
        if section == "Part VIII":
            match = re.search(
                r'Part VIII\s+Statement of Revenue(.*?)(?:Part IX|$)',
                text, re.DOTALL | re.IGNORECASE
            )
            return match.group(1) if match else None

        elif section == "Part IX":
            match = re.search(
                r'Part IX\s+Statement of Functional(.*?)(?:Part X|$)',
                text, re.DOTALL | re.IGNORECASE
            )
            return match.group(1) if match else None

        return None

    def validate(self, value: str) -> Tuple[bool, float, List[str]]:
        """Validate monetary amount"""
        errors = []
        confidence = 1.0

        if not value:
            return False, 0.0, ["Value is empty"]

        # Check if valid monetary format
        if not self._is_valid_monetary_amount(value):
            errors.append("Invalid monetary format")
            return False, 0.0, errors

        # Clean and check range
        clean_value = value.replace(',', '').replace('.', '')
        try:
            num = int(clean_value)

            # Reasonable range check
            if num < 0:
                errors.append("Negative amounts not expected")
                confidence *= 0.5
            elif num > 999999999999:  # 999 billion
                errors.append("Amount exceeds reasonable limit")
                confidence *= 0.7

        except ValueError:
            errors.append("Cannot parse as number")
            return False, 0.0, errors

        is_valid = len(errors) == 0 or all('not expected' in e or 'exceeds' in e for e in errors)
        return is_valid, confidence, errors

    def extract(self, text: str, tables: List[Any], page_metadata: List[Any]) -> FieldExtractionResult:
        """Generic extract method (required by base class)"""
        # This is called by base class, but we use extract_field instead
        return FieldExtractionResult(
            field_name="monetary_field",
            value=None,
            confidence=0.0,
            source="none"
        )
