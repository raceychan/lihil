"""MCP configuration for lihil applications."""

from msgspec import Struct
from typing import Literal


class MCPConfig(Struct):
    """Configuration for MCP integration in lihil applications.

    Attributes:
        enabled: Whether MCP functionality is enabled
        server_name: Name of the MCP server
        expose_docs: Whether to expose OpenAPI docs as MCP resources
        auto_expose: Whether to automatically expose all endpoints as MCP tools/resources
        auth_required: Whether authentication is required for MCP operations
        transport: Transport protocol to use ('asgi' or 'stdio')
        mcp_path_prefix: URL path prefix for MCP endpoints (default: '/mcp')
    """

    enabled: bool = False
    server_name: str = "lihil-mcp-server"
    expose_docs: bool = True
    auto_expose: bool = True
    auth_required: bool = False
    transport: Literal["asgi", "stdio"] = "asgi"
    mcp_path_prefix: str = "/mcp"
