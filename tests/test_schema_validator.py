"""
Tests for Resource Schema Validator
"""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from canton_mcp_server.core.resources.validator import (
    ResourceSchemaValidator,
    SchemaValidationError,
    get_validator,
    validate_resource_data,
    validate_yaml_file,
)


class TestResourceSchemaValidator:
    """Test the ResourceSchemaValidator class"""
    
    def test_validator_initialization(self):
        """Test validator initialization with schemas directory"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mock schema files
            schemas_dir = Path(temp_dir) / "schemas"
            schemas_dir.mkdir()
            
            # Create a simple pattern schema
            pattern_schema = {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string"}
                }
            }
            
            with open(schemas_dir / "pattern.schema.json", 'w') as f:
                json.dump(pattern_schema, f)
            
            validator = ResourceSchemaValidator(str(schemas_dir))
            
            assert validator.is_schema_loaded("pattern")
            assert not validator.is_schema_loaded("anti-pattern")
            assert "pattern" in validator.list_supported_types()
    
    def test_schema_loading_missing_directory(self):
        """Test behavior when schemas directory doesn't exist"""
        validator = ResourceSchemaValidator("nonexistent_dir")
        assert len(validator.list_supported_types()) == 0
    
    def test_schema_loading_invalid_json(self):
        """Test behavior when schema file contains invalid JSON"""
        with tempfile.TemporaryDirectory() as temp_dir:
            schemas_dir = Path(temp_dir) / "schemas"
            schemas_dir.mkdir()
            
            # Create invalid JSON file
            with open(schemas_dir / "pattern.schema.json", 'w') as f:
                f.write("invalid json content")
            
            validator = ResourceSchemaValidator(str(schemas_dir))
            assert not validator.is_schema_loaded("pattern")
    
    def test_validate_resource_success(self):
        """Test successful resource validation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            schemas_dir = Path(temp_dir) / "schemas"
            schemas_dir.mkdir()
            
            # Create a simple pattern schema
            pattern_schema = {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string"}
                }
            }
            
            with open(schemas_dir / "pattern.schema.json", 'w') as f:
                json.dump(pattern_schema, f)
            
            validator = ResourceSchemaValidator(str(schemas_dir))
            
            # Valid data
            valid_data = {
                "name": "test-pattern",
                "version": "1.0.0"
            }
            
            result = validator.validate_resource(valid_data, "pattern")
            assert result is True
    
    def test_validate_resource_failure(self):
        """Test resource validation failure"""
        with tempfile.TemporaryDirectory() as temp_dir:
            schemas_dir = Path(temp_dir) / "schemas"
            schemas_dir.mkdir()
            
            # Create a simple pattern schema
            pattern_schema = {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string"}
                }
            }
            
            with open(schemas_dir / "pattern.schema.json", 'w') as f:
                json.dump(pattern_schema, f)
            
            validator = ResourceSchemaValidator(str(schemas_dir))
            
            # Invalid data (missing required fields)
            invalid_data = {
                "name": "test-pattern"
                # Missing version
            }
            
            with pytest.raises(SchemaValidationError) as exc_info:
                validator.validate_resource(invalid_data, "pattern")
            
            assert "version" in str(exc_info.value)
    
    def test_validate_resource_unknown_type(self):
        """Test validation with unknown resource type"""
        validator = ResourceSchemaValidator()
        
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate_resource({}, "unknown-type")
        
        assert "No schema found" in str(exc_info.value)
    
    def test_validate_yaml_file_success(self):
        """Test successful YAML file validation"""
        with tempfile.TemporaryDirectory() as temp_dir:
            schemas_dir = Path(temp_dir) / "schemas"
            schemas_dir.mkdir()
            
            # Create a simple pattern schema
            pattern_schema = {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "string"}
                }
            }
            
            with open(schemas_dir / "pattern.schema.json", 'w') as f:
                json.dump(pattern_schema, f)
            
            # Create valid YAML file
            yaml_file = Path(temp_dir) / "test.yaml"
            yaml_content = """
