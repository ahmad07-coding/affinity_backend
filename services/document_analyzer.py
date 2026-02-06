"""
Document Intelligence Layer
Handles multi-document PDFs, Form 990 detection, and layout classification
"""
import re
import logging
from typing import List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PageMetadata:
    """Metadata about a PDF page"""
    page_number: int
    is_form_990: bool
    is_form_8868: bool
    confidence: float
    sections_detected: List[str]
    layout_type: str  # "digital", "scanned", "hybrid"
    ocr_quality_score: float


class DocumentAnalyzer:
    """
    Analyzes document structure and identifies Form 990 pages
    """

    # Form 990 identifiers
    FORM_990_PATTERNS = [
        r'Form\s+990\b',
        r'OMB\s+No\.\s*1545-0047',
        r'Return of Organization Exempt',
        r'Part\s+I\s+Summary',
    ]

    # Form 8868 (Extension) identifiers
    FORM_8868_PATTERNS = [
        r'Form\s+8868\b',
        r'Application for.*Extension of Time',
        r'Automatic Extension of Time',
    ]

    # Section identifiers
    SECTION_PATTERNS = {
        'Part I': r'Part\s+I\s+Summary',
        'Part VIII': r'Part\s+VIII\s+Statement of Revenue',
        'Part IX': r'Part\s+IX\s+Statement of Functional',
        'Part X': r'Part\s+X\s+Balance Sheet',
    }

    # OCR artifact patterns
    OCR_ARTIFACT_PATTERNS = [
        r'<ti \(/1',
        r'C c,J :C',
        r'[<>(){}/\\]{3,}',
        r'\s{5,}',
        r'\.{10,}',
    ]

    def detect_form_990_start(self, pages: List[Dict[str, Any]]) -> int:
        """
        Find the first page of actual Form 990 (skip Form 8868, cover pages)

        Args:
            pages: List of page data dictionaries with 'text' field

        Returns:
            Page number (1-indexed) of first Form 990 page, or 1 if not found
        """
        for page in pages:
            page_num = page.get('page_number', 1)
            text = page.get('text', '')

            # Check if this is Form 8868 (skip it)
            if self._is_form_8868(text):
                logger.info(f"Page {page_num}: Form 8868 detected, skipping")
                continue

            # Check if this is Form 990
            if self._is_form_990(text):
                logger.info(f"Page {page_num}: Form 990 detected")
                return page_num

        # Default to page 1 if no clear Form 990 found
        logger.warning("Form 990 start page not clearly detected, defaulting to page 1")
        return 1

    def analyze_page(self, page: Dict[str, Any]) -> PageMetadata:
        """
        Analyze a single page and return metadata

        Args:
            page: Page data dictionary

        Returns:
            PageMetadata with analysis results
        """
        page_num = page.get('page_number', 1)
        text = page.get('text', '')

        # Detect form types
        is_form_990 = self._is_form_990(text)
        is_form_8868 = self._is_form_8868(text)

        # Detect sections
        sections = self._detect_sections(text)

        # Classify layout type
        layout_type = self.classify_page_layout(text)

        # Analyze OCR quality
        ocr_quality = self.analyze_ocr_quality(text)

        # Calculate confidence
        confidence = self._calculate_page_confidence(
            is_form_990, sections, layout_type, ocr_quality
        )

        return PageMetadata(
            page_number=page_num,
            is_form_990=is_form_990,
            is_form_8868=is_form_8868,
            confidence=confidence,
            sections_detected=sections,
            layout_type=layout_type,
            ocr_quality_score=ocr_quality
        )

    def classify_page_layout(self, text: str) -> str:
        """
        Classify page layout type based on text characteristics

        Args:
            text: Page text

        Returns:
            One of: "digital", "scanned", "hybrid"
        """
        if not text or len(text) < 100:
            return "unknown"

        # Calculate OCR quality score
        ocr_quality = self.analyze_ocr_quality(text)

        # Check character distribution
        total_chars = len(text)
        alpha_chars = sum(1 for c in text if c.isalpha())
        digit_chars = sum(1 for c in text if c.isdigit())
        space_chars = sum(1 for c in text if c.isspace())

        # Digital PDFs have high OCR quality and good char distribution
        if ocr_quality > 0.8:
            return "digital"

        # Scanned PDFs have low OCR quality and artifacts
        if ocr_quality < 0.5:
            return "scanned"

        # Hybrid PDFs have medium OCR quality
        return "hybrid"

    def analyze_ocr_quality(self, text: str) -> float:
        """
        Analyze OCR quality based on artifact patterns

        Args:
            text: Page text

        Returns:
            Score from 0.0 (poor) to 1.0 (excellent)
        """
        if not text:
            return 0.0

        artifact_count = 0
        for pattern in self.OCR_ARTIFACT_PATTERNS:
            matches = re.findall(pattern, text)
            artifact_count += len(matches)

        # Normalize by text length (artifacts per 1000 chars)
        text_len = len(text)
        if text_len == 0:
            return 0.0

        artifact_density = (artifact_count / text_len) * 1000

        # Convert to quality score
        # 0 artifacts = 1.0 score
        # 10+ artifacts per 1000 chars = 0.0 score
        quality_score = max(0.0, 1.0 - (artifact_density / 10))

        return quality_score

    def _is_form_990(self, text: str) -> bool:
        """Check if text contains Form 990 indicators"""
        if not text:
            return False

        # First, check if this is Form 8868 (extension) - if so, NOT Form 990
        if self._is_form_8868(text):
            return False

        matches = 0
        for pattern in self.FORM_990_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                matches += 1

        # If "Form 990" is found with any other indicator, it's Form 990
        # Or if we find strong indicators like "Part I Summary"
        has_form_990 = re.search(r'Form\s+990\b', text, re.IGNORECASE) is not None
        has_part_i = re.search(r'Part\s+I\s+Summary', text, re.IGNORECASE) is not None
        has_omb = re.search(r'OMB\s+No\.\s*1545-0047', text, re.IGNORECASE) is not None

        # Strong evidence: Form 990 + OMB number or Part I
        if has_form_990 and (has_omb or has_part_i):
            return True

        # Alternative: Check for EIN field which is unique to Form 990 page 1
        has_ein_field = re.search(r'Employer identification number|EIN\s*[:.]', text, re.IGNORECASE) is not None
        if has_form_990 and has_ein_field:
            return True

        # Fallback: Need at least 2 indicators
        return matches >= 2

    def _is_form_8868(self, text: str) -> bool:
        """Check if text contains Form 8868 (Extension) indicators"""
        if not text:
            return False

        for pattern in self.FORM_8868_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False

    def _detect_sections(self, text: str) -> List[str]:
        """Detect which Form 990 sections are present in text"""
        sections = []

        for section_name, pattern in self.SECTION_PATTERNS.items():
            if re.search(pattern, text, re.IGNORECASE):
                sections.append(section_name)

        return sections

    def _calculate_page_confidence(
        self,
        is_form_990: bool,
        sections: List[str],
        layout_type: str,
        ocr_quality: float
    ) -> float:
        """Calculate confidence score for page analysis"""
        confidence = 0.0

        # Base confidence from form detection
        if is_form_990:
            confidence += 0.4

        # Add confidence for sections detected
        if sections:
            confidence += min(0.3, len(sections) * 0.1)

        # Add confidence for layout classification
        if layout_type in ['digital', 'hybrid']:
            confidence += 0.2
        elif layout_type == 'scanned':
            confidence += 0.1

        # Add confidence from OCR quality
        confidence += ocr_quality * 0.1

        return min(1.0, confidence)

    def get_form_990_pages(self, pages: List[Dict[str, Any]]) -> List[int]:
        """
        Get all page numbers that contain Form 990 content

        Args:
            pages: List of page data dictionaries

        Returns:
            List of page numbers (1-indexed) containing Form 990
        """
        form_990_pages = []

        for page in pages:
            page_num = page.get('page_number', 1)
            text = page.get('text', '')

            if self._is_form_990(text):
                form_990_pages.append(page_num)

        return form_990_pages

    def detect_form_sections(self, pages: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Detect which pages contain which Form 990 sections

        Args:
            pages: List of page data dictionaries

        Returns:
            Dictionary mapping section names to page numbers
        """
        section_pages = {}

        for page in pages:
            page_num = page.get('page_number', 1)
            text = page.get('text', '')

            sections = self._detect_sections(text)
            for section in sections:
                if section not in section_pages:
                    section_pages[section] = page_num

        return section_pages
