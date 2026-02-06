"""
PDFPlumber-based PDF extraction implementation
Wraps existing pdfplumber logic from pdf_processor.py
"""
import pdfplumber
from collections import defaultdict
from typing import List, Tuple, Dict, Any
import logging

from .base_extractor import BasePDFExtractor, ExtractionResult, Word, Table, TableCell

logger = logging.getLogger(__name__)


class PDFPlumberExtractor(BasePDFExtractor):
    """
    PDF extractor using pdfplumber library
    Best for clean digital PDFs and table extraction
    """

    def __init__(self, y_tolerance: int = 3):
        """
        Initialize pdfplumber extractor

        Args:
            y_tolerance: Y-coordinate tolerance for grouping words on same line
        """
        self.y_tolerance = y_tolerance

    @property
    def name(self) -> str:
        return "pdfplumber"

    def extract(self, filepath: str) -> ExtractionResult:
        """Extract all data from PDF using pdfplumber"""
        self.validate_file(filepath)

        full_text = ""
        pages_data = []
        all_tables = []
        all_words = []

        try:
            with pdfplumber.open(filepath) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract text with y-tolerance grouping
                    page_text = self.extract_text(page)

                    # Extract tables
                    page_tables = self.extract_tables(page)
                    all_tables.extend(page_tables)

                    # Extract words with coordinates
                    page_words = self.extract_words(page)
                    all_words.extend(page_words)

                    # Get page dimensions
                    width, height = self.get_page_dimensions(page)

                    # Store page data
                    page_data = {
                        "page_number": page_num,
                        "text": page_text,
                        "tables": [t.cells for t in page_tables],  # Raw table data
                        "width": width,
                        "height": height,
                    }
                    pages_data.append(page_data)
                    full_text += f"\n--- Page {page_num} ---\n{page_text}\n"

            logger.info(f"PDFPlumber extracted {len(pages_data)} pages, "
                       f"{len(all_tables)} tables, {len(all_words)} words")

            return ExtractionResult(
                text=full_text,
                pages=pages_data,
                tables=all_tables,
                words=all_words,
                metadata={
                    "y_tolerance": self.y_tolerance,
                    "num_pages": len(pages_data)
                },
                extractor_name=self.name
            )

        except Exception as e:
            logger.error(f"PDFPlumber extraction failed: {e}")
            raise

    def extract_text(self, page) -> str:
        """
        Extract text from page using y-tolerance word grouping
        Reuses logic from pdf_processor.py:_extract_words_to_text()
        """
        words = page.extract_words(keep_blank_chars=True)
        if not words:
            return ""

        # Group words by approximate y-coordinate
        lines_by_y = defaultdict(list)
        for w in words:
            y_key = round(w['top'] / self.y_tolerance) * self.y_tolerance
            lines_by_y[y_key].append(w)

        # Build text lines sorted by y, words sorted by x within each line
        text_lines = []
        for y in sorted(lines_by_y.keys()):
            line_words = sorted(lines_by_y[y], key=lambda w: w['x0'])
            line = ' '.join(w['text'] for w in line_words)
            text_lines.append(line)

        return '\n'.join(text_lines)

    def extract_tables(self, page) -> List[Table]:
        """Extract tables from page"""
        tables = []
        raw_tables = page.extract_tables() or []

        page_num = page.page_number

        for table_idx, raw_table in enumerate(raw_tables):
            if not raw_table:
                continue

            # Create Table object
            table = Table(
                cells=raw_table,
                page_number=page_num,
                x0=0.0,  # pdfplumber doesn't provide table bbox by default
                y0=0.0,
                x1=0.0,
                y1=0.0
            )
            tables.append(table)

        return tables

    def extract_words(self, page) -> List[Word]:
        """Extract words with bounding boxes"""
        words = []
        raw_words = page.extract_words(keep_blank_chars=True)

        page_num = page.page_number

        for w in raw_words:
            word = Word(
                text=w['text'],
                x0=w['x0'],
                y0=w['top'],
                x1=w['x1'],
                y1=w['bottom'],
                page_number=page_num
            )
            words.append(word)

        return words

    def get_page_dimensions(self, page) -> Tuple[float, float]:
        """Get page dimensions"""
        return (page.width, page.height)
