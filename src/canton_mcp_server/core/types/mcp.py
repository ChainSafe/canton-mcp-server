"""
MCP Protocol Type Definitions

Based on MCP Specification 2025-06-18
https://modelcontextprotocol.io/specification/2025-06-18/schema
"""

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

# Import conversion utilities from utils module
from canton_mcp_server.utils.conversion import convert_keys_to_camel_case

# =============================================================================
# Base Classes
# =============================================================================


class SerializableMixin:
    """Mixin class providing JSON and dictionary serialization utilities

    Provides both snake_case (original) and camelCase serialization methods
    for all dataclasses that inherit from this mixin.
    """

    def to_json(self) -> str:
        """Convert to JSON string with snake_case keys

        Returns:
            JSON string representation with original snake_case keys
        """
        import json

        return json.dumps(asdict(self))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with snake_case keys

        Returns:
            Dictionary representation with original snake_case keys
        """
        return asdict(self)

    def to_camel_json(self) -> str:
        """Convert to JSON string with camelCase keys and null filtering

        Returns:
            JSON string representation with camelCase keys and null values excluded
        """
        import json

        return json.dumps(convert_keys_to_camel_case(asdict(self)))

    def to_camel_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with camelCase keys and null filtering

        Returns:
            Dictionary representation with camelCase keys and null values excluded
        """
        return convert_keys_to_camel_case(asdict(self))


# =============================================================================
# Base Types
# =============================================================================

RequestId = Union[str, int, None]
ProgressToken = str
Cursor = str


class Role(str, Enum):
    """Role in a conversation"""

    USER = "user"
    ASSISTANT = "assistant"


# =============================================================================
# Annotations
# =============================================================================


@dataclass
class Annotations:
    """Optional annotations for the client"""

    audience: Optional[List[Role]] = None
    last_modified: Optional[str] = None  # ISO 8601 string
    priority: Optional[float] = None  # 0 (least) to 1 (most important)


# =============================================================================
# Content Types
# =============================================================================


@dataclass
class TextContent:
    """Text content block"""

    text: str
    type: Literal["text"] = "text"
    annotations: Optional[Annotations] = None
    _meta: Optional[Dict[str, Any]] = None


@dataclass
class ImageContent:
    """Image content block"""

    data: str  # base64-encoded
    mime_type: str
    type: Literal["image"] = "image"
    annotations: Optional[Annotations] = None
    _meta: Optional[Dict[str, Any]] = None


@dataclass
class AudioContent:
    """Audio content block"""

    data: str  # base64-encoded
    mime_type: str
    type: Literal["audio"] = "audio"
    annotations: Optional[Annotations] = None
    _meta: Optional[Dict[str, Any]] = None


@dataclass
class ResourceLink:
    """Link to a resource"""

    uri: str
    type: Literal["resource"] = "resource"
    annotations: Optional[Annotations] = None
    _meta: Optional[Dict[str, Any]] = None


@dataclass
class EmbeddedResource:
    """Embedded resource content"""

    resource: Union["TextResourceContents", "BlobResourceContents"]
    type: Literal["resource"] = "resource"
    annotations: Optional[Annotations] = None
    _meta: Optional[Dict[str, Any]] = None


# Union type for all content blocks
ContentBlock = Union[
    TextContent, ImageContent, AudioContent, ResourceLink, EmbeddedResource
]


# =============================================================================
# Resource Types
# =============================================================================


@dataclass
class TextResourceContents:
    """Text resource contents"""

    uri: str
    text: str
    mime_type: Optional[str] = None
    _meta: Optional[Dict[str, Any]] = None


@dataclass
class BlobResourceContents:
    """Binary resource contents"""

    uri: str
    blob: str  # base64-encoded
    mime_type: Optional[str] = None
    _meta: Optional[Dict[str, Any]] = None


ResourceContents = Union[TextResourceContents, BlobResourceContents]


@dataclass
class Resource:
    """Resource definition"""

    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None
    annotations: Optional[Annotations] = None
    _meta: Optional[Dict[str, Any]] = None


# =============================================================================
# Tool Types
# =============================================================================


@dataclass
class Tool(SerializableMixin):
    """Tool definition"""

    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema
    output_schema: Optional[Dict[str, Any]] = None
    annotations: Optional[Annotations] = None
    _meta: Optional[Dict[str, Any]] = None


# =============================================================================
# JSON-RPC Types
# =============================================================================


@dataclass
class JSONRPCError:
    """JSON-RPC error object"""

    code: int
    message: str
    data: Optional[Any] = None


@dataclass
class JSONRPCRequest:
    """JSON-RPC request"""

    jsonrpc: Literal["2.0"] = "2.0"
    id: RequestId = None
    method: str = ""
    params: Optional[Dict[str, Any]] = None


