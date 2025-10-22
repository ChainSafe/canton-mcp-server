"""
Tests for enhanced Resource Loader with hot-reload functionality
"""

import os
import tempfile
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from canton_mcp_server.core.resources.loader import (
    ResourceLoader,
    ResourceFileHandler,
    get_loader,
    load_resources,
    reload_resources,
    stop_hot_reload,
)
from canton_mcp_server.core.resources.base import ResourceCategory
from canton_mcp_server.core.resources.registry import ResourceRegistry


class TestResourceLoaderHotReload:
    """Test hot-reload functionality"""
    
    def test_enable_hot_reload_flag(self):
        """Test that hot-reload can be enabled/disabled"""
        loader = ResourceLoader(enable_hot_reload=True)
        assert loader.enable_hot_reload is True
        
        loader = ResourceLoader(enable_hot_reload=False)
        assert loader.enable_hot_reload is False
    
    def test_file_watcher_start_stop(self):
        """Test file watcher start and stop functionality"""
        with tempfile.TemporaryDirectory() as temp_dir:
            loader = ResourceLoader(resources_dir=temp_dir, enable_hot_reload=True)
            
            # Mock the observer to avoid actual file watching
            mock_observer = MagicMock()
            loader.observer = mock_observer
            
            # Test start
            loader._start_file_watcher()
            assert loader.observer is not None
            
            # Test stop
            loader.stop_file_watcher()
            mock_observer.stop.assert_called_once()
            mock_observer.join.assert_called_once()
    
    def test_file_handler_debouncing(self):
        """Test that file handler debounces rapid changes"""
        loader = ResourceLoader()
        handler = ResourceFileHandler(loader)
        
        # Mock the reload method
        loader._reload_single_file = MagicMock()
        
        # Create a mock event
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "test.yaml"
        
        # First call should trigger reload
        handler.on_modified(mock_event)
        assert loader._reload_single_file.called
        
        # Reset mock
        loader._reload_single_file.reset_mock()
        
        # Second call within debounce period should be ignored
        handler.on_modified(mock_event)
        assert not loader._reload_single_file.called
    
    def test_file_handler_ignores_non_yaml_files(self):
        """Test that file handler ignores non-YAML files"""
        loader = ResourceLoader()
        handler = ResourceFileHandler(loader)
        
        loader._reload_single_file = MagicMock()
        
        # Test with non-YAML file
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = "test.txt"
        
        handler.on_modified(mock_event)
        assert not loader._reload_single_file.called
    
    def test_file_handler_ignores_directories(self):
        """Test that file handler ignores directory events"""
        loader = ResourceLoader()
        handler = ResourceFileHandler(loader)
        
        loader._reload_single_file = MagicMock()
        
        # Test with directory event
        mock_event = MagicMock()
        mock_event.is_directory = True
        mock_event.src_path = "test.yaml"
        
        handler.on_modified(mock_event)
        assert not loader._reload_single_file.called


class TestResourceLoaderSingleFileReload:
    """Test single file reload functionality"""
    
    def test_reload_single_file_pattern(self):
        """Test reloading a single pattern file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test structure
            patterns_dir = Path(temp_dir) / "patterns"
            patterns_dir.mkdir()
            
            # Create test file
            test_file = patterns_dir / "test-pattern.yaml"
            test_file.write_text("""
name: test-pattern
version: "1.0.0"
description: Test pattern
tags: [test]
author: Test Author
created_at: "2024-01-15T10:00:00Z"
pattern_type: test
daml_template: |
  template Test
    with
      party: Party
    where
      signatory party
authorization_requirements:
  - id: REQ-AUTH-001
    rule: Test rule
    satisfied: true
    explanation: Test explanation
when_to_use: [Test scenarios]
when_not_to_use: [Non-test scenarios]
security_considerations: [Test security]
test_cases:
  - description: Test case
    passes: true
    code: test code
""")
            
            # Create loader with fresh registry
            registry = ResourceRegistry()
            loader = ResourceLoader(resources_dir=temp_dir)
            loader.registry = registry
            
            # Load initial resource
            resource = loader._load_resource_file(test_file, ResourceCategory.PATTERN)
            assert resource is not None
            registry.register(resource)
            
            # Modify file
            test_file.write_text("""
