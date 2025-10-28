"""
Tests for SafetyChecker

Integration tests for Gate 1: DAML Compiler Safety orchestrator.
Some tests require DAML SDK to be installed.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from canton_mcp_server.daml.audit_trail import AuditTrail
from canton_mcp_server.daml.authorization_validator import AuthorizationValidator
from canton_mcp_server.daml.daml_compiler_integration import DamlCompiler
from canton_mcp_server.daml.safety_checker import SafetyChecker
from canton_mcp_server.daml.type_safety_verifier import TypeSafetyVerifier


# Check if daml command is available
DAML_AVAILABLE = shutil.which("daml") is not None
requires_daml = pytest.mark.skipif(
    not DAML_AVAILABLE, reason="DAML SDK not installed"
)


class TestSafetyChecker:
    """Test SafetyChecker orchestration"""

    def setup_method(self):
        """Setup test fixtures"""
        self.temp_dir = tempfile.mkdtemp(prefix="safety_test_")
        self.storage_path = Path(self.temp_dir)

        if DAML_AVAILABLE:
            self.compiler = DamlCompiler()
            self.auth_validator = AuthorizationValidator()
            self.type_verifier = TypeSafetyVerifier()
            self.audit_trail = AuditTrail(storage_path=self.storage_path)

            self.safety_checker = SafetyChecker(
                compiler=self.compiler,
                auth_validator=self.auth_validator,
                type_verifier=self.type_verifier,
                audit_trail=self.audit_trail,
            )

    def teardown_method(self):
        """Cleanup temporary directory"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_with_defaults(self):
        """Test SafetyChecker initializes with default components"""
        if not DAML_AVAILABLE:
            pytest.skip("Requires DAML SDK")

        checker = SafetyChecker()

        assert checker.compiler is not None
        assert checker.auth_validator is not None
        assert checker.type_verifier is not None
        assert checker.audit_trail is not None

    @requires_daml
    @pytest.mark.asyncio
    async def test_check_pattern_safety_valid_template(self):
        """Test safety check passes for valid template"""
        fixture_path = Path(__file__).parent / "fixtures" / "valid_template.daml"
        code = fixture_path.read_text()

        result = await self.safety_checker.check_pattern_safety(code, module_name="Main")

        assert result.passed is True
        assert result.is_safe is True
        assert result.compilation_result.succeeded is True
        assert result.authorization_model is not None
        assert result.authorization_model.template_name == "SimpleIOU"
        assert "issuer" in result.authorization_model.signatories
        assert result.blocked_reason is None
        assert result.safety_certificate is not None
        assert result.audit_id

        # Verify certificate is valid JSON
        cert = json.loads(result.safety_certificate)
        assert cert["gate"] == "daml_compiler_safety"
        assert cert["type_safe"] is True
        assert cert["signature"]

    @requires_daml
    @pytest.mark.asyncio
    async def test_check_pattern_safety_invalid_auth(self):
        """Test safety check blocks template with authorization error"""
        fixture_path = Path(__file__).parent / "fixtures" / "invalid_auth.daml"
        code = fixture_path.read_text()

        result = await self.safety_checker.check_pattern_safety(code, module_name="Main")

        assert result.passed is False
        assert result.is_safe is False
        assert result.blocked_reason is not None
        assert "Compilation failed" in result.blocked_reason
        assert result.safety_certificate is None
        assert result.audit_id

    @requires_daml
    @pytest.mark.asyncio
    async def test_check_pattern_safety_invalid_type(self):
        """Test safety check blocks template with type error"""
        fixture_path = Path(__file__).parent / "fixtures" / "invalid_type.daml"
        code = fixture_path.read_text()

        result = await self.safety_checker.check_pattern_safety(code, module_name="Main")

        assert result.passed is False
        assert result.is_safe is False
        assert result.blocked_reason is not None
        assert result.safety_certificate is None

    @requires_daml
    @pytest.mark.asyncio
    async def test_audit_trail_integration(self):
        """Test safety checker logs to audit trail"""
        fixture_path = Path(__file__).parent / "fixtures" / "valid_template.daml"
        code = fixture_path.read_text()

        result = await self.safety_checker.check_pattern_safety(code, module_name="Main")

        # Verify audit entry was created
        assert result.audit_id

        entry = self.audit_trail.get_audit_entry(result.audit_id)
        assert entry is not None
        assert entry.module_name == "Main"
        assert entry.blocked is False

    @requires_daml
    @pytest.mark.asyncio
    async def test_audit_trail_blocked_entry(self):
        """Test audit trail records blocked patterns"""
        fixture_path = Path(__file__).parent / "fixtures" / "invalid_auth.daml"
        code = fixture_path.read_text()

        result = await self.safety_checker.check_pattern_safety(code, module_name="Main")

        # Verify blocked entry in audit
        entry = self.audit_trail.get_audit_entry(result.audit_id)
        assert entry is not None
        assert entry.blocked is True
        assert len(entry.errors) > 0

    @requires_daml
    @pytest.mark.asyncio
    async def test_multiple_checks_audit_trail(self):
        """Test multiple safety checks accumulate in audit trail"""
        valid_fixture = Path(__file__).parent / "fixtures" / "valid_template.daml"
        invalid_fixture = Path(__file__).parent / "fixtures" / "invalid_auth.daml"

        # Check valid template
        await self.safety_checker.check_pattern_safety(
            valid_fixture.read_text(), module_name="Valid"
        )

        # Check invalid template
        await self.safety_checker.check_pattern_safety(
            invalid_fixture.read_text(), module_name="Invalid"
        )

        # Verify audit stats
        stats = self.safety_checker.get_audit_stats()
        assert stats["total"] >= 2
        assert stats["blocked"] >= 1

    @requires_daml
    def test_generate_safety_certificate_structure(self):
        """Test safety certificate structure"""
        from canton_mcp_server.daml.types import AuthorizationModel, CompilationResult, CompilationStatus

        code_hash = "test_hash_123"
        auth_model = AuthorizationModel(
            template_name="Test",
            signatories=["issuer"],
            observers=["owner"],
            controllers={"Transfer": ["owner"]},
        )
        compilation_result = CompilationResult(
            status=CompilationStatus.SUCCESS, exit_code=0, compilation_time_ms=250
        )

        cert_json = self.safety_checker._generate_safety_certificate(
            code_hash, auth_model, compilation_result
        )

        cert = json.loads(cert_json)

        # Verify certificate structure
        assert cert["version"] == "1.0"
        assert cert["gate"] == "daml_compiler_safety"
        assert cert["timestamp"]
        assert cert["code_hash"] == code_hash
        assert cert["daml_sdk_version"]
        assert cert["compilation_time_ms"] == 250
        assert cert["type_safe"] is True
        assert cert["strict_mode"] is True
        assert cert["authorization_model"]["template"] == "Test"
        assert cert["authorization_model"]["signatories"] == ["issuer"]
        assert cert["signature"]  # Certificate is signed

    @requires_daml
    def test_should_block_success(self):
        """Test blocking logic for successful compilation"""
        from canton_mcp_server.daml.types import CompilationResult, CompilationStatus

        result = CompilationResult(status=CompilationStatus.SUCCESS, exit_code=0)

        should_block, reason = self.safety_checker._should_block(result)

        assert should_block is False
        assert reason is None

    @requires_daml
    def test_should_block_failed(self):
        """Test blocking logic for failed compilation"""
        from canton_mcp_server.daml.types import CompilationResult, CompilationStatus

        result = CompilationResult(status=CompilationStatus.FAILED, exit_code=1)

        should_block, reason = self.safety_checker._should_block(result)

        assert should_block is True
        assert reason is not None
        assert "Compilation failed" in reason

    @requires_daml
    def test_build_block_reason_type_unsafe(self):
        """Test building block reason for type safety failure"""
        reason = self.safety_checker._build_block_reason(
            type_safe=False, auth_valid=True
        )

        assert "Type safety verification failed" in reason

    @requires_daml
    def test_build_block_reason_auth_invalid(self):
        """Test building block reason for invalid authorization"""
        reason = self.safety_checker._build_block_reason(
            type_safe=True, auth_valid=False
        )

        assert "Authorization model invalid" in reason

    @requires_daml
    def test_build_block_reason_both_invalid(self):
        """Test building block reason for both failures"""
        reason = self.safety_checker._build_block_reason(
            type_safe=False, auth_valid=False
        )

        assert "Type safety" in reason
        assert "Authorization" in reason

    @requires_daml
    @pytest.mark.asyncio
    async def test_safety_check_result_string_representation(self):
        """Test SafetyCheckResult string representation"""
        fixture_path = Path(__file__).parent / "fixtures" / "valid_template.daml"
        code = fixture_path.read_text()

        result = await self.safety_checker.check_pattern_safety(code, module_name="Main")

        result_str = str(result)

        assert "Safety Check:" in result_str
        if result.passed:
            assert "✅ SAFE" in result_str
            assert result.audit_id in result_str

