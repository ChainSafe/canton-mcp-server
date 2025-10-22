"""
Canonical Resource Registry

Manages Canton canonical resources (patterns, anti-patterns, rules, docs).
Provides resource discovery and retrieval functionality.
"""

import logging
from typing import Dict, List, Optional

from .base import CanonicalResource, ResourceCategory, parse_canton_uri

logger = logging.getLogger(__name__)


class ResourceRegistry:
    """Registry for Canton canonical resources"""
    
    def __init__(self):
        self._resources: Dict[str, CanonicalResource] = {}
        self._by_category: Dict[ResourceCategory, List[CanonicalResource]] = {
            category: [] for category in ResourceCategory
        }
    
    def register(self, resource: CanonicalResource) -> None:
        """
        Register a canonical resource.
        
        Args:
            resource: Resource to register
        """
        uri = resource.uri
        
        # Validate resource
        errors = resource.validate()
        if errors:
            logger.error(f"Invalid resource {uri}: {errors}")
            return
        
        # Check for conflicts
        if uri in self._resources:
            logger.warning(f"Resource {uri} already registered, replacing")
        
        # Register resource
        self._resources[uri] = resource
        self._by_category[resource.metadata.category].append(resource)
        
        logger.debug(f"Registered resource: {uri}")
    
    def unregister(self, uri: str) -> bool:
        """
        Unregister a resource by URI.
        
        Args:
            uri: Resource URI to unregister
            
        Returns:
            True if resource was found and unregistered, False otherwise
        """
        if uri not in self._resources:
            return False
        
        resource = self._resources[uri]
        del self._resources[uri]
        
        # Remove from category list
        category_resources = self._by_category[resource.metadata.category]
        if resource in category_resources:
            category_resources.remove(resource)
        
        logger.debug(f"Unregistered resource: {uri}")
        return True
    
    def get_resource(self, uri: str) -> Optional[CanonicalResource]:
        """
        Get a resource by URI.
        
        Args:
            uri: Resource URI
            
        Returns:
            Resource if found, None otherwise
        """
        return self._resources.get(uri)
    
    def list_resources(self, category: Optional[ResourceCategory] = None) -> List[CanonicalResource]:
        """
        List all resources, optionally filtered by category.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of resources
        """
        if category is None:
            return list(self._resources.values())
        
        return self._by_category[category].copy()
    
    def search_resources(self, query: str) -> List[CanonicalResource]:
        """
        Search resources by name, description, or tags.
        
        Args:
            query: Search query
            
        Returns:
            List of matching resources
        """
        query_lower = query.lower()
        matches = []
        
        for resource in self._resources.values():
            # Search in name
            if query_lower in resource.name.lower():
                matches.append(resource)
                continue
            
            # Search in description
            if resource.metadata.description and query_lower in resource.metadata.description.lower():
                matches.append(resource)
                continue
            
            # Search in tags
            for tag in resource.metadata.tags:
                if query_lower in tag.lower():
                    matches.append(resource)
                    break
        
        return matches
    
    def get_resource_by_components(self, category: str, name: str, version: str) -> Optional[CanonicalResource]:
        """
        Get a resource by its components.
        
        Args:
            category: Resource category
            name: Resource name
            version: Resource version
            
        Returns:
            Resource if found, None otherwise
        """
        uri = f"canton://canonical/{category}/{name}/v{version}"
        return self.get_resource(uri)
    
    def validate_uri(self, uri: str) -> bool:
        """
        Validate that a URI follows the canton://canonical/* scheme.
        
        Args:
            uri: URI to validate
            
        Returns:
            True if valid, False otherwise
        """
        return parse_canton_uri(uri) is not None
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get registry statistics.
        
        Returns:
            Dict with resource counts by category
        """
        stats = {
            "total": len(self._resources),
            "by_category": {}
        }
        
        for category in ResourceCategory:
            stats["by_category"][category.value] = len(self._by_category[category])
        
        return stats


# Global registry instance
_registry: Optional[ResourceRegistry] = None


def get_registry() -> ResourceRegistry:
    """Get the global resource registry instance"""
    global _registry
    if _registry is None:
        _registry = ResourceRegistry()
    return _registry


def register_resource(resource: CanonicalResource) -> None:
    """Register a resource in the global registry"""
    get_registry().register(resource)


def get_resource(uri: str) -> Optional[CanonicalResource]:
    """Get a resource from the global registry"""
    return get_registry().get_resource(uri)


def list_resources(category: Optional[ResourceCategory] = None) -> List[CanonicalResource]:
    """List resources from the global registry"""
    return get_registry().list_resources(category)
