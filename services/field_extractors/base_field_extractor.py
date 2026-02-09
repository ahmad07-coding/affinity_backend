"""
Base classes for field-specific extraction
Each field extractor knows how to extract, validate, and score confidence for a specific field
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
import re


@dataclass
class FieldExtractionResult:
    """Result from extracting a single field"""
    field_name: str
    value: Optional[str]
    confidence: float  # 0.0 to 1.0
    source: str  # "table", "text_pattern", "coordinate", "ocr"
    validation_errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Check if extraction is valid (has value and no critical errors)"""
        return self.value is not None and len(self.validation_errors) == 0


class BaseFieldExtractor(ABC):
    """
    Abstract base class for field extractors
    Each field type (EIN, monetary, etc.) should implement this
    """

    def __init__(self):
        self.expected_section: str = ""  # e.g., "Part VIII", "Part I"
        self.expected_type: str = ""     # e.g., "currency", "ein", "percentage"
        self.validation_rules: List[Callable] = []

    @abstractmethod
    def extract(self, text: str, tables: List[Any], page_metadata: List[Any]) -> FieldExtractionResult:
        """
        Extract the field value using multiple strategies

        Args:
            text: Full text from PDF
            tables: List of normalized tables
            page_metadata: List of page metadata from document analyzer

        Returns:
            FieldExtractionResult with value and confidence
        """
        pass

    @abstractmethod
    def validate(self, value: str) -> tuple[bool, float, List[str]]:
        """
        Validate the extracted value

        Args:
            value: Extracted value to validate

        Returns:
            Tuple of (is_valid, confidence_adjustment, error_messages)
        """
        pass

    def _extract_with_fallback(
        self,
        strategies: List[Callable],
        field_name: str
    ) -> FieldExtractionResult:
        """
        Try multiple extraction strategies in order, return first successful one

        Args:
            strategies: List of extraction functions to try
            field_name: Name of the field being extracted

        Returns:
            Best FieldExtractionResult
        """
        best_result = None
        best_confidence = 0.0

        for strategy_func in strategies:
            try:
                result = strategy_func()
                if result and result.value is not None:
                    if result.confidence > best_confidence:
                        best_result = result
                        best_confidence = result.confidence

                    # If we got high confidence, no need to try more strategies
                    if result.confidence >= 0.9:
                        break
            except Exception as e:
                continue

        if best_result:
            return best_result

        # No successful extraction
        return FieldExtractionResult(
            field_name=field_name,
            value=None,
            confidence=0.0,
            source="none",
            validation_errors=["Field not found"]
        )

    def _is_valid_monetary_amount(self, value: str) -> bool:
        """
        Check if value is a valid monetary amount
        Reuses logic from existing field_extractor.py
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
        if len(clean) < 4:
            return False

        try:
            num = int(clean)
            if num < 100:
                return False
        except ValueError:
            return False

        return True

    def _normalize_monetary_value(self, value: str) -> str:
        """Normalize monetary value format"""
        if not value:
            return value

        # Remove extra whitespace
        value = value.strip()

        # Strip trailing dot: "384,948." → "384,948"
        # IRS trailing dot means "no cents" - just remove it
        value = value.rstrip('.')

        return value
