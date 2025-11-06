"""
Tests for AuthorizationValidator

Unit tests for DAML authorization model extraction and validation.
"""

import pytest

from canton_mcp_server.daml.authorization_validator import AuthorizationValidator
from canton_mcp_server.daml.types import CompilationResult, CompilationStatus


class TestAuthorizationValidator:
    """Test AuthorizationValidator functionality"""

    def setup_method(self):
        """Setup test fixtures"""
        self.validator = AuthorizationValidator()

    def test_extract_template_name_simple(self):
        """Test extracting simple template name"""
        code = """
module Main where

template SimpleIOU
  with
    issuer: Party
"""
        name = self.validator._extract_template_name(code)
        assert name == "SimpleIOU"

    def test_extract_template_name_complex(self):
        """Test extracting template name with underscores and numbers"""
        code = """
template My_Template_123
  with
    party: Party
"""
        name = self.validator._extract_template_name(code)
        assert name == "My_Template_123"

    def test_extract_template_name_not_found(self):
        """Test when no template is present"""
        code = "module Main where\n-- No template"
        name = self.validator._extract_template_name(code)
        assert name is None

    def test_parse_signatories_single(self):
        """Test parsing single signatory"""
        code = """
template Test
  with
    issuer: Party
  where
    signatory issuer
"""
        signatories = self.validator._parse_signatories(code)
        assert signatories == ["issuer"]

    def test_parse_signatories_multiple_inline(self):
        """Test parsing multiple signatories on one line"""
        code = """
template Test
  where
    signatory issuer, owner
"""
        signatories = self.validator._parse_signatories(code)
        assert set(signatories) == {"issuer", "owner"}

    def test_parse_signatories_list_format(self):
        """Test parsing signatories in list format"""
        code = """
template Test
  where
    signatory [party1, party2, party3]
"""
        signatories = self.validator._parse_signatories(code)
        assert set(signatories) == {"party1", "party2", "party3"}

    def test_parse_observers_single(self):
        """Test parsing single observer"""
        code = """
template Test
  where
    observer owner
"""
        observers = self.validator._parse_observers(code)
        assert observers == ["owner"]

    def test_parse_observers_multiple(self):
        """Test parsing multiple observers"""
        code = """
template Test
  where
    observer [auditor, regulator]
"""
        observers = self.validator._parse_observers(code)
        assert set(observers) == {"auditor", "regulator"}

    def test_parse_controllers_single_choice(self):
        """Test parsing controller for single choice"""
        code = """
template Test
  where
    choice Transfer : ContractId Test
      with
        newOwner: Party
      controller owner
      do
        create this with owner = newOwner
"""
        controllers = self.validator._parse_controllers(code)
        assert controllers == {"Transfer": ["owner"]}

    def test_parse_controllers_multiple_choices(self):
        """Test parsing controllers for multiple choices"""
        code = """
template Test
  where
    choice Transfer : ContractId Test
      controller owner
      do
        return ()
    
    choice Archive : ()
      controller issuer
      do
        return ()
"""
        controllers = self.validator._parse_controllers(code)
        assert "Transfer" in controllers
        assert "Archive" in controllers
        assert controllers["Transfer"] == ["owner"]
        assert controllers["Archive"] == ["issuer"]

    def test_extract_auth_model_success(self):
        """Test extracting complete authorization model from valid code"""
        code = """
module Main where

template SimpleIOU
  with
    issuer: Party
    owner: Party
  where
    signatory issuer
    observer owner
    
    choice Transfer : ContractId SimpleIOU
      controller owner
      do
        return ()
"""
        # Mock successful compilation
        compilation_result = CompilationResult(
            status=CompilationStatus.SUCCESS, exit_code=0
        )

        auth_model = self.validator.extract_auth_model(code, compilation_result)

        assert auth_model is not None
        assert auth_model.template_name == "SimpleIOU"
        assert auth_model.signatories == ["issuer"]
        assert auth_model.observers == ["owner"]
        assert "Transfer" in auth_model.controllers
        assert auth_model.controllers["Transfer"] == ["owner"]

    def test_extract_auth_model_failed_compilation(self):
        """Test that extraction is skipped for failed compilation"""
        code = "invalid code"
        compilation_result = CompilationResult(
            status=CompilationStatus.FAILED, exit_code=1
        )

        auth_model = self.validator.extract_auth_model(code, compilation_result)

        assert auth_model is None

    def test_validate_authorization_valid(self):
        """Test validation of valid authorization model"""
        from canton_mcp_server.daml.types import AuthorizationModel

        auth_model = AuthorizationModel(
            template_name="Test",
            signatories=["issuer"],
            observers=["owner"],
            controllers={"Transfer": ["owner"]},
        )

        valid = self.validator.validate_authorization(auth_model)
        assert valid is True

    def test_validate_authorization_no_signatories(self):
        """Test validation fails when no signatories"""
        from canton_mcp_server.daml.types import AuthorizationModel

        auth_model = AuthorizationModel(
            template_name="Test", signatories=[], observers=["owner"], controllers={}
        )

        valid = self.validator.validate_authorization(auth_model)
        assert valid is False

    def test_validate_authorization_invalid_controller(self):
        """Test validation fails when controller is not a party"""
        from canton_mcp_server.daml.types import AuthorizationModel

        auth_model = AuthorizationModel(
            template_name="Test",
            signatories=["issuer"],
            observers=["owner"],
            controllers={"Transfer": ["unknown_party"]},  # Not in signatories/observers
        )

        valid = self.validator.validate_authorization(auth_model)
        assert valid is False

    def test_validate_authorization_controller_is_signatory(self):
        """Test validation passes when controller is signatory"""
        from canton_mcp_server.daml.types import AuthorizationModel

        auth_model = AuthorizationModel(
            template_name="Test",
            signatories=["issuer"],
            observers=[],
            controllers={"Archive": ["issuer"]},
        )

        valid = self.validator.validate_authorization(auth_model)
        assert valid is True