name: test-pattern
version: "1.0.0"
description: Updated test pattern
tags: [test]
author: Test Author
created_at: "2024-01-15T10:00:00Z"
pattern_type: test
daml_template: |
  template Test
    with
      party: Party
    where
      signatory party
authorization_requirements:
  - id: REQ-AUTH-001
    rule: Test rule
    satisfied: true
    explanation: Test explanation
when_to_use: [Test scenarios]
when_not_to_use: [Non-test scenarios]
security_considerations: [Test security]
test_cases:
  - description: Test case
    passes: true
    code: test code
""")
            
            # Reload single file
            loader._reload_single_file(test_file)
            
            # Check that resource was updated
            updated_resource = registry.get_resource("canton://canonical/patterns/test-pattern/v1.0.0")
            assert updated_resource is not None
            assert updated_resource.metadata.description == "Updated test pattern"
    
    def test_reload_single_file_anti_pattern(self):
        """Test reloading a single anti-pattern file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test structure
            anti_patterns_dir = Path(temp_dir) / "anti-patterns"
            anti_patterns_dir.mkdir()
            
            # Create test file
            test_file = anti_patterns_dir / "test-anti-pattern.yaml"
            test_file.write_text("""
name: test-anti-pattern
version: "1.0.0"
description: Test anti-pattern
tags: [test]
author: Test Author
created_at: "2024-01-15T10:00:00Z"
anti_pattern_type: test
severity: high
problematic_code: |
  template Bad
    with
      party: Party
    where
      observer party
why_problematic: This is problematic because...
detection_pattern: [Pattern to detect]
correct_alternative: |
  template Good
    with
      party: Party
    where
      signatory party
impact:
  - type: correctness
    severity: high
    description: Test impact
remediation: [Fix the issue]
""")
            
            # Create loader with fresh registry
            registry = ResourceRegistry()
            loader = ResourceLoader(resources_dir=temp_dir)
            loader.registry = registry
            
            # Load initial resource
            resource = loader._load_resource_file(test_file, ResourceCategory.ANTI_PATTERN)
            assert resource is not None
            registry.register(resource)
            
            # Modify file
            test_file.write_text("""
name: test-anti-pattern
version: "1.0.0"
description: Updated test anti-pattern
tags: [test]
author: Test Author
created_at: "2024-01-15T10:00:00Z"
anti_pattern_type: test
severity: critical
problematic_code: |
  template Bad
    with
      party: Party
    where
      observer party
why_problematic: This is problematic because...
detection_pattern: [Pattern to detect]
correct_alternative: |
  template Good
    with
      party: Party
    where
      signatory party
impact:
  - type: correctness
    severity: critical
    description: Test impact
remediation: [Fix the issue]
""")
            
            # Reload single file
            loader._reload_single_file(test_file)
            
            # Check that resource was updated
            updated_resource = registry.get_resource("canton://canonical/anti-patterns/test-anti-pattern/v1.0.0")
            assert updated_resource is not None
            assert updated_resource.metadata.description == "Updated test anti-pattern"
    
    def test_reload_single_file_invalid_category(self):
        """Test reloading a file with unknown category"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test file in unknown directory
            unknown_dir = Path(temp_dir) / "unknown"
            unknown_dir.mkdir()
            test_file = unknown_dir / "test.yaml"
            test_file.write_text("""