@dataclass
class JSONRPCResponse(SerializableMixin):
    """JSON-RPC response"""

    jsonrpc: Literal["2.0"] = "2.0"
    id: RequestId = None
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None


@dataclass
class JSONRPCNotification(SerializableMixin):
    """JSON-RPC notification (no response expected)"""

    jsonrpc: Literal["2.0"] = "2.0"
    method: str = ""
    params: Optional[Dict[str, Any]] = None


# =============================================================================
# MCP Result Types
# =============================================================================


@dataclass
class Result:
    """Base result type"""

    _meta: Optional[Dict[str, Any]] = None


@dataclass
class EmptyResult(Result):
    """Empty result indicating success"""

    pass


@dataclass
class PaginatedResult(Result):
    """Result with pagination support"""

    next_cursor: Optional[Cursor] = None


# =============================================================================
# Tool Call Types
# =============================================================================


@dataclass
class CallToolRequest:
    """Request to call a tool"""

    method: Literal["tools/call"] = "tools/call"
    params: Dict[str, Any] = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}


@dataclass
class CallToolResult(SerializableMixin):
    """Result of a tool call"""

    content: List[ContentBlock]
    is_error: bool = False
    structured_content: Optional[Dict[str, Any]] = None
    _meta: Optional[Dict[str, Any]] = None


# =============================================================================
# List Tools Types
# =============================================================================


@dataclass
class ListToolsRequest:
    """Request to list available tools"""

    method: Literal["tools/list"] = "tools/list"
    params: Optional[Dict[str, Any]] = None


@dataclass
class ListToolsResult(SerializableMixin):
    """Result of tools/list request"""

    tools: List[Tool]
    next_cursor: Optional[Cursor] = None
    _meta: Optional[Dict[str, Any]] = None


@dataclass
class PromptArgument:
    """
    Describes an argument that a prompt can accept.

    Per MCP spec: https://modelcontextprotocol.io/specification/2025-06-18/schema#promptargument
    """

    name: str
    description: Optional[str] = None
    required: Optional[bool] = None


@dataclass
class Prompt:
    """
    Prompt template definition.

    Per MCP spec: https://modelcontextprotocol.io/specification/2025-06-18/schema#prompt
    """

    name: str
    description: Optional[str] = None
    arguments: Optional[List[PromptArgument]] = None


@dataclass
class ListPromptsResult(SerializableMixin):
    """
    Result of prompts/list request.

    Per MCP spec: https://modelcontextprotocol.io/specification/2025-06-18/schema#listpromptsresult
    """

    prompts: List[Prompt]
    next_cursor: Optional[Cursor] = None
    _meta: Optional[Dict[str, Any]] = None


@dataclass
class ListResourcesResult(SerializableMixin):
    """
    Result of resources/list request.

    Per MCP spec: https://modelcontextprotocol.io/specification/2025-06-18/schema#listresourcesresult
    """

    resources: List[Resource]
    next_cursor: Optional[Cursor] = None
    _meta: Optional[Dict[str, Any]] = None


# =============================================================================
# Notification Types (per MCP specification)
# =============================================================================


@dataclass
class ProgressNotification(JSONRPCNotification):
    """Progress notification following MCP specification"""

    method: Literal["notifications/progress"] = "notifications/progress"
    params: Dict[str, Any] = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}


@dataclass
class CancelledNotification(JSONRPCNotification):
    """Cancellation notification following MCP specification"""

    method: Literal["notifications/cancelled"] = "notifications/cancelled"
    params: Optional[Dict[str, Any]] = None


@dataclass
class InitializedNotification(JSONRPCNotification):
    """Initialized notification following MCP specification"""

    method: Literal["notifications/initialized"] = "notifications/initialized"
    params: Optional[Dict[str, Any]] = None


@dataclass
class LoggingMessageNotification(JSONRPCNotification):
    """Logging message notification following MCP specification"""

    method: Literal["notifications/message"] = "notifications/message"
    params: Dict[str, Any] = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}


@dataclass
class ToolListChangedNotification(JSONRPCNotification):
    """Tool list changed notification following MCP specification"""

    method: Literal["notifications/tools/list_changed"] = (
        "notifications/tools/list_changed"
    )
    params: Optional[Dict[str, Any]] = None


@dataclass
class ResourceListChangedNotification(JSONRPCNotification):
    """Resource list changed notification following MCP specification"""

    method: Literal["notifications/resources/list_changed"] = (
        "notifications/resources/list_changed"
    )
    params: Optional[Dict[str, Any]] = None


@dataclass
class PromptListChangedNotification(JSONRPCNotification):
    """Prompt list changed notification following MCP specification"""

    method: Literal["notifications/prompts/list_changed"] = (
        "notifications/prompts/list_changed"
    )
    params: Optional[Dict[str, Any]] = None

