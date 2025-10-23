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
from ..core.github_verified_loader import GitHubVerifiedResourceLoader

logger = logging.getLogger(__name__)

# Global GitHub-verified loader instance
_github_loader: Optional[GitHubVerifiedResourceLoader] = None


def get_github_loader() -> GitHubVerifiedResourceLoader:
    """Get or create the GitHub-verified resource loader."""
    global _github_loader
    
    if _github_loader is None:
        # Initialize with resources directory (relative to project root)
        resources_dir = Path("../../resources")  # Go up from src/canton_mcp_server/ to project root
        _github_loader = GitHubVerifiedResourceLoader(resources_dir)
    
    return _github_loader


def handle_resources_list() -> ListResourcesResult:
    """
    Handle resources/list request with GitHub API verification.
    
    Returns list of available GitHub-verified Canton canonical resources.
    
    Returns:
        ListResourcesResult with available resources
    """
    loader = get_github_loader()
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
            
            # Add GitHub API verification metadata
            mcp_resource._meta = {
                "canonical_hash": resource.get("canonical_hash"),
                "source_commit": resource.get("source_commit"),
                "source_file": resource.get("source_file"),
                "extracted_at": resource.get("extracted_at"),
                "resource_type": resource_type,
                "github_verified": True
            }
            
            mcp_resources.append(mcp_resource)
    
    logger.info(f"Returning {len(mcp_resources)} GitHub-verified resources")
    return ListResourcesResult(resources=mcp_resources)


def handle_resources_read(uri: str) -> ReadResourceResult:
    """
    Handle resources/read request with GitHub API verification.
    
    Args:
        uri: Resource URI to read (format: canton://{type}/{name})
        
    Returns:
        ReadResourceResult with GitHub-verified resource contents
        
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
    
    # Get resource from GitHub-verified loader
    loader = get_github_loader()
    resource = loader.get_resource_by_name(resource_name, resource_type)
    
    if not resource:
        raise ValueError(f"GitHub-verified resource not found: {uri}")
    
    # Serialize resource content as JSON
    content_text = json.dumps(resource, indent=2)
    
    # Create resource contents with GitHub API verification metadata
    resource_contents = TextResourceContents(
        uri=uri,
        text=content_text,
        mime_type="application/json"
    )
    
    logger.info(f"Read GitHub-verified resource: {uri} (hash: {resource.get('canonical_hash', 'unknown')})")
    return ReadResourceResult(contents=[resource_contents])


def handle_resources_subscribe(uri: str) -> Dict[str, Any]:
    """
    Handle resources/subscribe request with GitHub API verification.
    
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
    
    # Check if GitHub-verified resource exists
    loader = get_github_loader()
    resource = loader.get_resource_by_name(resource_name, resource_type)
    
    if not resource:
        raise ValueError(f"GitHub-verified resource not found: {uri}")
    
    # TODO: Implement actual subscription mechanism for GitHub-verified resources
    logger.info(f"Subscribed to GitHub-verified resource: {uri} (hash: {resource.get('canonical_hash', 'unknown')})")
    return {}


def handle_resources_unsubscribe(uri: str) -> Dict[str, Any]:
    """
    Handle resources/unsubscribe request with GitHub API verification.
    
    Args:
        uri: Resource URI to unsubscribe from
        
    Returns:
        Empty dict (unsubscription confirmation)
    """
    # TODO: Implement actual unsubscription mechanism for GitHub-verified resources
    logger.info(f"Unsubscribed from GitHub-verified resource: {uri}")
    return {}
