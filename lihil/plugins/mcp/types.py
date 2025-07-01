"""MCP-specific types and data structures."""

from typing import Any, Dict, Optional, Union, Literal
from msgspec import Struct


class MCPMetadata(Struct):
    """Metadata for MCP tool/resource registration."""

    type: Literal["tool", "resource"]
    title: Optional[str] = None
    description: Optional[str] = None
    uri_template: Optional[str] = None  # For resources
    extra: Dict[str, Any] = {}


class MCPToolInfo(Struct):
    """Information about an MCP tool."""

    name: str
    description: Optional[str] = None
    inputSchema: Optional[Dict[str, Any]] = None


class MCPResourceInfo(Struct):
    """Information about an MCP resource."""

    uri: str
    name: Optional[str] = None
    description: Optional[str] = None
    mimeType: Optional[str] = None


class MCPError(Exception):
    """Base exception for MCP-related errors."""
    pass


class MCPConfigurationError(MCPError):
    """Raised when MCP configuration is invalid."""
    pass


class MCPRegistrationError(MCPError):
    """Raised when there's an error registering an endpoint as MCP tool/resource."""
    pass
