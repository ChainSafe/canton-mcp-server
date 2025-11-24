"""
Unit tests for MCP Resources Protocol

Tests the resource protocol implementation including:
- Resource registry functionality
- URI parsing and generation
- Resource loading from YAML files
- MCP protocol handlers
"""

import json
import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch

from canton_mcp_server.core.resources.base import (
    CanonicalResourceMetadata,
    PatternResource,
    AntiPatternResource,
    RuleResource,
    ResourceCategory,
    parse_canton_uri,
)
from canton_mcp_server.core.resources.registry import ResourceRegistry
from canton_mcp_server.core.resources.loader import ResourceLoader
from canton_mcp_server.handlers.resource_handler import (
    handle_resources_list,
    handle_resources_read,
)


class TestCanonicalResource:
    """Test CanonicalResource base class functionality"""
    
    def test_pattern_resource_creation(self):
        """Test creating a pattern resource"""
        metadata = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.PATTERN,
            tags=["transfer", "asset"],
            description="Test pattern"
        )
        content = {"pattern_type": "asset_transfer"}
        
        resource = PatternResource("test-pattern", metadata, content)
        
        assert resource.name == "test-pattern"
        assert resource.metadata.version == "1.0"
        assert resource.metadata.category == ResourceCategory.PATTERN
        assert resource.uri == "canton://canonical/patterns/test-pattern/v1.0"
        assert resource.get_content() == content
    
    def test_uri_generation(self):
        """Test URI generation for different resource types"""
        metadata = CanonicalResourceMetadata(
            version="2.1",
            category=ResourceCategory.ANTI_PATTERN,
            tags=["security"]
        )
        
        resource = AntiPatternResource("bad-pattern", metadata, {})
        assert resource.uri == "canton://canonical/anti-patterns/bad-pattern/v2.1"
    
    def test_mcp_resource_conversion(self):
        """Test conversion to MCP Resource format"""
        metadata = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.PATTERN,
            tags=["test"],
            description="Test resource"
        )
        
        resource = PatternResource("test", metadata, {})
        mcp_resource = resource.mcp_resource
        
        assert mcp_resource.uri == "canton://canonical/patterns/test/v1.0"
        assert mcp_resource.name == "test"
        assert mcp_resource.description == "Test resource"
        assert mcp_resource.mime_type == "application/yaml"
        assert mcp_resource.annotations["category"] == "patterns"
        assert mcp_resource.annotations["version"] == "1.0"
        assert mcp_resource.annotations["tags"] == ["test"]
    
    def test_resource_validation(self):
        """Test resource validation"""
        # Valid resource
        metadata = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.PATTERN,
            tags=["test"]
        )
        resource = PatternResource("test", metadata, {})
        errors = resource.validate()
        assert len(errors) == 0
        
        # Invalid resource - missing name
        resource.name = ""
        errors = resource.validate()
        assert "Resource name cannot be empty" in errors
        
        # Invalid resource - missing version
        resource.name = "test"
        resource.metadata.version = ""
        errors = resource.validate()
        assert "Resource version cannot be empty" in errors
        
        # Invalid resource - missing tags
        resource.metadata.version = "1.0"
        resource.metadata.tags = []
        errors = resource.validate()
        assert "Resource must have at least one tag" in errors


class TestURIParsing:
    """Test URI parsing functionality"""
    
    def test_valid_uri_parsing(self):
        """Test parsing valid Canton URIs"""
        uri = "canton://canonical/patterns/simple-transfer/v1.0"
        result = parse_canton_uri(uri)
        
        assert result is not None
        assert result["scheme"] == "canton"
        assert result["category"] == "patterns"
        assert result["name"] == "simple-transfer"
        assert result["version"] == "1.0"
    
    def test_invalid_uri_parsing(self):
        """Test parsing invalid URIs"""
        # Wrong scheme
        assert parse_canton_uri("http://canonical/patterns/test/v1.0") is None
        
        # Wrong netloc
        assert parse_canton_uri("canton://other/patterns/test/v1.0") is None
        
        # Missing version prefix
        assert parse_canton_uri("canton://canonical/patterns/test/1.0") is None
        
        # Wrong number of path parts
        assert parse_canton_uri("canton://canonical/patterns/v1.0") is None
        assert parse_canton_uri("canton://canonical/patterns/test/extra/v1.0") is None
    
    def test_different_categories(self):
        """Test parsing URIs for different categories"""
        categories = ["patterns", "anti-patterns", "rules", "docs"]
        
        for category in categories:
            uri = f"canton://canonical/{category}/test-resource/v2.0"
            result = parse_canton_uri(uri)
            
            assert result is not None
            assert result["category"] == category
            assert result["name"] == "test-resource"
            assert result["version"] == "2.0"


