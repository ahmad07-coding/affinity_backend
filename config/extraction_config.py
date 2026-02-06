"""
Extraction Configuration
Centralized configuration for PDF extraction, validation, and confidence scoring
"""

EXTRACTION_CONFIG = {
    # Confidence thresholds
    "confidence_thresholds": {
        "production": 0.70,  # Minimum score for production use
        "development": 0.50,  # Lower threshold for development/testing
        "critical_fields": 0.50,  # Minimum for critical fields (EIN, gross receipts)
    },

    # Extractor selection rules
    "extractor_selection": {
        "prefer_pdfminer_if_scanned": True,  # Use pdfminer.six for scanned PDFs
        "ocr_quality_threshold": 0.6,  # Below this, consider PDF as scanned
        "fast_fail": True,  # Skip second extractor if first one is good enough
    },

    # Table normalization settings
    "table_normalization": {
        # OCR artifact patterns to remove
        "artifact_patterns": [
            r'<ti \(/1',      # Strange symbol sequences from 2022 PDF
            r'C c,J :C',      # Garbled characters from 2022 PDF
            r'\.{5,}',        # Excessive dots (dot leaders)
            r'~{5,}',         # Excessive tildes from 2024 PDF
            r'[<>(){}/\\]{3,}',  # Multiple special chars
        ],

        # Spacing fix patterns (pattern, replacement)
        "spacing_fix_patterns": [
            # Fix EIN with spaces: "3 9 - 0 8 0 6 2 5 1" → "39-0806251"
            (r'(\d)\s+(\d)\s*-\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)',
             r'\1\2-\3\4\5\6\7\8\9'),
        ],

        # Decimal normalization
        "decimal_normalization": True,  # "384,948." → "384,948.00"

        # Column header fixes
        "header_fixes": {
            "(Cl)": "(C)",  # OCR typo in 2022 PDF
            "ia-1f": "1a-1f",  # OCR typo
        },
    },

    # Validation rules
    "validation_rules": {
        # Revenue consistency check
        "revenue_tolerance_percent": 2.0,  # ±2% tolerance for cross-validation

        # Expense allocation check
        "expense_allocation_exact": True,  # Part IX totals must match exactly

        # Required fields
        "require_ein": True,
        "require_gross_receipts": True,
        "require_total_revenue": True,
        "require_total_assets": True,
    },

    # Confidence scoring weights
    "confidence_weights": {
        "extraction_source": 0.40,  # Weight for extraction method quality
        "validation_score": 0.30,   # Weight for field validation
        "cross_validation": 0.20,   # Weight for cross-field consistency
        "ocr_quality": 0.10,        # Weight for OCR quality
    },

    # Critical fields (used for overall confidence calculation)
    "critical_fields": [
        "employer_identification_number",
        "gross_receipts",
        "total_revenue",
        "total_contributions",
        "total_assets",
        "net_assets_or_fund_balances",
        "total_functional_expenses_a",
    ],

    # Field extraction strategies (in order of preference)
    "extraction_strategies": [
        "table_based",      # Primary: Extract from normalized tables
        "coordinate_based",  # Secondary: Use word bounding boxes
        "text_pattern",      # Fallback: Enhanced regex with context
    ],
}
