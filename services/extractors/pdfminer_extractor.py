"""
PDFMiner.six-based PDF extraction implementation
Better for scanned PDFs with OCR layers and complex layouts
"""
from pdfminer.high_level import extract_pages, extract_text
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTChar, LTFigure, LTPage
from typing import List, Tuple, Dict, Any
import logging

from .base_extractor import BasePDFExtractor, ExtractionResult, Word, Table

logger = logging.getLogger(__name__)


class PDFMinerExtractor(BasePDFExtractor):
    """
    PDF extractor using pdfminer.six library
    Better for scanned PDFs and documents with OCR layers
    """

    def __init__(self, line_overlap: float = 0.5, char_margin: float = 2.0,
                 word_margin: float = 0.1):
        """
        Initialize pdfminer.six extractor with LAParams

        Args:
            line_overlap: Min overlap for line detection (0-1)
            char_margin: Max space between chars in same word
            word_margin: Max space between words in same line
        """
        self.laparams = LAParams(
            line_overlap=line_overlap,
            char_margin=char_margin,
            word_margin=word_margin,
            boxes_flow=0.5
        )

    @property
    def name(self) -> str:
        return "pdfminer"

    def extract(self, filepath: str) -> ExtractionResult:
        """Extract all data from PDF using pdfminer.six"""
        self.validate_file(filepath)

        full_text = ""
        pages_data = []
        all_words = []
        all_tables = []

        try:
            page_num = 0
            for page_layout in extract_pages(filepath, laparams=self.laparams):
                page_num += 1

                # Extract text
                page_text = self.extract_text(page_layout)

                # Extract words with coordinates
                page_words = self.extract_words(page_layout)
                all_words.extend(page_words)

                # Extract tables (basic implementation)
                page_tables = self.extract_tables(page_layout)
                all_tables.extend(page_tables)

                # Get dimensions
                width, height = self.get_page_dimensions(page_layout)

                # Store page data
                page_data = {
                    "page_number": page_num,
                    "text": page_text,
                    "tables": [t.cells for t in page_tables],
                    "width": width,
                    "height": height,
                }
                pages_data.append(page_data)
                full_text += f"\n--- Page {page_num} ---\n{page_text}\n"

            logger.info(f"PDFMiner extracted {len(pages_data)} pages, "
                       f"{len(all_tables)} tables, {len(all_words)} words")

            return ExtractionResult(
                text=full_text,
                pages=pages_data,
                tables=all_tables,
                words=all_words,
                metadata={
                    "laparams": {
                        "line_overlap": self.laparams.line_overlap,
                        "char_margin": self.laparams.char_margin
                    },
                    "num_pages": len(pages_data)
                },
                extractor_name=self.name
            )

        except Exception as e:
            logger.error(f"PDFMiner extraction failed: {e}")
            raise

    def extract_text(self, page_layout: LTPage) -> str:
        """Extract text from page layout preserving structure"""
        text_elements = []

        def extract_text_from_element(element):
            """Recursively extract text from layout elements"""
            if isinstance(element, (LTTextBox, LTTextLine)):
                text_elements.append({
                    'text': element.get_text(),
                    'y0': element.y0,
                    'x0': element.x0
                })
            elif isinstance(element, LTFigure):
                # Recursively process figures
                for child in element:
                    extract_text_from_element(child)
            elif hasattr(element, '__iter__'):
                for child in element:
                    extract_text_from_element(child)

        extract_text_from_element(page_layout)

        # Sort by y-coordinate (top to bottom), then x-coordinate (left to right)
        # Note: PDF coordinates have origin at bottom-left
        text_elements.sort(key=lambda e: (-e['y0'], e['x0']))

        # Combine text
        return ''.join(e['text'] for e in text_elements)

    def extract_tables(self, page_layout: LTPage) -> List[Table]:
        """
        Basic table extraction using text clustering
        Note: pdfminer.six doesn't have built-in table detection
        This is a simple implementation that groups nearby text elements
        """
        tables = []
        # For now, return empty list - table extraction is better handled by pdfplumber
        # A full implementation would cluster text elements by coordinates
        return tables

    def extract_words(self, page_layout: LTPage) -> List[Word]:
        """Extract words with bounding boxes"""
        words = []
        page_num = page_layout.pageid if hasattr(page_layout, 'pageid') else 1

        def extract_words_from_element(element, current_page):
            """Recursively extract words from layout elements"""
            if isinstance(element, LTTextLine):
                # Get text and bbox from text line
                text = element.get_text().strip()
                if text:
                    word = Word(
                        text=text,
                        x0=element.x0,
                        y0=element.y0,
                        x1=element.x1,
                        y1=element.y1,
                        page_number=current_page
                    )
                    words.append(word)

            elif isinstance(element, LTFigure):
                for child in element:
                    extract_words_from_element(child, current_page)

            elif hasattr(element, '__iter__'):
                for child in element:
                    extract_words_from_element(child, current_page)

        extract_words_from_element(page_layout, page_num)
        return words

    def get_page_dimensions(self, page_layout: LTPage) -> Tuple[float, float]:
        """Get page dimensions"""
        return (page_layout.width, page_layout.height)