class TestResourceRegistry:
    """Test ResourceRegistry functionality"""
    
    def test_registry_creation(self):
        """Test creating a resource registry"""
        registry = ResourceRegistry()
        assert len(registry.list_resources()) == 0
    
    def test_resource_registration(self):
        """Test registering resources"""
        registry = ResourceRegistry()
        
        metadata = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.PATTERN,
            tags=["test"]
        )
        resource = PatternResource("test", metadata, {})
        
        registry.register(resource)
        
        assert len(registry.list_resources()) == 1
        assert registry.get_resource(resource.uri) == resource
    
    def test_resource_unregistration(self):
        """Test unregistering resources"""
        registry = ResourceRegistry()
        
        metadata = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.PATTERN,
            tags=["test"]
        )
        resource = PatternResource("test", metadata, {})
        
        registry.register(resource)
        assert len(registry.list_resources()) == 1
        
        success = registry.unregister(resource.uri)
        assert success is True
        assert len(registry.list_resources()) == 0
        
        # Try to unregister non-existent resource
        success = registry.unregister("canton://canonical/patterns/nonexistent/v1.0")
        assert success is False
    
    def test_resource_search(self):
        """Test searching resources"""
        registry = ResourceRegistry()
        
        # Add multiple resources
        metadata1 = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.PATTERN,
            tags=["transfer", "asset"],
            description="Simple transfer pattern"
        )
        resource1 = PatternResource("simple-transfer", metadata1, {})
        
        metadata2 = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.PATTERN,
            tags=["complex", "multi-party"],
            description="Complex multi-party pattern"
        )
        resource2 = PatternResource("multi-party", metadata2, {})
        
        registry.register(resource1)
        registry.register(resource2)
        
        # Search by name
        results = registry.search_resources("transfer")
        assert len(results) == 1
        assert results[0].name == "simple-transfer"
        
        # Search by description
        results = registry.search_resources("multi-party")
        assert len(results) == 1
        assert results[0].name == "multi-party"
        
        # Search by tag
        results = registry.search_resources("asset")
        assert len(results) == 1
        assert results[0].name == "simple-transfer"
    
    def test_category_filtering(self):
        """Test filtering resources by category"""
        registry = ResourceRegistry()
        
        # Add resources from different categories
        pattern_metadata = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.PATTERN,
            tags=["test"]
        )
        pattern_resource = PatternResource("pattern", pattern_metadata, {})
        
        rule_metadata = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.RULE,
            tags=["test"]
        )
        rule_resource = RuleResource("rule", rule_metadata, {})
        
        registry.register(pattern_resource)
        registry.register(rule_resource)
        
        # Filter by category
        patterns = registry.list_resources(ResourceCategory.PATTERN)
        assert len(patterns) == 1
        assert patterns[0].name == "pattern"
        
        rules = registry.list_resources(ResourceCategory.RULE)
        assert len(rules) == 1
        assert rules[0].name == "rule"
    
    def test_registry_stats(self):
        """Test registry statistics"""
        registry = ResourceRegistry()
        
        # Add resources from different categories
        pattern_metadata = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.PATTERN,
            tags=["test"]
        )
        pattern_resource = PatternResource("pattern", pattern_metadata, {})
        
        rule_metadata = CanonicalResourceMetadata(
            version="1.0",
            category=ResourceCategory.RULE,
            tags=["test"]
        )
        rule_resource = RuleResource("rule", rule_metadata, {})
        
        registry.register(pattern_resource)
        registry.register(rule_resource)
        
        stats = registry.get_stats()
        assert stats["total"] == 2
        assert stats["by_category"]["patterns"] == 1
        assert stats["by_category"]["rules"] == 1
        assert stats["by_category"]["anti-patterns"] == 0
        assert stats["by_category"]["docs"] == 0