name: test-pattern
version: 1.0.0
"""
            yaml_file.write_text(yaml_content)
            
            validator = ResourceSchemaValidator(str(schemas_dir))
            result = validator.validate_yaml_file(yaml_file, "pattern")
            assert result is True
    
    def test_validate_yaml_file_invalid_yaml(self):
        """Test validation with invalid YAML file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            schemas_dir = Path(temp_dir) / "schemas"
            schemas_dir.mkdir()
            
            validator = ResourceSchemaValidator(str(schemas_dir))
            
            # Create invalid YAML file
            yaml_file = Path(temp_dir) / "invalid.yaml"
            yaml_file.write_text("invalid: yaml: content: [")
            
            with pytest.raises(SchemaValidationError) as exc_info:
                validator.validate_yaml_file(yaml_file, "pattern")
            
            assert "YAML parsing error" in str(exc_info.value)
    
    def test_validate_yaml_file_empty(self):
        """Test validation with empty YAML file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            schemas_dir = Path(temp_dir) / "schemas"
            schemas_dir.mkdir()
            
            validator = ResourceSchemaValidator(str(schemas_dir))
            
            # Create empty YAML file
            yaml_file = Path(temp_dir) / "empty.yaml"
            yaml_file.write_text("")
            
            with pytest.raises(SchemaValidationError) as exc_info:
                validator.validate_yaml_file(yaml_file, "pattern")
            
            assert "Empty YAML file" in str(exc_info.value)
    
    def test_format_validation_errors(self):
        """Test validation error formatting"""
        with tempfile.TemporaryDirectory() as temp_dir:
            schemas_dir = Path(temp_dir) / "schemas"
            schemas_dir.mkdir()
            
            # Create schema with nested validation
            pattern_schema = {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "required": ["name", "metadata"],
                "properties": {
                    "name": {"type": "string"},
                    "metadata": {
                        "type": "object",
                        "required": ["version"],
                        "properties": {
                            "version": {"type": "string"}
                        }
                    }
                }
            }
            
            with open(schemas_dir / "pattern.schema.json", 'w') as f:
                json.dump(pattern_schema, f)
            
            validator = ResourceSchemaValidator(str(schemas_dir))
            
            # Data with nested validation errors
            invalid_data = {
                "name": "test",
                "metadata": {}  # Missing version
            }
            
            with pytest.raises(SchemaValidationError) as exc_info:
                validator.validate_resource(invalid_data, "pattern")
            
            assert exc_info.value.errors
            assert any("version" in error for error in exc_info.value.errors)


class TestGlobalValidatorFunctions:
    """Test global validator functions"""
    
    def test_get_validator_singleton(self):
        """Test that get_validator returns singleton instance"""
        validator1 = get_validator()
        validator2 = get_validator()
        assert validator1 is validator2
    
    def test_validate_resource_data(self):
        """Test validate_resource_data function"""
        # Mock the validator to avoid loading actual schemas
        with patch('canton_mcp_server.core.resources.validator.get_validator') as mock_get_validator:
            mock_validator = MagicMock()
            mock_validator.validate_resource.return_value = True
            mock_get_validator.return_value = mock_validator
            
            result = validate_resource_data({"name": "test", "version": "1.0"}, "pattern")
            assert result is True
            mock_validator.validate_resource.assert_called_once_with({"name": "test", "version": "1.0"}, "pattern")
    
    def test_validate_yaml_file_function(self):
        """Test validate_yaml_file function"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test YAML file
            yaml_file = Path(temp_dir) / "test.yaml"
            yaml_file.write_text("name: test\nversion: 1.0")
            
            # Mock the validator
            with patch('canton_mcp_server.core.resources.validator.get_validator') as mock_get_validator:
                mock_validator = MagicMock()
                mock_validator.validate_yaml_file.return_value = True
                mock_get_validator.return_value = mock_validator
                
                result = validate_yaml_file(yaml_file, "pattern")
                assert result is True
                mock_validator.validate_yaml_file.assert_called_once()


class TestSchemaIntegration:
    """Test schema integration with actual schemas"""
    
    def test_pattern_schema_validation(self):
        """Test validation against actual pattern schema"""
        # Create a valid pattern resource
        valid_pattern = {
            "name": "test-pattern",
            "version": "1.0.0",
            "description": "A test pattern for validation",
            "tags": ["test", "validation"],
            "author": "Test Author",
            "created_at": "2024-01-15T10:00:00Z",
            "pattern_type": "test",
            "daml_template": "template Test\n  with\n    party: Party\n  where\n    signatory party",
            "authorization_requirements": [
                {
                    "id": "REQ-AUTH-001",
                    "rule": "Test rule",
                    "satisfied": True,
                    "explanation": "Test explanation"
                }
            ],
            "when_to_use": ["Test scenarios"],
            "when_not_to_use": ["Non-test scenarios"],
            "security_considerations": ["Test security"],
            "test_cases": [
                {
                    "description": "Test case",
                    "passes": True,
                    "code": "test code"
                }
            ]
        }
        
        validator = get_validator()
        if validator.is_schema_loaded("pattern"):
            result = validator.validate_resource(valid_pattern, "pattern")
            assert result is True
    
    def test_anti_pattern_schema_validation(self):
        """Test validation against actual anti-pattern schema"""
        # Create a valid anti-pattern resource
        valid_anti_pattern = {
            "name": "test-anti-pattern",
            "version": "1.0.0",
            "description": "A test anti-pattern for validation",
            "tags": ["test", "anti-pattern"],
            "author": "Test Author",
            "created_at": "2024-01-15T10:00:00Z",
            "anti_pattern_type": "test",
            "severity": "high",
            "problematic_code": "template Bad\n  with\n    party: Party\n  where\n    observer party",
            "why_problematic": "This is problematic because...",
            "detection_pattern": ["Pattern to detect"],
            "correct_alternative": "template Good\n  with\n    party: Party\n  where\n    signatory party",
            "impact": [
                {
                    "type": "correctness",
                    "severity": "high",
                    "description": "Test impact"
                }
            ],
            "remediation": ["Fix the issue"]
        }
        
        validator = get_validator()
        if validator.is_schema_loaded("anti-pattern"):
            result = validator.validate_resource(valid_anti_pattern, "anti-pattern")
            assert result is True
