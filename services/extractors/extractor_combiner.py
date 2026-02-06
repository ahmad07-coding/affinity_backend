"""
Extractor Combiner - Compares and selects best extraction result
"""
import re
import logging
from typing import List, Dict, Any
from dataclasses import dataclass

from .base_extractor import BasePDFExtractor, ExtractionResult

logger = logging.getLogger(__name__)


@dataclass
class ComparisonMetrics:
    """Metrics for comparing extraction results"""
    extractor_name: str
    text_length: int
    num_tables: int
    num_words: int
    ocr_quality_score: float
    completeness_score: float
    overall_score: float


class ExtractorCombiner:
    """
    Compares results from multiple extractors and selects the best one
    """

    def __init__(self, prefer_pdfminer_if_scanned: bool = True):
        """
        Initialize combiner

        Args:
            prefer_pdfminer_if_scanned: If True, prefer pdfminer for scanned PDFs
        """
        self.prefer_pdfminer_if_scanned = prefer_pdfminer_if_scanned

    def extract_with_best_method(
        self,
        filepath: str,
        extractors: List[BasePDFExtractor]
    ) -> ExtractionResult:
        """
        Extract using multiple extractors and return the best result

        Args:
            filepath: Path to PDF file
            extractors: List of extractors to try

        Returns:
            Best extraction result
        """
        if not extractors:
            raise ValueError("At least one extractor must be provided")

        results = []
        metrics = []

        # Extract with each extractor
        for extractor in extractors:
            try:
                logger.info(f"Extracting with {extractor.name}...")
                result = extractor.extract(filepath)
                results.append(result)

                # Calculate quality metrics
                metric = self._calculate_metrics(result)
                metrics.append(metric)

                logger.info(f"{extractor.name} metrics: "
                          f"text_len={metric.text_length}, "
                          f"tables={metric.num_tables}, "
                          f"ocr_quality={metric.ocr_quality_score:.2f}, "
                          f"overall={metric.overall_score:.2f}")

            except Exception as e:
                logger.error(f"{extractor.name} extraction failed: {e}")
                continue

        if not results:
            raise RuntimeError("All extractors failed")

        # Select best result
        best_result = self._select_best(results, metrics)
        logger.info(f"Selected {best_result.extractor_name} as best extractor")

        return best_result

    def _calculate_metrics(self, result: ExtractionResult) -> ComparisonMetrics:
        """Calculate quality metrics for an extraction result"""

        # Text length (more is generally better)
        text_length = len(result.text)

        # Number of tables
        num_tables = len(result.tables)

        # Number of words
        num_words = len(result.words)

        # OCR quality score (based on artifact detection)
        ocr_quality_score = self._analyze_ocr_quality(result.text)

        # Completeness score (based on text length and word count)
        completeness_score = min(1.0, (text_length / 10000) * 0.5 + (num_words / 1000) * 0.5)

        # Overall score (weighted combination)
        overall_score = (
            completeness_score * 0.5 +
            ocr_quality_score * 0.3 +
            min(1.0, num_tables / 10) * 0.2
        )

        return ComparisonMetrics(
            extractor_name=result.extractor_name,
            text_length=text_length,
            num_tables=num_tables,
            num_words=num_words,
            ocr_quality_score=ocr_quality_score,
            completeness_score=completeness_score,
            overall_score=overall_score
        )

    def _analyze_ocr_quality(self, text: str) -> float:
        """
        Analyze OCR quality based on artifact patterns
        Returns score from 0.0 (poor) to 1.0 (excellent)
        """
        if not text:
            return 0.0

        # Common OCR artifacts
        artifact_patterns = [
            r'<ti \(/1',          # Strange symbol sequences
            r'C c,J :C',          # Garbled characters
            r'[<>(){}/\\]{3,}',   # Multiple special chars in sequence
            r'\s{5,}',            # Excessive spacing
            r'\.{10,}',           # Excessive dots
            r'[A-Z]\s[a-z]\s',    # Single letters with spaces (OCR splitting)
        ]

        artifact_count = 0
        for pattern in artifact_patterns:
            matches = re.findall(pattern, text)
            artifact_count += len(matches)

        # Normalize by text length (artifacts per 1000 chars)
        artifact_density = (artifact_count / len(text)) * 1000 if len(text) > 0 else 0

        # Convert to quality score (lower artifacts = higher quality)
        # 0 artifacts = 1.0 score
        # 10+ artifacts per 1000 chars = 0.0 score
        quality_score = max(0.0, 1.0 - (artifact_density / 10))

        return quality_score

    def _select_best(
        self,
        results: List[ExtractionResult],
        metrics: List[ComparisonMetrics]
    ) -> ExtractionResult:
        """
        Select the best extraction result based on metrics

        Args:
            results: List of extraction results
            metrics: List of corresponding metrics

        Returns:
            Best extraction result
        """
        if len(results) == 1:
            return results[0]

        # Find result with highest overall score
        best_idx = 0
        best_score = metrics[0].overall_score

        for idx, metric in enumerate(metrics[1:], 1):
            # Special case: prefer pdfminer for scanned PDFs (low OCR quality)
            if self.prefer_pdfminer_if_scanned:
                if (metric.extractor_name == "pdfminer" and
                    metric.ocr_quality_score < 0.6 and
                    metrics[best_idx].ocr_quality_score < 0.6):
                    # If both have low OCR quality, prefer pdfminer
                    if metric.overall_score > best_score * 0.9:  # Within 10% is good enough
                        best_idx = idx
                        best_score = metric.overall_score
                        continue

            # Otherwise, select by highest overall score
            if metric.overall_score > best_score:
                best_idx = idx
                best_score = metric.overall_score

        return results[best_idx]

    def compare_extractions(
        self,
        result1: ExtractionResult,
        result2: ExtractionResult
    ) -> Dict[str, Any]:
        """
        Compare two extraction results and return comparison details

        Args:
            result1: First extraction result
            result2: Second extraction result

        Returns:
            Dictionary with comparison details
        """
        metrics1 = self._calculate_metrics(result1)
        metrics2 = self._calculate_metrics(result2)

        return {
            "extractor1": metrics1.extractor_name,
            "extractor2": metrics2.extractor_name,
            "metrics1": {
                "text_length": metrics1.text_length,
                "num_tables": metrics1.num_tables,
                "ocr_quality": metrics1.ocr_quality_score,
                "overall_score": metrics1.overall_score
            },
            "metrics2": {
                "text_length": metrics2.text_length,
                "num_tables": metrics2.num_tables,
                "ocr_quality": metrics2.ocr_quality_score,
                "overall_score": metrics2.overall_score
            },
            "winner": metrics1.extractor_name if metrics1.overall_score > metrics2.overall_score else metrics2.extractor_name
        }
