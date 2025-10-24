"""
Git-Verified Resource Handler

Handles MCP resource protocol methods with Git verification:
- resources/list: List available Git-verified resources
- resources/read: Read Git-verified resource contents
"""

import logging
import json
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..core.responses import ErrorCodes
from ..core.responses.resource import ResourceResponse
from ..core.types.mcp import (
    BlobResourceContents,
    ListResourcesResult,
    ReadResourceResult,
    Resource,
    TextResourceContents,
)
from ..core.direct_file_loader import DirectFileResourceLoader

logger = logging.getLogger(__name__)

# Global direct file loader instance
_direct_loader: Optional[DirectFileResourceLoader] = None


def get_direct_loader() -> DirectFileResourceLoader:
    """Get or create the direct file resource loader."""
    global _direct_loader
    
    if _direct_loader is None:
        # Initialize with canonical docs path (relative to project root)
        canonical_docs_path = Path(os.environ.get("CANONICAL_DOCS_PATH", "../canonical-daml-docs"))  # Load from env var
        _direct_loader = DirectFileResourceLoader(canonical_docs_path)
    
    return _direct_loader


def handle_resources_list() -> ListResourcesResult:
    """
    Handle resources/list request with direct file serving.
    
    Returns list of available canonical documentation files from cloned repos.
    
    Returns:
        ListResourcesResult with available resources
    """
    loader = get_direct_loader()
    all_resources = loader.scan_repositories()
    
    # Convert to MCP Resource objects
    mcp_resources = []
    
    for resource_type, resources in all_resources.items():
        for resource in resources:
            # Create MCP Resource with Git verification metadata
            mcp_resource = Resource(
                uri=f"canton://{resource_type}/{resource['name']}",
                name=resource['name'],
                description=resource['description'],
                mime_type="application/json"
            )
            
            # Add direct file metadata
            mcp_resource._meta = {
                "canonical_hash": resource.get("canonical_hash"),
                "source_commit": resource.get("source_commit"),
                "source_file": resource.get("source_file"),
                "source_repo": resource.get("source_repo"),
                "file_path": resource.get("file_path"),
                "file_extension": resource.get("file_extension"),
                "extracted_at": resource.get("extracted_at"),
                "resource_type": resource_type,
                "direct_file": True
            }
            
            mcp_resources.append(mcp_resource)
    
    logger.info(f"Returning {len(mcp_resources)} direct file resources")
    return ListResourcesResult(resources=mcp_resources)


def handle_resources_read(uri: str) -> ReadResourceResult:
    """
    Handle resources/read request with direct file serving.
    
    Args:
        uri: Resource URI to read (format: canton://{type}/{name})
        
    Returns:
        ReadResourceResult with direct file contents
        
    Raises:
        ValueError: If URI is invalid or resource not found
    """
    # Parse Canton URI
    if not uri.startswith("canton://"):
        raise ValueError(f"Invalid Canton URI format: {uri}")
    
    # Extract resource type and name from URI
    uri_parts = uri[9:].split("/")  # Remove "canton://" prefix
    if len(uri_parts) != 2:
        raise ValueError(f"Invalid Canton URI format: {uri}")
    
    resource_type, resource_name = uri_parts
    
    # Validate resource type
    valid_types = ["patterns", "anti_patterns", "rules", "docs"]
    if resource_type not in valid_types:
        raise ValueError(f"Invalid resource type: {resource_type}. Must be one of: {valid_types}")
    
    # Get resource from direct file loader
    loader = get_direct_loader()
    resource = loader.get_resource_by_name(resource_name, resource_type)
    
    if not resource:
        raise ValueError(f"Direct file resource not found: {uri}")
    
    # Get file content directly
    content_text = resource.get("content", "")
    
    # Determine MIME type based on file extension
    file_extension = resource.get("file_extension", "")
    if file_extension == ".md":
        mime_type = "text/markdown"
    elif file_extension == ".rst":
        mime_type = "text/x-rst"
    elif file_extension == ".daml":
        mime_type = "text/x-daml"
    elif file_extension in [".yaml", ".yml"]:
        mime_type = "text/yaml"
    else:
        mime_type = "text/plain"
    
    # Create resource contents with direct file metadata
    resource_contents = TextResourceContents(
        uri=uri,
        text=content_text,
        mime_type=mime_type
    )
    
    logger.info(f"Read direct file resource: {uri} (repo: {resource.get('source_repo', 'unknown')}, file: {resource.get('file_path', 'unknown')})")
    return ReadResourceResult(contents=[resource_contents])


def handle_resources_subscribe(uri: str) -> Dict[str, Any]:
    """
    Handle resources/subscribe request with direct file serving.
    
    Args:
        uri: Resource URI to subscribe to
        
    Returns:
        Empty dict (subscription confirmation)
        
    Raises:
        ValueError: If URI is invalid or resource not found
    """
    # Validate URI format
    if not uri.startswith("canton://"):
        raise ValueError(f"Invalid Canton URI format: {uri}")
    
    # Extract resource type and name from URI
    uri_parts = uri[9:].split("/")
    if len(uri_parts) != 2:
        raise ValueError(f"Invalid Canton URI format: {uri}")
    
    resource_type, resource_name = uri_parts
    
    # Validate resource type
    valid_types = ["patterns", "anti_patterns", "rules", "docs"]
    if resource_type not in valid_types:
        raise ValueError(f"Invalid resource type: {resource_type}")
    
    # Check if direct file resource exists
    loader = get_direct_loader()
    resource = loader.get_resource_by_name(resource_name, resource_type)
    
    if not resource:
        raise ValueError(f"Direct file resource not found: {uri}")
    
    # TODO: Implement actual subscription mechanism for direct file resources
    logger.info(f"Subscribed to direct file resource: {uri} (repo: {resource.get('source_repo', 'unknown')})")
    return {}


def handle_resources_unsubscribe(uri: str) -> Dict[str, Any]:
    """
    Handle resources/unsubscribe request with direct file serving.
    
    Args:
        uri: Resource URI to unsubscribe from
        
    Returns:
        Empty dict (unsubscription confirmation)
    """
    # TODO: Implement actual unsubscription mechanism for direct file resources
    logger.info(f"Unsubscribed from direct file resource: {uri}")
    return {}