class TestResourceLoader:
    """Test ResourceLoader functionality"""
    
    def test_load_yaml_resource(self):
        """Test loading a resource from YAML file"""
        # Create temporary YAML file
        yaml_content = {
            "name": "test-pattern",
            "version": "1.0.0",
            "description": "Test pattern",
            "tags": ["test", "pattern"],
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
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            patterns_dir = temp_path / "patterns"
            patterns_dir.mkdir()
            
            yaml_file = patterns_dir / "test-pattern-v1.0.yaml"
            with open(yaml_file, 'w') as f:
                yaml.dump(yaml_content, f)
            
            # Test loading
            loader = ResourceLoader(str(temp_path))
            loader.registry = ResourceRegistry()  # Fresh registry
            loader._load_category_resources(ResourceCategory.PATTERN, "patterns")
            
            # Verify resource was loaded
            registry = loader.registry
            resources = registry.list_resources()
            assert len(resources) == 1
            
            resource = resources[0]
            assert resource.name == "test-pattern"
            assert resource.metadata.version == "1.0.0"
            assert resource.metadata.description == "Test pattern"
            assert resource.metadata.tags == ["test", "pattern"]
            assert resource.metadata.author == "Test Author"
            assert resource.get_content()["pattern_type"] == "test"
    
    def test_load_invalid_yaml(self):
        """Test loading invalid YAML files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            patterns_dir = temp_path / "patterns"
            patterns_dir.mkdir()
            
            # Create invalid YAML file
            invalid_file = patterns_dir / "invalid.yaml"
            with open(invalid_file, 'w') as f:
                f.write("invalid: yaml: content: [")
            
            # Create a fresh loader with clean registry
            loader = ResourceLoader(str(temp_path))
            loader.registry = ResourceRegistry()  # Fresh registry
            loader._load_category_resources(ResourceCategory.PATTERN, "patterns")
            
            # Should not crash and should load no resources
            registry = loader.registry
            assert len(registry.list_resources()) == 0
    
    def test_load_missing_fields(self):
        """Test loading YAML with missing required fields"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            patterns_dir = temp_path / "patterns"
            patterns_dir.mkdir()
            
            # Create YAML missing name
            yaml_content = {
                "version": "1.0.0",
                "tags": ["test"]
            }
            
            yaml_file = patterns_dir / "missing-name.yaml"
            with open(yaml_file, 'w') as f:
                yaml.dump(yaml_content, f)
            
            # Create a fresh loader with clean registry
            loader = ResourceLoader(str(temp_path))
            loader.registry = ResourceRegistry()  # Fresh registry
            loader._load_category_resources(ResourceCategory.PATTERN, "patterns")
            
            # Should not load resource due to missing name
            registry = loader.registry
            assert len(registry.list_resources()) == 0


class TestResourceHandlers:
    """Test MCP resource protocol handlers"""
    
    def test_handle_resources_list(self):
        """Test resources/list handler"""
        # Mock registry with test resources
        with patch('canton_mcp_server.handlers.resource_handler.get_registry') as mock_get_registry:
            mock_registry = mock_get_registry.return_value
            
            metadata = CanonicalResourceMetadata(
                version="1.0",
                category=ResourceCategory.PATTERN,
                tags=["test"]
            )
            resource = PatternResource("test", metadata, {})
            mock_registry.list_resources.return_value = [resource]
            
            result = handle_resources_list()
            
            assert len(result.resources) == 1
            assert result.resources[0].uri == "canton://canonical/patterns/test/v1.0"
            assert result.resources[0].name == "test"
    
    def test_handle_resources_read(self):
        """Test resources/read handler"""
        # Mock registry with test resource
        with patch('canton_mcp_server.handlers.resource_handler.get_registry') as mock_get_registry:
            mock_registry = mock_get_registry.return_value
            
            metadata = CanonicalResourceMetadata(
                version="1.0",
                category=ResourceCategory.PATTERN,
                tags=["test"]
            )
            resource = PatternResource("test", metadata, {"pattern_type": "test"})
            mock_registry.get_resource.return_value = resource
            
            result = handle_resources_read("canton://canonical/patterns/test/v1.0")
            
            assert len(result.contents) == 1
            assert result.contents[0].uri == "canton://canonical/patterns/test/v1.0"
            assert result.contents[0].mime_type == "application/json"
            
            # Verify content is JSON
            content_data = json.loads(result.contents[0].text)
            assert content_data["pattern_type"] == "test"
    
    def test_handle_resources_read_invalid_uri(self):
        """Test resources/read handler with invalid URI"""
        with pytest.raises(ValueError, match="Invalid Canton URI format"):
            handle_resources_read("invalid-uri")
    
    def test_handle_resources_read_not_found(self):
        """Test resources/read handler with non-existent resource"""
        with patch('canton_mcp_server.handlers.resource_handler.get_registry') as mock_get_registry:
            mock_registry = mock_get_registry.return_value
            mock_registry.get_resource.return_value = None
            
            with pytest.raises(ValueError, match="Resource not found"):
                handle_resources_read("canton://canonical/patterns/nonexistent/v1.0")


if __name__ == "__main__":
    pytest.main([__file__])
