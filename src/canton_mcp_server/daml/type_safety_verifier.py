"""
DAML Type Safety Verifier

Analyzes and classifies type safety errors from DAML compilation.
"""

import logging
from typing import Dict, List

from .types import CompilationError, CompilationResult, ErrorCategory

logger = logging.getLogger(__name__)


class TypeSafetyVerifier:
    """
    Verify type safety of DAML code through error analysis.

    Classifies compilation errors and determines if code is type-safe.
    """

    def verify_type_safety(self, compilation_result: CompilationResult) -> bool:
        """
        Verify that code is type-safe.

        Args:
            compilation_result: Result of DAML compilation

        Returns:
            True if no type errors found, False otherwise
        """
        if compilation_result.succeeded:
            # Successful compilation means type-safe
            return True

        # Check for type safety errors
        has_type_errors = any(
            error.category == ErrorCategory.TYPE_SAFETY
            for error in compilation_result.errors
        )

        if has_type_errors:
            type_errors = self.get_type_errors(compilation_result.errors)
            logger.warning(
                f"Type safety verification failed: {len(type_errors)} type errors"
            )
            return False

        logger.info("Type safety verified (no type errors)")
        return True

    def classify_errors(
        self, errors: List[CompilationError]
    ) -> Dict[ErrorCategory, List[CompilationError]]:
        """
        Group errors by category.

        Args:
            errors: List of compilation errors

        Returns:
            Dictionary mapping ErrorCategory to list of errors
        """
        result: Dict[ErrorCategory, List[CompilationError]] = {
            category: [] for category in ErrorCategory
        }

        for error in errors:
            result[error.category].append(error)

        logger.debug(
            f"Error classification: "
            + ", ".join(f"{cat.value}={len(errs)}" for cat, errs in result.items())
        )

        return result

    def get_type_errors(
        self, errors: List[CompilationError]
    ) -> List[CompilationError]:
        """
        Filter for type safety errors only.

        Args:
            errors: List of compilation errors

        Returns:
            List of type safety errors
        """
        type_errors = [
            error for error in errors if error.category == ErrorCategory.TYPE_SAFETY
        ]

        logger.debug(f"Found {len(type_errors)} type errors out of {len(errors)} total")

        return type_errors

    def get_authorization_errors(
        self, errors: List[CompilationError]
    ) -> List[CompilationError]:
        """
        Filter for authorization errors only.

        Args:
            errors: List of compilation errors

        Returns:
            List of authorization errors
        """
        auth_errors = [
            error
            for error in errors
            if error.category == ErrorCategory.AUTHORIZATION
        ]

        logger.debug(
            f"Found {len(auth_errors)} authorization errors out of {len(errors)} total"
        )

        return auth_errors

    def get_error_summary(self, errors: List[CompilationError]) -> str:
        """
        Generate human-readable summary of errors.

        Args:
            errors: List of compilation errors

        Returns:
            Formatted error summary string
        """
        if not errors:
            return "No errors"

        classified = self.classify_errors(errors)

        summary_lines = [f"Total errors: {len(errors)}"]

        for category in ErrorCategory:
            cat_errors = classified[category]
            if cat_errors:
                summary_lines.append(f"  {category.value}: {len(cat_errors)}")

        # Add first few error messages
        summary_lines.append("\nFirst errors:")
        for i, error in enumerate(errors[:3], 1):
            summary_lines.append(f"  {i}. {error.file_path}:{error.line} - {error.message[:80]}...")

        if len(errors) > 3:
            summary_lines.append(f"  ... and {len(errors) - 3} more")

        return "\n".join(summary_lines)

    def is_critical_error(self, error: CompilationError) -> bool:
        """
        Determine if error is critical (blocks safety).

        All authorization and type errors are critical.
        Syntax errors are critical.
        Warnings (if any) are not critical.

        Args:
            error: Compilation error

        Returns:
            True if critical, False otherwise
        """
        critical_categories = {
            ErrorCategory.AUTHORIZATION,
            ErrorCategory.TYPE_SAFETY,
            ErrorCategory.SYNTAX,
        }

        return error.category in critical_categories

