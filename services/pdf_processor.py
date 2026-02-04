"""
PDF Processing Service - Enhanced OCR with Full Page Analysis
Handles: Text-based, Image-based, and Hybrid PDFs (like filled IRS Form 990)
Uses full-page OCR combined with smart text parsing for maximum accuracy
"""
import pdfplumber
from pdf2image import convert_from_path
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from collections import defaultdict
import io
import os
import re
from typing import Optional, Tuple, List, Dict, Any
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PDFType(Enum):
    """Classification of PDF types"""
    TEXT_BASED = "text_based"
    IMAGE_BASED = "image_based"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class HybridPDFProcessor:
    """
    Enhanced PDF processor that:
    1. Runs full-page OCR to capture ALL text including image overlays
    2. Combines OCR text with pdfplumber text for complete extraction
    3. Uses smart parsing to find field values
    """
    
    def __init__(self, dpi: int = 400):  # Higher DPI for better OCR accuracy
        self.dpi = dpi
        self.supported_extensions = ['.pdf']
        self.ocr_available = self._check_tesseract()
    
    def _check_tesseract(self) -> bool:
        """Verify tesseract is installed"""
        try:
            version = pytesseract.get_tesseract_version()
            logger.info(f"Tesseract OCR is available (version {version})")
            return True
        except Exception as e:
            logger.warning(f"Tesseract not available: {e}. OCR features disabled.")
            return False
    
    def validate_file(self, filepath: str) -> bool:
        """Validate that the file exists and is a PDF"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        
        ext = os.path.splitext(filepath)[1].lower()
        if ext not in self.supported_extensions:
            raise ValueError(f"Unsupported file type: {ext}")
        
        return True
    
    def detect_pdf_type(self, filepath: str) -> PDFType:
        """Detect the type of PDF based on text content"""
        try:
            with pdfplumber.open(filepath) as pdf:
                if len(pdf.pages) == 0:
                    return PDFType.UNKNOWN
                
                page = pdf.pages[0]
                text = page.extract_text(layout=True) or ""
                chars = len(text.replace(" ", "").replace("\n", ""))
                
                if chars > 1000:
                    # Check for Form 990 - these are typically hybrid
                    if self._is_form_990_text(text):
                        return PDFType.HYBRID
                    return PDFType.TEXT_BASED
                elif chars > 100:
                    return PDFType.HYBRID
                else:
                    return PDFType.IMAGE_BASED
                    
        except Exception as e:
            logger.error(f"Error detecting PDF type: {e}")
            return PDFType.UNKNOWN
    
    def _is_form_990_text(self, text: str) -> bool:
        """Check if the text contains Form 990 indicators"""
        indicators = ["Form 990", "Return of Organization", "Employer identification", 
                     "Gross receipts", "Part I", "Summary"]
        text_lower = text.lower()
        return sum(1 for ind in indicators if ind.lower() in text_lower) >= 2
    
    def process_pdf_hybrid(self, filepath: str) -> Dict[str, Any]:
        """
        Main processing method - uses OCR for hybrid PDFs to capture filled values
        """
        self.validate_file(filepath)
        
        pdf_type = self.detect_pdf_type(filepath)
        logger.info(f"Detected PDF type: {pdf_type.value}")
        
        result = {
            "full_text": "",
            "pages_data": [],
            "ocr_fields": {},
            "extraction_info": {
                "method": "hybrid",
                "pdf_type": pdf_type.value,
                "ocr_available": self.ocr_available,
                "dpi": self.dpi,
                "pages_processed": 0,
            }
        }
        
        # Step 1: Get pdfplumber text (for structure)
        try:
            plumber_text, pages = self._extract_with_pdfplumber(filepath)
            result["pages_data"] = pages
            result["extraction_info"]["pages_processed"] = len(pages)
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}")
            plumber_text = ""
        
        # Step 2: For hybrid/form PDFs, ALWAYS run full-page OCR to capture filled values
        if self.ocr_available and pdf_type in [PDFType.HYBRID, PDFType.IMAGE_BASED]:
            try:
                ocr_text, ocr_pages = self._extract_with_full_ocr(filepath)
                
                # Combine pdfplumber (structure) with OCR (filled values)
                result["full_text"] = self._merge_texts(plumber_text, ocr_text)
                
                # Store OCR text in pages_data for the field extractor
                for i, page_data in enumerate(result["pages_data"]):
                    if i < len(ocr_pages):
                        page_data["ocr_text"] = ocr_pages[i].get("text", "")
                
                result["extraction_info"]["method"] = "hybrid_ocr"
                logger.info("Hybrid extraction with full-page OCR completed")
                
            except Exception as e:
                logger.error(f"OCR extraction failed: {e}")
                result["full_text"] = plumber_text
        else:
            result["full_text"] = plumber_text
            result["extraction_info"]["method"] = "text_only"
        
        return result
    
    def _extract_words_to_text(self, page, y_tolerance: int = 3) -> str:
        """
        Build page text from extract_words() with y-tolerance grouping.
        This merges form template text and filled-in overlay values that are
        at slightly different y-coordinates (typically ~1px apart) onto the
        same line, which pdfplumber's extract_text() fails to do.
        """
        words = page.extract_words(keep_blank_chars=True)
        if not words:
            return ""

        # Group words by approximate y-coordinate
        lines_by_y = defaultdict(list)
        for w in words:
            y_key = round(w['top'] / y_tolerance) * y_tolerance
            lines_by_y[y_key].append(w)

        # Build text lines sorted by y, words sorted by x within each line
        text_lines = []
        for y in sorted(lines_by_y.keys()):
            line_words = sorted(lines_by_y[y], key=lambda w: w['x0'])
            line = ' '.join(w['text'] for w in line_words)
            text_lines.append(line)

        return '\n'.join(text_lines)

    def _extract_with_pdfplumber(self, filepath: str) -> Tuple[str, List[dict]]:
        """Extract text using pdfplumber with word-level y-tolerance grouping"""
        full_text = ""
        pages_data = []

        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = self._extract_words_to_text(page, y_tolerance=3)
                tables = page.extract_tables() or []

                page_data = {
                    "page_number": page_num,
                    "text": page_text,
                    "tables": tables,
                    "width": page.width,
                    "height": page.height,
                }
                pages_data.append(page_data)
                full_text += f"\n--- Page {page_num} ---\n{page_text}\n"

        return full_text, pages_data
    
    def _extract_with_full_ocr(self, filepath: str) -> Tuple[str, List[dict]]:
        """
        Full page OCR extraction - captures ALL text including image overlays
        This is crucial for filled form values
        """
        full_text = ""
        pages_data = []
        
        # Convert PDF to high-resolution images
        images = convert_from_path(filepath, dpi=self.dpi)
        
        for page_num, image in enumerate(images, 1):
            # Preprocess image for better OCR
            processed = self._preprocess_image(image)
            
            # Use optimal OCR settings for forms
            custom_config = r'--oem 3 --psm 6 -c preserve_interword_spaces=1'
            page_text = pytesseract.image_to_string(processed, config=custom_config)
            
            page_data = {
                "page_number": page_num,
                "text": page_text,
                "width": image.width,
                "height": image.height,
            }
            pages_data.append(page_data)
            full_text += f"\n--- Page {page_num} (OCR) ---\n{page_text}\n"
            
            logger.debug(f"OCR Page {page_num}: {len(page_text)} chars extracted")
        
        return full_text, pages_data
    
    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocess image for optimal OCR - minimal processing with high DPI works best"""
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Note: Testing showed that with DPI 400, minimal preprocessing produces
        # the most accurate results. Previous contrast/sharpness enhancement was
        # causing character misrecognition (e.g., '3' -> '9')
        
        return image
    
    def _merge_texts(self, plumber_text: str, ocr_text: str) -> str:
        """Merge pdfplumber and OCR text, prioritizing unique content from each"""
        # Include both texts - OCR text often has the filled values
        merged = plumber_text + "\n\n--- OCR Extracted Text ---\n" + ocr_text
        return merged
    
    def get_page_count(self, filepath: str) -> int:
        """Get the number of pages in the PDF"""
        self.validate_file(filepath)
        with pdfplumber.open(filepath) as pdf:
            return len(pdf.pages)


# Backward compatibility wrapper
class PDFProcessor:
    """Wrapper for backward compatibility"""
    
    def __init__(self):
        self.hybrid = HybridPDFProcessor()
        self.supported_extensions = ['.pdf']
    
    def validate_file(self, filepath: str) -> bool:
        return self.hybrid.validate_file(filepath)
    
    def process_pdf(self, filepath: str, force_ocr: bool = False) -> Tuple[str, List[dict], str]:
        """Process PDF and return (text, pages_data, method)"""
        result = self.hybrid.process_pdf_hybrid(filepath)
        
        # Pass OCR text to pages_data for the field extractor
        if result["pages_data"]:
            result["pages_data"][0]["pdf_type"] = result["extraction_info"].get("pdf_type", "unknown")
        
        return result["full_text"], result["pages_data"], result["extraction_info"]["method"]
    
    def get_page_count(self, filepath: str) -> int:
        return self.hybrid.get_page_count(filepath)
