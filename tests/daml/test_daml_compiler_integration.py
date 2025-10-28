"""
Tests for DamlCompiler Integration

Integration tests for DAML compiler subprocess wrapper.
Requires DAML SDK to be installed.
"""

import pytest
import shutil
from pathlib import Path

from canton_mcp_server.daml.daml_compiler_integration import DamlCompiler, DamlCompilerError
from canton_mcp_server.daml.types import CompilationStatus, ErrorCategory


# Check if daml command is available
DAML_AVAILABLE = shutil.which("daml") is not None
requires_daml = pytest.mark.skipif(
    not DAML_AVAILABLE,
    reason="DAML SDK not installed (run: curl -sSL https://get.daml.com/ | sh)"
)


class TestDamlCompiler:
    """Test DamlCompiler integration (requires DAML SDK)"""

    def setup_method(self):
        """Setup test fixtures"""
        if DAML_AVAILABLE:
            self.compiler = DamlCompiler(sdk_version="2.10.2", compilation_timeout=30)

    def test_init_requires_daml_command(self):
        """Test initialization fails if daml command not found"""
        if DAML_AVAILABLE:
            pytest.skip("DAML is available, cannot test missing case")
        
        with pytest.raises(DamlCompilerError, match="DAML compiler not found"):
            DamlCompiler(daml_command="nonexistent-command")

    @requires_daml
    def test_generate_daml_yaml_basic(self):
        """Test generating basic daml.yaml"""
        yaml_content = self.compiler._generate_daml_yaml("Main", strict_mode=False)

        assert "sdk-version:" in yaml_content
        assert "name: safety-check" in yaml_content
        assert "source: daml" in yaml_content
        assert "daml-prim" in yaml_content
        assert "daml-stdlib" in yaml_content

    @requires_daml
    def test_generate_daml_yaml_strict(self):
        """Test generating daml.yaml with strict mode"""
        yaml_content = self.compiler._generate_daml_yaml("Main", strict_mode=True)

        assert "build-options:" in yaml_content
        assert "-Werror" in yaml_content
        assert "-Wunused-top-binds" in yaml_content

    @requires_daml
    def test_categorize_error_authorization(self):
        """Test categorizing authorization errors"""
        msg = "Authorization failure: missing signatory"
        category = self.compiler._categorize_error(msg)

        assert category == ErrorCategory.AUTHORIZATION

    @requires_daml
    def test_categorize_error_type(self):
        """Test categorizing type errors"""
        msg = "Couldn't match expected type 'Party' with actual type 'Text'"
        category = self.compiler._categorize_error(msg)

        assert category == ErrorCategory.TYPE_SAFETY

    @requires_daml
    def test_categorize_error_syntax(self):
        """Test categorizing syntax errors"""
        msg = "parse error on input 'where'"
        category = self.compiler._categorize_error(msg)

        assert category == ErrorCategory.SYNTAX

    @requires_daml
    def test_categorize_error_other(self):
        """Test categorizing unknown errors"""
        msg = "Some other error message"
        category = self.compiler._categorize_error(msg)

        assert category == ErrorCategory.OTHER

    @requires_daml
    def test_get_code_hash(self):
        """Test code hash generation"""
        code1 = "template Test where signatory party"
        code2 = "template Test where signatory party"
        code3 = "template Test where signatory owner"

        hash1 = self.compiler.get_code_hash(code1)
        hash2 = self.compiler.get_code_hash(code2)
        hash3 = self.compiler.get_code_hash(code3)

        # Same code = same hash
        assert hash1 == hash2

        # Different code = different hash
        assert hash1 != hash3

        # Hash should be hex string
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA256 hex digest

    @requires_daml
    @pytest.mark.asyncio
    async def test_compile_valid_template(self):
        """Test compiling valid DAML template"""
        # Read valid fixture
        fixture_path = Path(__file__).parent / "fixtures" / "valid_template.daml"
        code = fixture_path.read_text()

        result = await self.compiler.compile(code, module_name="Main", strict_mode=True)

        assert result.status == CompilationStatus.SUCCESS
        assert result.exit_code == 0
        assert len(result.errors) == 0
        assert result.compilation_time_ms > 0

    @requires_daml
    @pytest.mark.asyncio
    async def test_compile_invalid_auth(self):
        """Test compiling template with authorization error"""
        # Read invalid auth fixture
        fixture_path = Path(__file__).parent / "fixtures" / "invalid_auth.daml"
        code = fixture_path.read_text()

        result = await self.compiler.compile(code, module_name="Main", strict_mode=True)

        assert result.status == CompilationStatus.FAILED
        assert result.exit_code != 0
        assert len(result.errors) > 0

        # Should have at least one authorization error
        auth_errors = [e for e in result.errors if e.category == ErrorCategory.AUTHORIZATION]
        assert len(auth_errors) > 0

    @requires_daml
    @pytest.mark.asyncio
    async def test_compile_invalid_type(self):
        """Test compiling template with type error"""
        # Read invalid type fixture
        fixture_path = Path(__file__).parent / "fixtures" / "invalid_type.daml"
        code = fixture_path.read_text()

        result = await self.compiler.compile(code, module_name="Main", strict_mode=True)

        assert result.status == CompilationStatus.FAILED
        assert result.exit_code != 0
        assert len(result.errors) > 0

        # Should have type safety errors
        type_errors = [e for e in result.errors if e.category == ErrorCategory.TYPE_SAFETY]
        assert len(type_errors) > 0

    @requires_daml
    @pytest.mark.asyncio
    async def test_compile_syntax_error(self):
        """Test compiling code with syntax errors"""
        code = """
module Main where

template BadSyntax
  with
    party: Party
  where
    signatory party
    -- Missing choice closing
    choice Transfer
      controller party
"""

        result = await self.compiler.compile(code, module_name="Main", strict_mode=True)

        assert result.status == CompilationStatus.FAILED
        assert len(result.errors) > 0

    @requires_daml
    @pytest.mark.asyncio
    async def test_parse_errors_extracts_location(self):
        """Test error parsing extracts file, line, column"""
        fixture_path = Path(__file__).parent / "fixtures" / "invalid_auth.daml"
        code = fixture_path.read_text()

        result = await self.compiler.compile(code, module_name="Main", strict_mode=True)

        if len(result.errors) > 0:
            error = result.errors[0]
            assert error.file_path
            assert error.line > 0
            assert error.column >= 0
            assert error.message

    @requires_daml
    @pytest.mark.asyncio
    async def test_compilation_timeout(self):
        """Test compilation timeout handling"""
        # Use very short timeout
        compiler_fast_timeout = DamlCompiler(compilation_timeout=0.001)  # 1ms timeout

        fixture_path = Path(__file__).parent / "fixtures" / "valid_template.daml"
        code = fixture_path.read_text()

        # Should timeout
        with pytest.raises(DamlCompilerError, match="timed out"):
            await compiler_fast_timeout.compile(code, module_name="Main")