name: test
version: "1.0.0"
description: Test
""")
            
            registry = ResourceRegistry()
            loader = ResourceLoader(resources_dir=temp_dir)
            loader.registry = registry
            
            # Should not crash, just log warning
            loader._reload_single_file(test_file)
            
            # No resource should be registered
            assert len(registry.list_resources()) == 0
    
    def test_reload_single_file_invalid_yaml(self):
        """Test reloading a file with invalid YAML"""
        with tempfile.TemporaryDirectory() as temp_dir:
            patterns_dir = Path(temp_dir) / "patterns"
            patterns_dir.mkdir()
            
            # Create invalid YAML file
            test_file = patterns_dir / "invalid.yaml"
            test_file.write_text("invalid: yaml: content: [")
            
            registry = ResourceRegistry()
            loader = ResourceLoader(resources_dir=temp_dir)
            loader.registry = registry
            
            # Should not crash, just log error
            loader._reload_single_file(test_file)
            
            # No resource should be registered
            assert len(registry.list_resources()) == 0


class TestResourceLoaderGlobalFunctions:
    """Test global loader functions"""
    
    def test_get_loader_with_hot_reload(self):
        """Test getting loader with hot-reload enabled"""
        # Reset global loader
        import canton_mcp_server.core.resources.loader as loader_module
        loader_module._loader = None
        
        loader = get_loader(enable_hot_reload=True)
        assert loader.enable_hot_reload is True
        
        # Second call should return same instance
        loader2 = get_loader(enable_hot_reload=False)
        assert loader is loader2  # Same instance
    
    def test_load_resources_with_hot_reload(self):
        """Test loading resources with hot-reload"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test structure
            patterns_dir = Path(temp_dir) / "patterns"
            patterns_dir.mkdir()
            
            test_file = patterns_dir / "test.yaml"
            test_file.write_text("""
name: test
version: "1.0.0"
description: Test
tags: [test]
pattern_type: test
""")
            
            # Reset global loader
            import canton_mcp_server.core.resources.loader as loader_module
            loader_module._loader = None
            
            # Load with hot-reload enabled
            with patch('canton_mcp_server.core.resources.loader.ResourceLoader._start_file_watcher') as mock_start:
                load_resources(enable_hot_reload=True)
                mock_start.assert_called_once()
    
    def test_stop_hot_reload(self):
        """Test stopping hot-reload"""
        # Reset global loader
        import canton_mcp_server.core.resources.loader as loader_module
        loader_module._loader = None
        
        # Create loader with mock observer
        loader = get_loader(enable_hot_reload=True)
        mock_observer = MagicMock()
        loader.observer = mock_observer
        
        # Stop hot-reload
        stop_hot_reload()
        
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()


class TestResourceLoaderIntegration:
    """Integration tests for resource loader"""
    
    def test_full_workflow_with_hot_reload(self):
        """Test complete workflow with hot-reload enabled"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test structure
            patterns_dir = Path(temp_dir) / "patterns"
            patterns_dir.mkdir()
            
            # Create initial file
            test_file = patterns_dir / "workflow-test.yaml"
            test_file.write_text("""
name: workflow-test
version: "1.0.0"
description: Initial description
tags: [test]
author: Test Author
created_at: "2024-01-15T10:00:00Z"
pattern_type: test
daml_template: |
  template Test
    with
      party: Party
    where
      signatory party
authorization_requirements:
  - id: REQ-AUTH-001
    rule: Test rule
    satisfied: true
    explanation: Test explanation
when_to_use: [Test scenarios]
when_not_to_use: [Non-test scenarios]
security_considerations: [Test security]
test_cases:
  - description: Test case
    passes: true
    code: test code
""")
            
            # Reset global loader
            import canton_mcp_server.core.resources.loader as loader_module
            loader_module._loader = None
            
            # Load resources from temp directory
            loader = ResourceLoader(resources_dir=temp_dir, enable_hot_reload=True)
            loader.load_all_resources()
            
            # Check initial load
            initial_resource = loader.registry.get_resource("canton://canonical/patterns/workflow-test/v1.0.0")
            assert initial_resource is not None
            assert initial_resource.metadata.description == "Initial description"
            
            # Modify file
            test_file.write_text("""
name: workflow-test
version: "1.0.0"
description: Updated description
tags: [test]
author: Test Author
created_at: "2024-01-15T10:00:00Z"
pattern_type: test
daml_template: |
  template Test
    with
      party: Party
    where
      signatory party
authorization_requirements:
  - id: REQ-AUTH-001
    rule: Test rule
    satisfied: true
    explanation: Test explanation
when_to_use: [Test scenarios]
when_not_to_use: [Non-test scenarios]
security_considerations: [Test security]
test_cases:
  - description: Test case
    passes: true
    code: test code
""")
            
            # Simulate file change (normally done by file watcher)
            loader._reload_single_file(test_file)
            
            # Check updated resource
            updated_resource = loader.registry.get_resource("canton://canonical/patterns/workflow-test/v1.0.0")
            assert updated_resource is not None
            assert updated_resource.metadata.description == "Updated description"
            
            # Stop hot-reload
            loader.stop_file_watcher()
