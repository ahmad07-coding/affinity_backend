"""
Table Normalization Layer
Extracts and normalizes tables from Form 990, cleaning OCR artifacts
"""
import re
import logging
from typing import List, Optional, Tuple, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NormalizedTableCell:
    """Represents a normalized cell in a table"""
    text: str
    row: int
    col: int
    confidence: float
    original_text: str  # Before normalization


@dataclass
class NormalizedTable:
    """Represents a normalized table"""
    headers: List[str]
    rows: List[List[NormalizedTableCell]]
    table_type: str  # "Part_I", "Part_VIII", "Part_IX", "unknown"
    confidence: float
    page_number: int


class TableProcessor:
    """
    Processes and normalizes tables extracted from Form 990
    Handles OCR artifacts and formatting differences
    """

    # OCR artifact patterns to clean
    ARTIFACT_PATTERNS = [
        (r'<ti \(/1', ''),
        (r'C c,J :C', ''),
        (r'\.{5,}', ''),  # Multiple dots (dot leaders)
        (r'~{5,}', ''),   # Multiple tildes
        (r'[<>(){}/\\]{3,}', ''),  # Multiple special chars
    ]

    # Spacing fix patterns
    SPACING_PATTERNS = [
        # Fix EIN spacing: "3 9 - 0 8 0 6 2 5 1" → "39-0806251"
        (r'(\d)\s+(\d)\s*-\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)',
         r'\1\2-\3\4\5\6\7\8\9'),
        # Fix general digit spacing: "1 2 3 4" → "1234"
        (r'(\d)\s+(\d)\s+(\d)', r'\1\2\3'),
    ]

    # Column header patterns
    COLUMN_HEADERS = {
        'Part_I': ['Prior Year', 'Current Year', 'Beginning of Year', 'End of Year'],
        'Part_VIII': ['(A)\nTotal revenue', '(B)\nRelated or exempt', '(C)\nUnrelated', '(D)\nRevenue excluded'],
        'Part_IX': ['(A)\nTotal expenses', '(B)\nProgram service', '(C)\nManagement', '(D)\nFundraising'],
    }

    def normalize_table(self, table: Any, page_number: int = 1) -> NormalizedTable:
        """
        Normalize a table by cleaning artifacts and standardizing format

        Args:
            table: Raw table (2D list of strings or Table object)
            page_number: Page number where table appears

        Returns:
            NormalizedTable with cleaned data
        """
        # Convert to 2D list if needed
        if hasattr(table, 'cells'):
            raw_cells = table.cells
            page_number = getattr(table, 'page_number', page_number)
        else:
            raw_cells = table

        if not raw_cells:
            return NormalizedTable([], [], "unknown", 0.0, page_number)

        # Clean all cells
        cleaned_rows = []
        for row_idx, row in enumerate(raw_cells):
            cleaned_row = []
            for col_idx, cell in enumerate(row):
                original_text = cell if cell else ""
                cleaned_text = self._clean_cell_text(original_text)

                normalized_cell = NormalizedTableCell(
                    text=cleaned_text,
                    row=row_idx,
                    col=col_idx,
                    confidence=self._calculate_cell_confidence(original_text, cleaned_text),
                    original_text=original_text
                )
                cleaned_row.append(normalized_cell)
            cleaned_rows.append(cleaned_row)

        # Extract headers (usually first row)
        headers = [cell.text for cell in cleaned_rows[0]] if cleaned_rows else []

        # Identify table type
        table_type = self._identify_table_type(headers, cleaned_rows)

        # Calculate overall confidence
        confidence = self._calculate_table_confidence(cleaned_rows, table_type)

        return NormalizedTable(
            headers=headers,
            rows=cleaned_rows,
            table_type=table_type,
            confidence=confidence,
            page_number=page_number
        )

    def _clean_cell_text(self, text: str) -> str:
        """Clean a single cell's text"""
        if not text:
            return ""

        cleaned = text

        # Apply artifact removal patterns
        for pattern, replacement in self.ARTIFACT_PATTERNS:
            cleaned = re.sub(pattern, replacement, cleaned)

        # Apply spacing fixes
        for pattern, replacement in self.SPACING_PATTERNS:
            cleaned = re.sub(pattern, replacement, cleaned)

        # Fix common OCR typos
        cleaned = self._fix_ocr_typos(cleaned)

        # Normalize decimal format: "384,948." → "384,948.00"
        cleaned = self._normalize_decimal_format(cleaned)

        # Strip extra whitespace
        cleaned = ' '.join(cleaned.split())

        return cleaned.strip()

    def _fix_ocr_typos(self, text: str) -> str:
        """Fix common OCR typos"""
        # Fix column label typos
        text = re.sub(r'\(Cl\)', '(C)', text)  # "(Cl)" → "(C)"
        text = re.sub(r'ia-1f', '1a-1f', text)  # "ia-1f" → "1a-1f"

        # Fix common letter/number confusion
        text = re.sub(r'\bl\b', '1', text)  # standalone "l" → "1"
        text = re.sub(r'\bO\b', '0', text)  # standalone "O" → "0"

        return text

    def _normalize_decimal_format(self, text: str) -> str:
        """Normalize decimal formats in monetary values"""
        # Match patterns like "384,948." (trailing period, no decimal places)
        # Convert to "384,948.00"
        pattern = r'\b(\d{1,3}(?:,\d{3})*)\.\s*$'
        match = re.search(pattern, text)
        if match:
            number = match.group(1)
            text = re.sub(pattern, f'{number}.00', text)

        return text

    def _calculate_cell_confidence(self, original: str, cleaned: str) -> float:
        """Calculate confidence score for a cell based on cleaning needed"""
        if not original:
            return 1.0

        # No changes needed = high confidence
        if original == cleaned:
            return 1.0

        # Calculate edit distance ratio
        changes = len(original) - len(cleaned) + abs(original.count(' ') - cleaned.count(' '))
        change_ratio = changes / len(original) if len(original) > 0 else 0

        # More changes = lower confidence
        confidence = max(0.5, 1.0 - change_ratio)

        return confidence

    def _identify_table_type(self, headers: List[str], rows: List[List]) -> str:
        """Identify which Form 990 section this table belongs to"""
        # Check headers against known patterns
        header_text = ' '.join(headers).lower()

        if 'prior year' in header_text and 'current year' in header_text:
            # Could be Part I
            if any('contributions' in str(row[0].text).lower() for row in rows[1:6] if row):
                return "Part_I"

        if 'total revenue' in header_text or 'column a' in header_text:
            # Check for revenue indicators in first column
            for row in rows[1:10]:
                if row and 'federated campaigns' in str(row[0].text).lower():
                    return "Part_VIII"

        if 'total expenses' in header_text or ('program service' in header_text):
            # Check for expense indicators
            for row in rows[1:10]:
                if row and ('grants' in str(row[0].text).lower() or
                           'domestic organizations' in str(row[0].text).lower()):
                    return "Part_IX"

        return "unknown"

    def _calculate_table_confidence(self, rows: List[List[NormalizedTableCell]],
                                   table_type: str) -> float:
        """Calculate overall table confidence"""
        if not rows:
            return 0.0

        # Average cell confidence
        all_cells = [cell for row in rows for cell in row]
        if not all_cells:
            return 0.0

        avg_cell_confidence = sum(c.confidence for c in all_cells) / len(all_cells)

        # Bonus for identified table type
        type_bonus = 0.2 if table_type != "unknown" else 0.0

        # Penalty for very short text (likely incomplete)
        total_text = sum(len(c.text) for c in all_cells)
        if total_text < 50:
            return avg_cell_confidence * 0.5

        return min(1.0, avg_cell_confidence + type_bonus)

    def extract_field_from_table(self, table: NormalizedTable, row_label: str,
                                column_name: str) -> Optional[Tuple[str, float]]:
        """
        Extract a specific field from a normalized table

        Args:
            table: Normalized table
            row_label: Label to search for in first column (e.g., "Total revenue", "8")
            column_name: Column header to extract from (e.g., "Current Year", "(A)")

        Returns:
            Tuple of (value, confidence) or None if not found
        """
        # Find column index
        col_idx = None
        for idx, header in enumerate(table.headers):
            if column_name.lower() in header.lower() or column_name in header:
                col_idx = idx
                break

        if col_idx is None:
            return None

        # Find row
        for row in table.rows:
            if not row:
                continue

            # Check if first cell matches row label
            first_cell = row[0].text
            if re.search(re.escape(row_label), first_cell, re.IGNORECASE):
                # Extract value from specified column
                if col_idx < len(row):
                    cell = row[col_idx]
                    return (cell.text, cell.confidence)

        return None

    def get_row_by_label(self, table: NormalizedTable,
                        row_label: str) -> Optional[List[NormalizedTableCell]]:
        """Get entire row by matching label in first column"""
        for row in table.rows:
            if row and re.search(re.escape(row_label), row[0].text, re.IGNORECASE):
                return row
        return None

    def get_column_by_header(self, table: NormalizedTable,
                           column_header: str) -> Optional[List[NormalizedTableCell]]:
        """Get entire column by matching header"""
        col_idx = None
        for idx, header in enumerate(table.headers):
            if column_header.lower() in header.lower():
                col_idx = idx
                break

        if col_idx is None:
            return None

        return [row[col_idx] for row in table.rows if col_idx < len(row)]
