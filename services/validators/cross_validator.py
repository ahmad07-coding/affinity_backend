"""
Cross-Field Validation
Validates consistency across related fields in Form 990
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import logging

from config.extraction_config import EXTRACTION_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result from cross-field validation"""
    passed: bool
    confidence_adjustment: float  # Multiplier for confidence (0-1)
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]


class CrossValidator:
    """Validates consistency across related Form 990 fields"""

    def __init__(self, config: Dict = None):
        """
        Initialize cross validator

        Args:
            config: Configuration dict (uses EXTRACTION_CONFIG if not provided)
        """
        self.config = config or EXTRACTION_CONFIG
        self.tolerance_percent = self.config['validation_rules']['revenue_tolerance_percent']

    def validate_all(
        self,
        page1_fields: Any,
        part8_fields: Any,
        part9_fields: Any
    ) -> ValidationResult:
        """
        Run all cross-validation checks

        Args:
            page1_fields: Page 1 fields (Page1Fields or dict)
            part8_fields: Part VIII fields (PartVIIIFields or dict)
            part9_fields: Part IX fields (PartIXFields or dict)

        Returns:
            ValidationResult with overall validation status
        """
        errors = []
        warnings = []
        passed_checks = 0
        total_checks = 0

        # Revenue consistency
        revenue_result = self.validate_revenue_consistency(page1_fields, part8_fields)
        total_checks += 1
        if revenue_result.passed:
            passed_checks += 1
        errors.extend(revenue_result.errors)
        warnings.extend(revenue_result.warnings)

        # Expense allocation
        expense_result = self.validate_expense_allocation(part9_fields)
        total_checks += 1
        if expense_result.passed:
            passed_checks += 1
        errors.extend(expense_result.errors)
        warnings.extend(expense_result.warnings)

        # Balance sheet
        balance_result = self.validate_balance_sheet(page1_fields)
        total_checks += 1
        if balance_result.passed:
            passed_checks += 1
        errors.extend(balance_result.errors)
        warnings.extend(balance_result.warnings)

        # Calculate confidence adjustment
        check_pass_rate = passed_checks / total_checks if total_checks > 0 else 0.0
        confidence_adjustment = 0.5 + (check_pass_rate * 0.5)  # Range: 0.5 to 1.0

        return ValidationResult(
            passed=len(errors) == 0,
            confidence_adjustment=confidence_adjustment,
            errors=errors,
            warnings=warnings,
            metadata={
                'checks_passed': passed_checks,
                'total_checks': total_checks,
                'pass_rate': check_pass_rate
            }
        )

    def validate_revenue_consistency(
        self,
        page1_fields: Any,
        part8_fields: Any
    ) -> ValidationResult:
        """
        Validate revenue consistency between Page 1 and Part VIII

        Checks:
        - Page1.total_contributions ≈ Part8.contributions_total
        - Page1.total_revenue ≈ Part8.total_revenue
        """
        errors = []
        warnings = []

        # Get values (handle both dict and object)
        page1_contrib = self._get_value(page1_fields, 'total_contributions')
        part8_contrib = self._get_value(part8_fields, 'contributions_total')
        page1_revenue = self._get_value(page1_fields, 'total_revenue')
        part8_revenue = self._get_value(part8_fields, 'total_revenue')

        # Check contributions consistency
        if page1_contrib and part8_contrib:
            if not self._values_match(page1_contrib, part8_contrib):
                errors.append(
                    f"Contributions mismatch: Page1={page1_contrib}, Part8={part8_contrib}"
                )
        elif page1_contrib or part8_contrib:
            warnings.append("Contributions found in only one location")

        # Check revenue consistency
        if page1_revenue and part8_revenue:
            if not self._values_match(page1_revenue, part8_revenue):
                errors.append(
                    f"Total revenue mismatch: Page1={page1_revenue}, Part8={part8_revenue}"
                )
        elif page1_revenue or part8_revenue:
            warnings.append("Total revenue found in only one location")

        return ValidationResult(
            passed=len(errors) == 0,
            confidence_adjustment=1.0 if len(errors) == 0 else 0.5,
            errors=errors,
            warnings=warnings,
            metadata={}
        )

    def validate_expense_allocation(self, part9_fields: Any) -> ValidationResult:
        """
        Validate expense allocation in Part IX

        Check: total_a ≈ total_b + total_c + total_d
        """
        errors = []
        warnings = []

        # Get values
        total_a = self._get_value(part9_fields, 'total_functional_expenses_a')
        total_b = self._get_value(part9_fields, 'total_functional_expenses_b')
        total_c = self._get_value(part9_fields, 'total_functional_expenses_c')
        total_d = self._get_value(part9_fields, 'total_functional_expenses_d')

        if total_a and total_b and total_c and total_d:
            a_num = self._parse_number(total_a)
            b_num = self._parse_number(total_b)
            c_num = self._parse_number(total_c)
            d_num = self._parse_number(total_d)

            if all(x is not None for x in [a_num, b_num, c_num, d_num]):
                calculated_total = b_num + c_num + d_num
                difference = abs(a_num - calculated_total)

                # Should match exactly (or very close due to rounding)
                if difference > 10:  # Allow $10 rounding difference
                    errors.append(
                        f"Expense allocation mismatch: "
                        f"Total A={a_num}, B+C+D={calculated_total}, diff={difference}"
                    )

        return ValidationResult(
            passed=len(errors) == 0,
            confidence_adjustment=1.0 if len(errors) == 0 else 0.7,
            errors=errors,
            warnings=warnings,
            metadata={}
        )

    def validate_balance_sheet(self, page1_fields: Any) -> ValidationResult:
        """
        Validate balance sheet equation

        Check: total_assets - total_liabilities ≈ net_assets
        """
        errors = []
        warnings = []

        # Get values
        total_assets = self._get_value(page1_fields, 'total_assets')
        total_liabilities = self._get_value(page1_fields, 'total_liabilities')
        net_assets = self._get_value(page1_fields, 'net_assets_or_fund_balances')

        if total_assets and total_liabilities and net_assets:
            assets_num = self._parse_number(total_assets)
            liab_num = self._parse_number(total_liabilities)
            net_num = self._parse_number(net_assets)

            if all(x is not None for x in [assets_num, liab_num, net_num]):
                calculated_net = assets_num - liab_num
                difference = abs(net_num - calculated_net)

                # Should match exactly
                if difference > 10:  # Allow $10 rounding
                    errors.append(
                        f"Balance sheet mismatch: "
                        f"Assets={assets_num}, Liab={liab_num}, Net={net_num}, "
                        f"Calculated={calculated_net}, diff={difference}"
                    )

        return ValidationResult(
            passed=len(errors) == 0,
            confidence_adjustment=1.0 if len(errors) == 0 else 0.6,
            errors=errors,
            warnings=warnings,
            metadata={}
        )

    def _get_value(self, obj: Any, field_name: str) -> Optional[str]:
        """Get value from object or dict"""
        if obj is None:
            return None

        # Try dict access
        if isinstance(obj, dict):
            return obj.get(field_name)

        # Try attribute access
        if hasattr(obj, field_name):
            return getattr(obj, field_name)

        return None

    def _parse_number(self, value: str) -> Optional[float]:
        """Parse monetary value to float"""
        if not value:
            return None

        try:
            # Remove commas and parse
            clean = value.replace(',', '')
            return float(clean)
        except (ValueError, AttributeError):
            return None

    def _values_match(self, value1: str, value2: str) -> bool:
        """Check if two monetary values match within tolerance"""
        num1 = self._parse_number(value1)
        num2 = self._parse_number(value2)

        if num1 is None or num2 is None:
            return False

        # Calculate percentage difference
        avg = (num1 + num2) / 2
        if avg == 0:
            return num1 == num2

        diff_percent = abs(num1 - num2) / avg * 100

        return diff_percent <= self.tolerance_percent
