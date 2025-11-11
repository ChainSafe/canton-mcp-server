"""
Tests for TypeSafetyVerifier

Unit tests for DAML type safety error analysis.
"""

import pytest

from canton_mcp_server.daml.type_safety_verifier import TypeSafetyVerifier
from canton_mcp_server.daml.types import (
    CompilationError,
    CompilationResult,
    CompilationStatus,
    ErrorCategory,
)


class TestTypeSafetyVerifier:
    """Test TypeSafetyVerifier functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.verifier = TypeSafetyVerifier()

    def test_verify_type_safety_success(self):
        """Test type safety verification with successful compilation"""
        result = CompilationResult(status=CompilationStatus.SUCCESS, exit_code=0)

        type_safe = self.verifier.verify_type_safety(result)
        assert type_safe is True

    def test_verify_type_safety_no_type_errors(self):
        """Test type safety with non-type errors"""
        auth_error = CompilationError(
            file_path="Main.daml",
            line=10,
            column=5,
            category=ErrorCategory.AUTHORIZATION,
            message="Missing signatory",
            raw_error="",
        )

        result = CompilationResult(
            status=CompilationStatus.FAILED, exit_code=1, errors=[auth_error]
        )

        type_safe = self.verifier.verify_type_safety(result)
        assert type_safe is True  # No TYPE errors, so type-safe

    def test_verify_type_safety_with_type_errors(self):
        """Test type safety fails with type errors"""
        type_error = CompilationError(
            file_path="Main.daml",
            line=15,
            column=10,
            category=ErrorCategory.TYPE_SAFETY,
            message="Couldn't match expected type",
            raw_error="",
        )

        result = CompilationResult(
            status=CompilationStatus.FAILED, exit_code=1, errors=[type_error]
        )

        type_safe = self.verifier.verify_type_safety(result)
        assert type_safe is False

    def test_classify_errors_empty(self):
        """Test error classification with no errors"""
        errors = []
        classified = self.verifier.classify_errors(errors)

        assert classified[ErrorCategory.AUTHORIZATION] == []
        assert classified[ErrorCategory.TYPE_SAFETY] == []
        assert classified[ErrorCategory.SYNTAX] == []
        assert classified[ErrorCategory.OTHER] == []

    def test_classify_errors_mixed(self):
        """Test error classification with mixed error types"""
        errors = [
            CompilationError(
                file_path="Main.daml",
                line=10,
                column=5,
                category=ErrorCategory.AUTHORIZATION,
                message="Auth error 1",
                raw_error="",
            ),
            CompilationError(
                file_path="Main.daml",
                line=20,
                column=10,
                category=ErrorCategory.TYPE_SAFETY,
                message="Type error 1",
                raw_error="",
            ),
            CompilationError(
                file_path="Main.daml",
                line=25,
                column=3,
                category=ErrorCategory.TYPE_SAFETY,
                message="Type error 2",
                raw_error="",
            ),
            CompilationError(
                file_path="Main.daml",
                line=30,
                column=1,
                category=ErrorCategory.SYNTAX,
                message="Syntax error 1",
                raw_error="",
            ),
        ]

        classified = self.verifier.classify_errors(errors)

        assert len(classified[ErrorCategory.AUTHORIZATION]) == 1
        assert len(classified[ErrorCategory.TYPE_SAFETY]) == 2
        assert len(classified[ErrorCategory.SYNTAX]) == 1
        assert len(classified[ErrorCategory.OTHER]) == 0

    def test_get_type_errors_filter(self):
        """Test filtering for type errors only"""
        errors = [
            CompilationError(
                file_path="Main.daml",
                line=10,
                column=5,
                category=ErrorCategory.AUTHORIZATION,
                message="Auth error",
                raw_error="",
            ),
            CompilationError(
                file_path="Main.daml",
                line=20,
                column=10,
                category=ErrorCategory.TYPE_SAFETY,
                message="Type error 1",
                raw_error="",
            ),
            CompilationError(
                file_path="Main.daml",
                line=25,
                column=3,
                category=ErrorCategory.TYPE_SAFETY,
                message="Type error 2",
                raw_error="",
            ),
        ]

        type_errors = self.verifier.get_type_errors(errors)

        assert len(type_errors) == 2
        assert all(e.category == ErrorCategory.TYPE_SAFETY for e in type_errors)

    def test_get_authorization_errors_filter(self):
        """Test filtering for authorization errors only"""
        errors = [
            CompilationError(
                file_path="Main.daml",
                line=10,
                column=5,
                category=ErrorCategory.AUTHORIZATION,
                message="Auth error 1",
                raw_error="",
            ),
            CompilationError(
                file_path="Main.daml",
                line=15,
                column=5,
                category=ErrorCategory.AUTHORIZATION,
                message="Auth error 2",
                raw_error="",
            ),
            CompilationError(
                file_path="Main.daml",
                line=20,
                column=10,
                category=ErrorCategory.TYPE_SAFETY,
                message="Type error",
                raw_error="",
            ),
        ]

        auth_errors = self.verifier.get_authorization_errors(errors)

        assert len(auth_errors) == 2
        assert all(e.category == ErrorCategory.AUTHORIZATION for e in auth_errors)

    def test_get_error_summary_no_errors(self):
        """Test error summary with no errors"""
        errors = []
        summary = self.verifier.get_error_summary(errors)

        assert summary == "No errors"

    def test_get_error_summary_few_errors(self):
        """Test error summary with few errors"""
        errors = [
            CompilationError(
                file_path="Main.daml",
                line=10,
                column=5,
                category=ErrorCategory.AUTHORIZATION,
                message="Missing signatory",
                raw_error="",
            ),
            CompilationError(
                file_path="Main.daml",
                line=20,
                column=10,
                category=ErrorCategory.TYPE_SAFETY,
                message="Type mismatch",
                raw_error="",
            ),
        ]

        summary = self.verifier.get_error_summary(errors)

        assert "Total errors: 2" in summary
        assert "authorization: 1" in summary
        assert "type_safety: 1" in summary
        assert "Main.daml:10" in summary
        assert "Main.daml:20" in summary

    def test_get_error_summary_many_errors(self):
        """Test error summary truncates long lists"""
        errors = [
            CompilationError(
                file_path="Main.daml",
                line=i,
                column=1,
                category=ErrorCategory.OTHER,
                message=f"Error {i}",
                raw_error="",
            )
            for i in range(10)
        ]

        summary = self.verifier.get_error_summary(errors)

        assert "Total errors: 10" in summary
        assert "... and 7 more" in summary  # Shows first 3 + "... and 7 more"

    def test_is_critical_error_authorization(self):
        """Test authorization errors are critical"""
        error = CompilationError(
            file_path="Main.daml",
            line=10,
            column=5,
            category=ErrorCategory.AUTHORIZATION,
            message="Missing signatory",
            raw_error="",
        )

        assert self.verifier.is_critical_error(error) is True

    def test_is_critical_error_type_safety(self):
        """Test type errors are critical"""
        error = CompilationError(
            file_path="Main.daml",
            line=10,
            column=5,
            category=ErrorCategory.TYPE_SAFETY,
            message="Type mismatch",
            raw_error="",
        )

        assert self.verifier.is_critical_error(error) is True

    def test_is_critical_error_syntax(self):
        """Test syntax errors are critical"""
        error = CompilationError(
            file_path="Main.daml",
            line=10,
            column=5,
            category=ErrorCategory.SYNTAX,
            message="Parse error",
            raw_error="",
        )

        assert self.verifier.is_critical_error(error) is True

    def test_is_critical_error_other(self):
        """Test OTHER errors might not be critical"""
        error = CompilationError(
            file_path="Main.daml",
            line=10,
            column=5,
            category=ErrorCategory.OTHER,
            message="Some warning",
            raw_error="",
        )

        # Currently OTHER errors are not classified as critical
        assert self.verifier.is_critical_error(error) is False





