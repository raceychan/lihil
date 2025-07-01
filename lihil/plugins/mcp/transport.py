"""ASGI transport for MCP integration with lihil."""

from typing import Any, Dict, Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from .server import LihilMCP

try:
    from mcp.server.asgi import ASGIServerTransport
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    ASGIServerTransport = None


class LihilMCPTransport:
    """ASGI transport wrapper for MCP server integration."""

    def __init__(self, mcp_server: "LihilMCP"):
        if not MCP_AVAILABLE:
            raise ImportError(
                "MCP functionality requires the 'mcp' package. "
                "Install it with: pip install 'lihil[mcp]' or pip install mcp"
            )

        self.mcp_server = mcp_server
        self.transport = ASGIServerTransport(mcp_server.mcp_server)
        self.mcp_path_prefix = mcp_server.config.mcp_path_prefix

    async def __call__(
        self,
        scope: Dict[str, Any],
        receive: Callable[[], Awaitable[Dict[str, Any]]],
        send: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """ASGI application for handling both MCP and regular HTTP requests."""

        # Check if this is an MCP request
        if self._is_mcp_request(scope):
            # Handle MCP protocol request
            return await self.transport(scope, receive, send)
        else:
            # Delegate to the main lihil app
            return await self.mcp_server.app(scope, receive, send)

    def _is_mcp_request(self, scope: Dict[str, Any]) -> bool:
        """Determine if this is an MCP protocol request."""
        if scope.get("type") != "http":
            return False

        path = scope.get("path", "")

        # Check if path starts with MCP prefix
        if path.startswith(self.mcp_path_prefix):
            return True

        # Check for MCP-specific headers or content types
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").decode("latin1")

        # MCP uses JSON-RPC 2.0 over HTTP
        return "application/json" in content_type and "jsonrpc" in str(headers)


class MCPMiddleware:
    """Middleware to add MCP capabilities to existing lihil applications."""

    def __init__(self, app: Callable, mcp_transport: LihilMCPTransport):
        self.app = app
        self.mcp_transport = mcp_transport

    async def __call__(
        self,
        scope: Dict[str, Any],
        receive: Callable[[], Awaitable[Dict[str, Any]]],
        send: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Middleware to handle MCP requests alongside regular HTTP requests."""

        # Let the transport decide whether to handle as MCP or delegate to app
        await self.mcp_transport(scope, receive, send)
