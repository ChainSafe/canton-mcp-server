"""
Resource Loader

Loads Canton canonical resources from YAML files.
Supports hot-reloading during development.
"""

import logging
import os
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    AntiPatternResource,
    CanonicalResourceMetadata,
    DocResource,
    PatternResource,
    ResourceCategory,
    RuleResource,
)
from .registry import get_registry

logger = logging.getLogger(__name__)


class ResourceLoader:
    """Loads resources from YAML files"""
    
    def __init__(self, resources_dir: str = "resources"):
        self.resources_dir = Path(resources_dir)
        self.registry = get_registry()
    
    def load_all_resources(self) -> None:
        """Load all resources from the resources directory"""
        if not self.resources_dir.exists():
            logger.warning(f"Resources directory not found: {self.resources_dir}")
            return
        
        # Load resources by category
        self._load_category_resources(ResourceCategory.PATTERN, "patterns")
        self._load_category_resources(ResourceCategory.ANTI_PATTERN, "anti-patterns")
        self._load_category_resources(ResourceCategory.RULE, "rules")
        self._load_category_resources(ResourceCategory.DOC, "docs")
        
        stats = self.registry.get_stats()
        logger.info(f"Loaded {stats['total']} resources")
    
    def _load_category_resources(self, category: ResourceCategory, dir_name: str) -> None:
        """Load resources from a specific category directory"""
        category_dir = self.resources_dir / dir_name
        
        if not category_dir.exists():
            logger.debug(f"Category directory not found: {category_dir}")
            return
        
        yaml_files = list(category_dir.glob("*.yaml")) + list(category_dir.glob("*.yml"))
        
        for yaml_file in yaml_files:
            try:
                resource = self._load_resource_file(yaml_file, category)
                if resource:
                    self.registry.register(resource)
            except Exception as e:
                logger.error(f"Failed to load resource {yaml_file}: {e}")
    
    def _load_resource_file(self, file_path: Path, category: ResourceCategory) -> Optional[Any]:
        """Load a single resource from a YAML file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data:
                logger.warning(f"Empty YAML file: {file_path}")
                return None
            
            # Extract metadata
            name = data.get('name')
            version = data.get('version')
            description = data.get('description')
            tags = data.get('tags', [])
            author = data.get('author')
            created_at = data.get('created_at')
            updated_at = data.get('updated_at')
            
            if not name or not version:
                logger.error(f"Missing name or version in {file_path}")
                return None
            
            # Create metadata
            metadata = CanonicalResourceMetadata(
                version=str(version),
                category=category,
                tags=tags,
                description=description,
                author=author,
                created_at=created_at,
                updated_at=updated_at
            )
            
            # Extract content (everything except metadata fields)
            content = {k: v for k, v in data.items() 
                      if k not in ['name', 'version', 'category', 'description', 
                                 'tags', 'author', 'created_at', 'updated_at']}
            
            # Create appropriate resource type
            resource = None
            if category == ResourceCategory.PATTERN:
                resource = PatternResource(name, metadata, content)
            elif category == ResourceCategory.ANTI_PATTERN:
                resource = AntiPatternResource(name, metadata, content)
            elif category == ResourceCategory.RULE:
                resource = RuleResource(name, metadata, content)
            elif category == ResourceCategory.DOC:
                resource = DocResource(name, metadata, content)
            else:
                logger.error(f"Unknown category: {category}")
                return None
            
            # Validate the resource before returning
            validation_errors = resource.validate()
            if validation_errors:
                logger.error(f"Resource validation failed for {file_path}: {validation_errors}")
                return None
            
            return resource
                
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error in {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading {file_path}: {e}")
            return None
    
    def reload_resources(self) -> None:
        """Reload all resources (useful for development)"""
        logger.info("Reloading all resources...")
        
        # Clear existing resources
        for uri in list(self.registry._resources.keys()):
            self.registry.unregister(uri)
        
        # Reload from files
        self.load_all_resources()


# Global loader instance
_loader: Optional[ResourceLoader] = None


def get_loader() -> ResourceLoader:
    """Get the global resource loader instance"""
    global _loader
    if _loader is None:
        _loader = ResourceLoader()
    return _loader


def load_resources() -> None:
    """Load all resources using the global loader"""
    get_loader().load_all_resources()


def reload_resources() -> None:
    """Reload all resources using the global loader"""
    get_loader().reload_resources()
