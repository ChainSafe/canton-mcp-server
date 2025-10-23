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
from ..core.git_verified_loader import GitVerifiedResourceLoader

logger = logging.getLogger(__name__)

# Global Git-verified loader instance
_git_loader: Optional[GitVerifiedResourceLoader] = None


def get_git_loader() -> GitVerifiedResourceLoader:
    """Get or create the Git-verified resource loader."""
    global _git_loader
    
    if _git_loader is None:
        # Initialize with default paths
        resources_dir = Path("resources")
        canonical_docs_path = Path("../canonical-daml-docs")
        
        _git_loader = GitVerifiedResourceLoader(resources_dir, canonical_docs_path)
        
        # Validate official repositories on first use
        if not _git_loader.validate_official_repos():
            logger.warning("Some official repositories failed validation")
    
    return _git_loader


def handle_resources_list() -> ListResourcesResult:
    """
    Handle resources/list request with Git verification.
    
    Returns list of available Git-verified Canton canonical resources.
    
    Returns:
        ListResourcesResult with available resources
    """
    loader = get_git_loader()
    all_resources = loader.load_all_resources()
    
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
            
            # Add Git verification metadata
            mcp_resource._meta = {
                "canonical_hash": resource.get("canonical_hash"),
                "source_commit": resource.get("source_commit"),
                "source_file": resource.get("source_file"),
                "extracted_at": resource.get("extracted_at"),
                "resource_type": resource_type,
                "git_verified": True
            }
            
            mcp_resources.append(mcp_resource)
    
    logger.info(f"Returning {len(mcp_resources)} Git-verified resources")
    return ListResourcesResult(resources=mcp_resources)


def handle_resources_read(uri: str) -> ReadResourceResult:
    """
    Handle resources/read request with Git verification.
    
    Args:
        uri: Resource URI to read (format: canton://{type}/{name})
        
    Returns:
        ReadResourceResult with Git-verified resource contents
        
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
    
    # Get resource from Git-verified loader
    loader = get_git_loader()
    resource = loader.get_resource_by_name(resource_name, resource_type)
    
    if not resource:
        raise ValueError(f"Git-verified resource not found: {uri}")
    
    # Serialize resource content as JSON
    content_text = json.dumps(resource, indent=2)
    
    # Create resource contents with Git verification metadata
    resource_contents = TextResourceContents(
        uri=uri,
        text=content_text,
        mime_type="application/json"
    )
    
    logger.info(f"Read Git-verified resource: {uri} (hash: {resource.get('canonical_hash', 'unknown')})")
    return ReadResourceResult(contents=[resource_contents])


def handle_resources_subscribe(uri: str) -> Dict[str, Any]:
    """
    Handle resources/subscribe request with Git verification.
    
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
    
    # Check if Git-verified resource exists
    loader = get_git_loader()
    resource = loader.get_resource_by_name(resource_name, resource_type)
    
    if not resource:
        raise ValueError(f"Git-verified resource not found: {uri}")
    
    # TODO: Implement actual subscription mechanism for Git-verified resources
    logger.info(f"Subscribed to Git-verified resource: {uri} (hash: {resource.get('canonical_hash', 'unknown')})")
    return {}


def handle_resources_unsubscribe(uri: str) -> Dict[str, Any]:
    """
    Handle resources/unsubscribe request with Git verification.
    
    Args:
        uri: Resource URI to unsubscribe from
        
    Returns:
        Empty dict (unsubscription confirmation)
    """
    # TODO: Implement actual unsubscription mechanism for Git-verified resources
    logger.info(f"Unsubscribed from Git-verified resource: {uri}")
    return {}
