"""
Confidence Scoring System
Calculates per-field and overall confidence scores with fail-fast thresholds
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

from config.extraction_config import EXTRACTION_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class FieldConfidence:
    """Confidence breakdown for a single field"""
    field_name: str
    value: Optional[str]
    confidence: float
    confidence_factors: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    source: str = "unknown"


@dataclass
class DocumentConfidence:
    """Overall document confidence with field-level breakdown"""
    overall_score: float
    field_scores: Dict[str, FieldConfidence]
    pass_threshold: bool
    critical_failures: List[str] = field(default_factory=list)
    metadata: Dict[str, any] = field(default_factory=dict)


class ConfidenceScorer:
    """Calculates confidence scores for extracted fields"""

    def __init__(self, config: Dict = None):
        """
        Initialize confidence scorer

        Args:
            config: Configuration dict (uses EXTRACTION_CONFIG if not provided)
        """
        self.config = config or EXTRACTION_CONFIG
        self.weights = self.config['confidence_weights']
        self.critical_fields = self.config['critical_fields']
        self.threshold = self.config['confidence_thresholds']['production']
        self.critical_threshold = self.config['confidence_thresholds']['critical_fields']

    def calculate_field_confidence(
        self,
        field_name: str,
        value: Optional[str],
        extraction_source: str,
        validation_score: float,
        cross_val_score: float,
        ocr_quality: float,
        validation_errors: List[str] = None
    ) -> FieldConfidence:
        """
        Calculate confidence for a single field

        Args:
            field_name: Name of the field
            value: Extracted value
            extraction_source: How it was extracted ("table", "text_pattern", etc.)
            validation_score: Score from field validation (0-1)
            cross_val_score: Score from cross-validation (0-1)
            ocr_quality: OCR quality score (0-1)
            validation_errors: List of validation errors

        Returns:
            FieldConfidence with breakdown
        """
        # Source confidence
        source_confidence = self._score_extraction_source(extraction_source)

        # Calculate weighted confidence
        factors = {
            'extraction_source': source_confidence,
            'validation': validation_score,
            'cross_validation': cross_val_score,
            'ocr_quality': ocr_quality
        }

        weighted_confidence = (
            source_confidence * self.weights['extraction_source'] +
            validation_score * self.weights['validation_score'] +
            cross_val_score * self.weights['cross_validation'] +
            ocr_quality * self.weights['ocr_quality']
        )

        # Collect warnings
        warnings = []
        if value is None:
            warnings.append("Field not found")
        if validation_errors:
            warnings.extend(validation_errors)
        if weighted_confidence < self.critical_threshold and field_name in self.critical_fields:
            warnings.append(f"Critical field below threshold ({weighted_confidence:.2f} < {self.critical_threshold})")

        return FieldConfidence(
            field_name=field_name,
            value=value,
            confidence=weighted_confidence,
            confidence_factors=factors,
            warnings=warnings,
            source=extraction_source
        )

    def calculate_overall_confidence(
        self,
        field_confidences: Dict[str, FieldConfidence],
        validation_result: any = None
    ) -> DocumentConfidence:
        """
        Calculate overall document confidence

        Args:
            field_confidences: Dictionary of field name to FieldConfidence
            validation_result: Cross-validation result

        Returns:
            DocumentConfidence with overall score
        """
        if not field_confidences:
            return DocumentConfidence(
                overall_score=0.0,
                field_scores={},
                pass_threshold=False,
                critical_failures=["No fields extracted"]
            )

        # Extract critical field scores
        critical_scores = []
        critical_failures = []

        for field_name in self.critical_fields:
            if field_name in field_confidences:
                fc = field_confidences[field_name]
                if fc.value is not None:
                    critical_scores.append(fc.confidence)
                else:
                    critical_failures.append(f"Critical field missing: {field_name}")

                # Check if critical field is below threshold
                if fc.confidence < self.critical_threshold:
                    critical_failures.append(
                        f"Critical field {field_name} below threshold: {fc.confidence:.2f}"
                    )

        # Calculate overall score as weighted average of critical fields
        if critical_scores:
            overall_score = sum(critical_scores) / len(critical_scores)
        else:
            overall_score = 0.0

        # Apply penalty for missing critical fields
        missing_count = len(self.critical_fields) - len(critical_scores)
        penalty = missing_count * 0.1
        overall_score = max(0.0, overall_score - penalty)

        # Check if passes threshold
        pass_threshold = (
            overall_score >= self.threshold and
            len(critical_failures) == 0
        )

        return DocumentConfidence(
            overall_score=overall_score,
            field_scores=field_confidences,
            pass_threshold=pass_threshold,
            critical_failures=critical_failures,
            metadata={
                'critical_field_count': len(critical_scores),
                'missing_critical_fields': missing_count,
                'threshold_used': self.threshold
            }
        )

    def _score_extraction_source(self, source: str) -> float:
        """Score extraction source quality"""
        source_scores = {
            'table': 1.0,
            'text_pattern': 0.7,
            'text_pattern_ocr_fixed': 0.5,
            'coordinate': 0.8,
            'ocr': 0.4,
            'none': 0.0,
            'unknown': 0.3
        }
        return source_scores.get(source, 0.5)

    def should_reject(self, doc_confidence: DocumentConfidence) -> bool:
        """
        Determine if extraction should be rejected (fail-fast)

        Args:
            doc_confidence: Document confidence result

        Returns:
            True if should reject, False otherwise
        """
        return not doc_confidence.pass_threshold

    def get_rejection_reason(self, doc_confidence: DocumentConfidence) -> str:
        """Get human-readable rejection reason"""
        if doc_confidence.overall_score < self.threshold:
            return (
                f"Overall confidence ({doc_confidence.overall_score:.2f}) "
                f"below threshold ({self.threshold})"
            )

        if doc_confidence.critical_failures:
            return "Critical field failures: " + ", ".join(doc_confidence.critical_failures)

        return "Unknown rejection reason"
