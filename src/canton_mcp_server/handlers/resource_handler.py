"""
Resource Handler

Handles MCP resource protocol methods:
- resources/list: List available resources
- resources/read: Read resource contents
"""

import logging
from typing import Any, Dict, List, Optional

from ..core.responses import ErrorCodes
from ..core.responses.resource import ResourceResponse
from ..core.types.mcp import (
    BlobResourceContents,
    ListResourcesResult,
    ReadResourceResult,
    Resource,
    TextResourceContents,
)
from ..core.resources.registry import get_registry, parse_canton_uri

logger = logging.getLogger(__name__)


def handle_resources_list() -> ListResourcesResult:
    """
    Handle resources/list request.
    
    Returns list of available Canton canonical resources.
    
    Returns:
        ListResourcesResult with available resources
    """
    registry = get_registry()
    resources = registry.list_resources()
    
    # Convert to MCP Resource objects
    mcp_resources = [resource.mcp_resource for resource in resources]
    
    logger.info(f"Returning {len(mcp_resources)} resources")
    return ListResourcesResult(resources=mcp_resources)


def handle_resources_read(uri: str) -> ReadResourceResult:
    """
    Handle resources/read request.
    
    Args:
        uri: Resource URI to read
        
    Returns:
        ReadResourceResult with resource contents
        
    Raises:
        ValueError: If URI is invalid or resource not found
    """
    # Validate URI format
    parsed = parse_canton_uri(uri)
    if not parsed:
        raise ValueError(f"Invalid Canton URI format: {uri}")
    
    # Get resource from registry
    registry = get_registry()
    resource = registry.get_resource(uri)
    
    if not resource:
        raise ValueError(f"Resource not found: {uri}")
    
    # Get resource content
    content = resource.get_content()
    
    # Convert to MCP resource contents
    # For now, we'll serialize as JSON text
    import json
    content_text = json.dumps(content, indent=2)
    
    resource_contents = TextResourceContents(
        uri=uri,
        text=content_text,
        mime_type="application/json"
    )
    
    logger.info(f"Read resource: {uri}")
    return ReadResourceResult(contents=[resource_contents])


def handle_resources_subscribe(uri: str) -> Dict[str, Any]:
    """
    Handle resources/subscribe request.
    
    Args:
        uri: Resource URI to subscribe to
        
    Returns:
        Empty dict (subscription confirmation)
        
    Raises:
        ValueError: If URI is invalid or resource not found
    """
    # Validate URI format
    parsed = parse_canton_uri(uri)
    if not parsed:
        raise ValueError(f"Invalid Canton URI format: {uri}")
    
    # Check if resource exists
    registry = get_registry()
    resource = registry.get_resource(uri)
    
    if not resource:
        raise ValueError(f"Resource not found: {uri}")
    
    # TODO: Implement actual subscription mechanism
    # For now, just confirm the subscription
    logger.info(f"Subscribed to resource: {uri}")
    return {}


def handle_resources_unsubscribe(uri: str) -> Dict[str, Any]:
    """
    Handle resources/unsubscribe request.
    
    Args:
        uri: Resource URI to unsubscribe from
        
    Returns:
        Empty dict (unsubscription confirmation)
    """
    # TODO: Implement actual unsubscription mechanism
    logger.info(f"Unsubscribed from resource: {uri}")
    return {}
