"""
DAML Safety Checker

Gate 1: DAML Compiler Safety
Orchestrates safety validation through compilation.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional

from .audit_trail import AuditTrail
from .authorization_validator import AuthorizationValidator
from .daml_compiler_integration import DamlCompiler
from .policy_checker import check_against_policies
from .type_safety_verifier import TypeSafetyVerifier
from .types import CompilationStatus, SafetyCheckResult
from ..core.resources.base import ResourceCategory
from ..core.resources.loader import ResourceLoader, get_loader

logger = logging.getLogger(__name__)


class SafetyChecker:
    """
    Gate 1: DAML Compiler Safety

    Orchestrates complete safety validation:
    1. Compile with DAML compiler
    2. Extract authorization model
    3. Verify type safety
    4. Generate safety certificate
    5. Maintain audit trail
    6. Block unsafe patterns
    """

    def __init__(
        self,
        compiler: Optional[DamlCompiler] = None,
        auth_validator: Optional[AuthorizationValidator] = None,
        type_verifier: Optional[TypeSafetyVerifier] = None,
        audit_trail: Optional[AuditTrail] = None,
        resource_loader: Optional[ResourceLoader] = None,
    ):
        """
        Initialize safety checker with validators.

        Args:
            compiler: DAML compiler (creates default if None)
            auth_validator: Authorization validator (creates default if None)
            type_verifier: Type safety verifier (creates default if None)
            audit_trail: Audit trail (creates default if None)
            resource_loader: Resource loader for canonical policies (creates default if None)
        """
        from ..env import get_env
        sdk_version = get_env("DAML_SDK_VERSION", "3.4.0-snapshot.20251013.0")
        self.compiler = compiler or DamlCompiler(sdk_version=sdk_version)
        self.auth_validator = auth_validator or AuthorizationValidator()
        self.type_verifier = type_verifier or TypeSafetyVerifier()
        self.audit_trail = audit_trail or AuditTrail()
        self.resource_loader = resource_loader or get_loader()

        logger.info("Safety checker initialized (Gate 1: DAML Compiler Safety)")

    async def check_pattern_safety(
        self, code: str, module_name: str = "Main"
    ) -> SafetyCheckResult:
        """
        Gate 1: DAML Compiler Safety Check

        Complete safety validation flow:
        1. Compile code (strict mode)
        2. If failed: block, log, return
        3. Extract authorization model
        4. Verify type safety
        5. Validate authorization model
        6. Generate safety certificate
        7. Log to audit trail
        8. Return result

        Args:
            code: DAML source code to validate
            module_name: Module name (default: "Main")

        Returns:
            SafetyCheckResult with pass/fail and details
        """
        logger.info(f"Starting safety check for module: {module_name}")

        # Generate code hash for audit trail
        code_hash = self.compiler.get_code_hash(code)

        # Step 1: Compile code
        compilation_result = await self.compiler.compile(
            code, module_name, strict_mode=True
        )

        # Step 2: Check if compilation failed
        blocked, blocked_reason = self._should_block(compilation_result)

        if blocked:
            logger.warning(f"Pattern blocked: {blocked_reason}")

            # Log to audit trail
            audit_id = self.audit_trail.log_compilation(
                code_hash=code_hash,
                module_name=module_name,
                result=compilation_result,
                auth_model=None,
                blocked=True,
            )

            return SafetyCheckResult(
                passed=False,
                compilation_result=compilation_result,
                authorization_model=None,
                blocked_reason=blocked_reason,
                safety_certificate=None,
                audit_id=audit_id,
            )

        # Step 2.5: Check against canonical anti-patterns (NEW)
        # Even if code compiles, it may match known anti-patterns
        anti_patterns = self.resource_loader.registry.list_resources(
            ResourceCategory.ANTI_PATTERN
        )
        safe_patterns = self.resource_loader.registry.list_resources(
            ResourceCategory.PATTERN
        )
        
        policy_result = await check_against_policies(
            code, anti_patterns, safe_patterns
        )
        
        if policy_result.matches_anti_pattern:
            logger.warning(
                f"Pattern blocked by policy: {policy_result.matched_anti_pattern_name}"
            )
            
            # Log to audit trail with policy violation
            audit_id = self.audit_trail.log_compilation(
                code_hash=code_hash,
                module_name=module_name,
                result=compilation_result,
                auth_model=None,
                blocked=True,
                policy_check=policy_result,
            )
            
            return SafetyCheckResult(
                passed=False,
                compilation_result=compilation_result,
                authorization_model=None,
                blocked_reason=f"Matches anti-pattern: {policy_result.matched_anti_pattern_name}",
                safety_certificate=None,
                audit_id=audit_id,
                policy_check=policy_result,
            )

        # Step 3: Extract authorization model
        auth_model = self.auth_validator.extract_auth_model(code, compilation_result)

        # Step 4: Verify type safety
        type_safe = self.type_verifier.verify_type_safety(compilation_result)

        # Step 5: Validate authorization model
        auth_valid = True
        if auth_model:
            auth_valid = self.auth_validator.validate_authorization(auth_model)
        else:
            logger.warning("Could not extract authorization model")
            auth_valid = False

        # Step 6: Final safety determination
        if not type_safe or not auth_valid:
            blocked_reason = self._build_block_reason(type_safe, auth_valid)
            logger.warning(f"Pattern blocked: {blocked_reason}")

            audit_id = self.audit_trail.log_compilation(
                code_hash=code_hash,
                module_name=module_name,
                result=compilation_result,
                auth_model=auth_model,
                blocked=True,
            )

            return SafetyCheckResult(
                passed=False,
                compilation_result=compilation_result,
                authorization_model=auth_model,
                blocked_reason=blocked_reason,
                safety_certificate=None,
                audit_id=audit_id,
            )

        # Step 7: Generate safety certificate
        safety_certificate = self._generate_safety_certificate(
            code_hash, auth_model, compilation_result
        )

        # Step 8: Log to audit trail
        audit_id = self.audit_trail.log_compilation(
            code_hash=code_hash,
            module_name=module_name,
            result=compilation_result,
            auth_model=auth_model,
            blocked=False,
        )

        logger.info(f"✅ Pattern passed safety check: {module_name} (audit: {audit_id})")

        return SafetyCheckResult(
            passed=True,
            compilation_result=compilation_result,
            authorization_model=auth_model,
            blocked_reason=None,
            safety_certificate=safety_certificate,
            audit_id=audit_id,
        )

    def _should_block(
        self, compilation_result
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if pattern should be blocked based on compilation result.

        Args:
            compilation_result: DAML compilation result

        Returns:
            Tuple of (should_block, reason)
        """
        # Block if compilation failed
        if not compilation_result.succeeded:
            error_summary = self.type_verifier.get_error_summary(
                compilation_result.errors
            )
            return True, f"Compilation failed:\n{error_summary}"

        # Block if system error
        if compilation_result.status == CompilationStatus.ERROR:
            return True, "System error during compilation"

        # Passed compilation
        return False, None

    def _build_block_reason(self, type_safe: bool, auth_valid: bool) -> str:
        """
        Build human-readable block reason.

        Args:
            type_safe: Whether type safety check passed
            auth_valid: Whether authorization validation passed

        Returns:
            Formatted block reason string
        """
        reasons = []

        if not type_safe:
            reasons.append("Type safety verification failed")

        if not auth_valid:
            reasons.append("Authorization model invalid or missing")

        return "; ".join(reasons)

    def _generate_safety_certificate(
        self, code_hash: str, auth_model, compilation_result
    ) -> str:
        """
        Generate safety certificate for validated pattern.

        Certificate contains:
        - Code hash (SHA256)
        - DAML SDK version
        - Authorization model
        - Compilation timestamp
        - Certificate signature

        Args:
            code_hash: SHA256 hash of code
            auth_model: Authorization model
            compilation_result: Compilation result

        Returns:
            JSON safety certificate
        """
        certificate = {
            "version": "1.0",
            "gate": "daml_compiler_safety",
            "timestamp": datetime.utcnow().isoformat(),
            "code_hash": code_hash,
            "daml_sdk_version": self.compiler.sdk_version,
            "compilation_time_ms": compilation_result.compilation_time_ms,
            "authorization_model": {
                "template": auth_model.template_name,
                "signatories": auth_model.signatories,
                "observers": auth_model.observers,
                "controllers": auth_model.controllers,
            }
            if auth_model
            else None,
            "type_safe": True,
            "strict_mode": True,
        }

        # Generate certificate signature (hash of certificate data)
        cert_json = json.dumps(certificate, sort_keys=True)
        certificate["signature"] = hashlib.sha256(cert_json.encode()).hexdigest()

        return json.dumps(certificate, indent=2)

    def get_audit_stats(self) -> dict:
        """
        Get audit trail statistics.

        Returns:
            Dictionary with audit stats
        """
        return self.audit_trail.get_stats()
