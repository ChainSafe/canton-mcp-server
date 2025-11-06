"""
DAML Compiler Safety Types

Data models for DAML compilation, safety checking, and audit trails.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class CompilationStatus(Enum):
    """Status of DAML compilation attempt"""

    SUCCESS = "success"
    FAILED = "failed"  # Code errors (auth, type, syntax)
    ERROR = "error"  # System errors (missing daml, timeout, etc.)


class ErrorCategory(Enum):
    """Category of compilation error"""

    AUTHORIZATION = "authorization"  # Missing signatory, controller issues
    TYPE_SAFETY = "type_safety"  # Type mismatches, missing instances
    SYNTAX = "syntax"  # Parse errors
    OTHER = "other"  # Uncategorized errors


@dataclass
class CompilationError:
    """Single compilation error from DAML compiler"""

    file_path: str
    line: int
    column: int
    category: ErrorCategory
    message: str
    raw_error: str

    def __str__(self) -> str:
        return f"{self.file_path}:{self.line}:{self.column}: [{self.category.value}] {self.message}"


@dataclass
class AuthorizationModel:
    """Extracted authorization model from DAML template"""

    template_name: str
    signatories: List[str] = field(default_factory=list)
    observers: List[str] = field(default_factory=list)
    controllers: Dict[str, List[str]] = field(
        default_factory=dict
    )  # choice -> controllers

    def is_valid(self) -> bool:
        """Check if authorization model is sound"""
        # At least one signatory is required
        if not self.signatories:
            return False

        # All controllers should be parties (signatories or observers)
        all_parties = set(self.signatories + self.observers)
        for choice, choice_controllers in self.controllers.items():
            for controller in choice_controllers:
                if controller not in all_parties:
                    return False

        return True

    def __str__(self) -> str:
        lines = [f"Template: {self.template_name}"]
        if self.signatories:
            lines.append(f"  Signatories: {', '.join(self.signatories)}")
        if self.observers:
            lines.append(f"  Observers: {', '.join(self.observers)}")
        if self.controllers:
            lines.append("  Choices:")
            for choice, controllers in self.controllers.items():
                lines.append(f"    {choice}: {', '.join(controllers)}")
        return "\n".join(lines)


@dataclass
class CompilationResult:
    """Result of DAML compilation attempt"""

    status: CompilationStatus
    errors: List[CompilationError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    compilation_time_ms: int = 0

    @property
    def succeeded(self) -> bool:
        """Check if compilation succeeded"""
        return self.status == CompilationStatus.SUCCESS

    @property
    def has_authorization_errors(self) -> bool:
        """Check if any authorization errors present"""
        return any(e.category == ErrorCategory.AUTHORIZATION for e in self.errors)

    @property
    def has_type_errors(self) -> bool:
        """Check if any type safety errors present"""
        return any(e.category == ErrorCategory.TYPE_SAFETY for e in self.errors)

    def get_errors_by_category(self) -> Dict[ErrorCategory, List[CompilationError]]:
        """Group errors by category"""
        result: Dict[ErrorCategory, List[CompilationError]] = {
            category: [] for category in ErrorCategory
        }
        for error in self.errors:
            result[error.category].append(error)
        return result


@dataclass
class SafetyCheckResult:
    """Gate 1 safety check result"""

    passed: bool
    compilation_result: CompilationResult
    authorization_model: Optional[AuthorizationModel] = None
    blocked_reason: Optional[str] = None
    safety_certificate: Optional[str] = None
    audit_id: str = ""

    @property
    def is_safe(self) -> bool:
        """Alias for passed"""
        return self.passed

    def __str__(self) -> str:
        status = "✅ SAFE" if self.passed else "❌ BLOCKED"
        lines = [f"Safety Check: {status}"]
        if self.blocked_reason:
            lines.append(f"Reason: {self.blocked_reason}")
        if self.authorization_model:
            lines.append(str(self.authorization_model))
        if self.audit_id:
            lines.append(f"Audit ID: {self.audit_id}")
        return "\n".join(lines)


@dataclass
class AuditEntry:
    """Audit trail entry for compilation"""

    audit_id: str
    timestamp: datetime
    code_hash: str
    module_name: str
    status: CompilationStatus
    errors: List[CompilationError] = field(default_factory=list)
    authorization_model: Optional[AuthorizationModel] = None
    blocked: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            "audit_id": self.audit_id,
            "timestamp": self.timestamp.isoformat(),
            "code_hash": self.code_hash,
            "module_name": self.module_name,
            "status": self.status.value,
            "errors": [
                {
                    "file": e.file_path,
                    "line": e.line,
                    "column": e.column,
                    "category": e.category.value,
                    "message": e.message,
                }
                for e in self.errors
            ],
            "authorization_model": (
                {
                    "template": self.authorization_model.template_name,
                    "signatories": self.authorization_model.signatories,
                    "observers": self.authorization_model.observers,
                    "controllers": self.authorization_model.controllers,
                }
                if self.authorization_model
                else None
            ),
            "blocked": self.blocked,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AuditEntry":
        """Create from dictionary"""
        errors = [
            CompilationError(
                file_path=e["file"],
                line=e["line"],
                column=e["column"],
                category=ErrorCategory(e["category"]),
                message=e["message"],
                raw_error=e.get("raw_error", ""),
            )
            for e in data.get("errors", [])
        ]

        auth_model = None
        if data.get("authorization_model"):
            am = data["authorization_model"]
            auth_model = AuthorizationModel(
                template_name=am["template"],
                signatories=am.get("signatories", []),
                observers=am.get("observers", []),
                controllers=am.get("controllers", {}),
            )

        return cls(
            audit_id=data["audit_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            code_hash=data["code_hash"],
            module_name=data["module_name"],
            status=CompilationStatus(data["status"]),
            errors=errors,
            authorization_model=auth_model,
            blocked=data.get("blocked", False),
        )




