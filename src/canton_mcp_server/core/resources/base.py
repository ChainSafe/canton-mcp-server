"""
Canonical Resource Base Model

Base classes for Canton canonical resources (patterns, anti-patterns, rules, docs).
Supports the canton://canonical/* URI scheme and resource metadata.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ..types.mcp import Resource


class ResourceCategory(Enum):
    """Resource categories for canton://canonical/* URIs"""
    
    PATTERN = "patterns"
    ANTI_PATTERN = "anti-patterns" 
    RULE = "rules"
    DOC = "docs"


@dataclass
class CanonicalResourceMetadata:
    """Metadata for canonical resources"""
    
    version: str
    category: ResourceCategory
    tags: List[str]
    description: Optional[str] = None
    author: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CanonicalResource(ABC):
    """Base class for Canton canonical resources"""
    
    def __init__(
        self,
        name: str,
        metadata: CanonicalResourceMetadata,
        content: Dict[str, Any]
    ):
        self.name = name
        self.metadata = metadata
        self.content = content
        self._uri = self._generate_uri()
    
    def _generate_uri(self) -> str:
        """Generate canton://canonical/* URI for this resource"""
        return f"canton://canonical/{self.metadata.category.value}/{self.name}/v{self.metadata.version}"
    
    @property
    def uri(self) -> str:
        """Get the resource URI"""
        return self._uri
    
    @property
    def mcp_resource(self) -> Resource:
        """Convert to MCP Resource for protocol responses"""
        return Resource(
            uri=self.uri,
            name=self.name,
            description=self.metadata.description,
            mime_type="application/yaml",
            annotations={
                "category": self.metadata.category.value,
                "version": self.metadata.version,
                "tags": self.metadata.tags
            }
        )
    
    def get_content(self) -> Dict[str, Any]:
        """Get the resource content"""
        return self.content
    
    def validate(self) -> List[str]:
        """Validate the resource content. Returns list of validation errors."""
        errors = []
        
        # Basic validation
        if not self.name:
            errors.append("Resource name cannot be empty")
        
        if not self.metadata.version:
            errors.append("Resource version cannot be empty")
        
        if not self.metadata.tags:
            errors.append("Resource must have at least one tag")
        
        return errors


class PatternResource(CanonicalResource):
    """Canonical pattern resource"""
    
    def __init__(self, name: str, metadata: CanonicalResourceMetadata, content: Dict[str, Any]):
        super().__init__(name, metadata, content)
        self.metadata.category = ResourceCategory.PATTERN


class AntiPatternResource(CanonicalResource):
    """Canonical anti-pattern resource"""
    
    def __init__(self, name: str, metadata: CanonicalResourceMetadata, content: Dict[str, Any]):
        super().__init__(name, metadata, content)
        self.metadata.category = ResourceCategory.ANTI_PATTERN


class RuleResource(CanonicalResource):
    """Canonical rule resource"""
    
    def __init__(self, name: str, metadata: CanonicalResourceMetadata, content: Dict[str, Any]):
        super().__init__(name, metadata, content)
        self.metadata.category = ResourceCategory.RULE


class DocResource(CanonicalResource):
    """Canonical documentation resource"""
    
    def __init__(self, name: str, metadata: CanonicalResourceMetadata, content: Dict[str, Any]):
        super().__init__(name, metadata, content)
        self.metadata.category = ResourceCategory.DOC


def parse_canton_uri(uri: str) -> Optional[Dict[str, str]]:
    """
    Parse canton://canonical/* URI into components.
    
    Args:
        uri: URI to parse (e.g., "canton://canonical/patterns/simple-transfer/v1.0")
        
    Returns:
        Dict with keys: scheme, category, name, version, or None if invalid
    """
    try:
        parsed = urlparse(uri)
        
        if parsed.scheme != "canton":
            return None
        
        # Handle canton://canonical/... format
        if parsed.netloc == "canonical":
            # Extract path components: /{category}/{name}/v{version}
            path_parts = parsed.path.strip("/").split("/")
            
            if len(path_parts) != 3:
                return None
            
            category = path_parts[0]
            name = path_parts[1]
            version_part = path_parts[2]
        else:
            return None
        
        if not version_part.startswith("v"):
            return None
        
        version = version_part[1:]  # Remove 'v' prefix
        
        return {
            "scheme": parsed.scheme,
            "category": category,
            "name": name,
            "version": version
        }
        
    except Exception:
        return None
