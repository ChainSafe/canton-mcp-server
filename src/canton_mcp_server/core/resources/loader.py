"""
Resource Loader

Loads Canton canonical resources from YAML files.
Supports hot-reloading during development.
"""

import logging
import os
import threading
import time
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

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


class ResourceFileHandler(FileSystemEventHandler):
    """Handles file system events for resource hot-reloading"""
    
    def __init__(self, loader: 'ResourceLoader'):
        self.loader = loader
        self.last_reload = 0
        self.reload_delay = 1.0  # Debounce reloads by 1 second
    
    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return
        
        # Only handle YAML files
        if not (event.src_path.endswith('.yaml') or event.src_path.endswith('.yml')):
            return
        
        # Debounce rapid file changes
        current_time = time.time()
        if current_time - self.last_reload < self.reload_delay:
            return
        
        self.last_reload = current_time
        
        # Reload the specific file
        file_path = Path(event.src_path)
        logger.info(f"Resource file changed: {file_path}")
        
        try:
            self.loader._reload_single_file(file_path)
        except Exception as e:
            logger.error(f"Failed to reload {file_path}: {e}")


class ResourceLoader:
    """Loads resources from YAML files with hot-reloading support"""
    
    def __init__(self, resources_dir: str = "resources", enable_hot_reload: bool = False):
        self.resources_dir = Path(resources_dir)
        self.registry = get_registry()
        self.enable_hot_reload = enable_hot_reload
        self.observer: Optional[Observer] = None
        self._file_timestamps: Dict[str, float] = {}
    
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
        
        # Start file watcher if hot-reload is enabled
        if self.enable_hot_reload:
            self._start_file_watcher()
    
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
    
    def _start_file_watcher(self) -> None:
        """Start the file system watcher for hot-reloading"""
        if self.observer is not None:
            return  # Already started
        
        try:
            self.observer = Observer()
            event_handler = ResourceFileHandler(self)
            
            # Watch the entire resources directory
            self.observer.schedule(event_handler, str(self.resources_dir), recursive=True)
            self.observer.start()
            
            logger.info(f"Started file watcher for hot-reloading: {self.resources_dir}")
        except Exception as e:
            logger.error(f"Failed to start file watcher: {e}")
            self.observer = None
    
    def stop_file_watcher(self) -> None:
        """Stop the file system watcher"""
        if self.observer is not None:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logger.info("Stopped file watcher")
    
    def _reload_single_file(self, file_path: Path) -> None:
        """Reload a single resource file"""
        # Determine category from file path
        category = None
        category_name = None
        
        for parent in file_path.parents:
            if parent.name == "patterns":
                category = ResourceCategory.PATTERN
                category_name = "patterns"
                break
            elif parent.name == "anti-patterns":
                category = ResourceCategory.ANTI_PATTERN
                category_name = "anti-patterns"
                break
            elif parent.name == "rules":
                category = ResourceCategory.RULE
                category_name = "rules"
                break
            elif parent.name == "docs":
                category = ResourceCategory.DOC
                category_name = "docs"
                break
        
        if category is None:
            logger.warning(f"Could not determine category for file: {file_path}")
            return
        
        # Find and unregister existing resource with same name
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if data and 'name' in data:
                resource_name = data['name']
                uri = f"canton://canonical/{category_name}/{resource_name}/v{data.get('version', '1.0')}"
                
                # Unregister existing resource
                if self.registry.get_resource(uri):
                    self.registry.unregister(uri)
                    logger.info(f"Unregistered existing resource: {uri}")
                
                # Load new resource
                resource = self._load_resource_file(file_path, category)
                if resource:
                    self.registry.register(resource)
                    logger.info(f"Reloaded resource: {uri}")
                else:
                    logger.error(f"Failed to reload resource: {file_path}")
        
        except Exception as e:
            logger.error(f"Error reloading single file {file_path}: {e}")


# Global loader instance
_loader: Optional[ResourceLoader] = None


def get_loader(enable_hot_reload: bool = False) -> ResourceLoader:
    """Get the global resource loader instance"""
    global _loader
    if _loader is None:
        _loader = ResourceLoader(enable_hot_reload=enable_hot_reload)
    return _loader


def load_resources(enable_hot_reload: bool = False) -> None:
    """Load all resources using the global loader"""
    get_loader(enable_hot_reload).load_all_resources()


def reload_resources() -> None:
    """Reload all resources using the global loader"""
    get_loader().reload_resources()


def stop_hot_reload() -> None:
    """Stop hot-reloading file watcher"""
    loader = get_loader()
    loader.stop_file_watcher()
