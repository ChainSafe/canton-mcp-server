"""
DAML Compiler Safety Integration

Gate 1: DAML Compiler Safety
- Validates DAML code through compilation
- Enforces authorization model
- Guarantees type safety
- Blocks unsafe patterns
- Maintains audit trail

This module provides the foundational safety gate for all DAML code
validation in the Canton MCP server.
"""

from .types import (
    CompilationStatus,
    ErrorCategory,
    CompilationError,
    AuthorizationModel,
    CompilationResult,
    SafetyCheckResult,
    AuditEntry,
)

from .daml_compiler_integration import DamlCompiler
from .safety_checker import SafetyChecker
from .authorization_validator import AuthorizationValidator
from .type_safety_verifier import TypeSafetyVerifier
from .audit_trail import AuditTrail

__all__ = [
    # Types
    "CompilationStatus",
    "ErrorCategory",
    "CompilationError",
    "AuthorizationModel",
    "CompilationResult",
    "SafetyCheckResult",
    "AuditEntry",
    # Classes
    "DamlCompiler",
    "SafetyChecker",
    "AuthorizationValidator",
    "TypeSafetyVerifier",
    "AuditTrail",
]