class TestDamlCompilerErrorParsing:
    """Test error parsing logic without requiring DAML SDK"""

    def setup_method(self):
        """Setup for error parsing tests"""
        if DAML_AVAILABLE:
            self.compiler = DamlCompiler()

    def test_parse_errors_empty_stderr(self):
        """Test parsing empty stderr"""
        if not DAML_AVAILABLE:
            pytest.skip("Requires DAML SDK")

        errors = self.compiler._parse_errors("")
        assert errors == []

    def test_parse_errors_single_error(self):
        """Test parsing single error from stderr"""
        if not DAML_AVAILABLE:
            pytest.skip("Requires DAML SDK")

        stderr = """
daml/Main.daml:10:5: error:
    • Authorization failure: missing signatory
    • In the definition of 'transfer'
"""
        errors = self.compiler._parse_errors(stderr)

        assert len(errors) >= 1
        if len(errors) > 0:
            error = errors[0]
            assert "Main.daml" in error.file_path
            assert error.line == 10
            assert error.column == 5
            assert "Authorization" in error.message or "missing signatory" in error.message

    def test_parse_errors_multiple_errors(self):
        """Test parsing multiple errors from stderr"""
        if not DAML_AVAILABLE:
            pytest.skip("Requires DAML SDK")

        stderr = """
daml/Main.daml:10:5: error:
    • First error message

daml/Main.daml:20:10: error:
    • Second error message
"""
        errors = self.compiler._parse_errors(stderr)

        assert len(errors) >= 2

