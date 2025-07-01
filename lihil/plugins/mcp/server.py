"""Main MCP server implementation for lihil."""

import inspect
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .config import MCPConfig
from .types import MCPError, MCPRegistrationError, MCPToolInfo, MCPResourceInfo
from .decorators import get_mcp_metadata, is_mcp_endpoint

if TYPE_CHECKING:
    from lihil.lihil import Lihil
    from lihil.routing import Route

try:
    from mcp.server.fastmcp import FastMCP
    from mcp import Context
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    FastMCP = None
    Context = None


class LihilMCP:
    """MCP server integration for lihil applications."""

    def __init__(self, app: "Lihil", config: MCPConfig):
        if not MCP_AVAILABLE:
            raise ImportError(
                "MCP functionality requires the 'mcp' package. "
                "Install it with: pip install 'lihil[mcp]' or pip install mcp"
            )

        self.app = app
        self.config = config
        self.mcp_server = FastMCP(config.server_name)
        self._tools: Dict[str, MCPToolInfo] = {}
        self._resources: Dict[str, MCPResourceInfo] = {}

        # Setup MCP tools and resources
        self._setup_mcp_endpoints()

    def _setup_mcp_endpoints(self) -> None:
        """Convert lihil routes to MCP tools and resources."""
        if not hasattr(self.app, 'routes'):
            return

        for route in self.app.routes:
            if hasattr(route, 'endpoints'):
                for endpoint in route.endpoints:
                    try:
                        self._register_endpoint(route, endpoint)
                    except Exception as e:
                        raise MCPRegistrationError(
                            f"Failed to register endpoint {endpoint.func.__name__}: {e}"
                        ) from e

    def _register_endpoint(self, route: "Route", endpoint: Any) -> None:
        """Register a lihil endpoint as MCP tool or resource."""
        func = endpoint.func
        mcp_meta = get_mcp_metadata(func)

        if mcp_meta:
            if mcp_meta.type == "tool":
                self._register_as_tool(route, endpoint, mcp_meta)
            elif mcp_meta.type == "resource":
                self._register_as_resource(route, endpoint, mcp_meta)
        elif self.config.auto_expose:
            self._auto_register_endpoint(route, endpoint)

    def _register_as_tool(self, route: "Route", endpoint: Any, mcp_meta: Any) -> None:
        """Register an endpoint as an MCP tool."""
        func = endpoint.func
        func_name = func.__name__

        # Create tool info
        tool_info = MCPToolInfo(
            name=func_name,
            description=mcp_meta.description or func.__doc__ or f"Tool: {func_name}",
            inputSchema=self._generate_input_schema(func)
        )

        self._tools[func_name] = tool_info

        # Register with FastMCP
        @self.mcp_server.tool(name=func_name, description=tool_info.description)
        async def mcp_tool_wrapper(*args, **kwargs):
            # TODO: Implement actual endpoint calling logic
            # This is a placeholder - we need to integrate with lihil's routing system
            return f"Tool {func_name} called with args: {args}, kwargs: {kwargs}"

    def _register_as_resource(self, route: "Route", endpoint: Any, mcp_meta: Any) -> None:
        """Register an endpoint as an MCP resource."""
        func = endpoint.func
        func_name = func.__name__

        # Create resource info
        resource_info = MCPResourceInfo(
            uri=mcp_meta.uri_template or f"lihil://{func_name}",
            name=mcp_meta.title or func_name,
            description=mcp_meta.description or func.__doc__ or f"Resource: {func_name}",
            mimeType=mcp_meta.extra.get("mime_type", "application/json")
        )

        self._resources[resource_info.uri] = resource_info

        # Register with FastMCP
        @self.mcp_server.resource(uri=resource_info.uri)
        async def mcp_resource_wrapper():
            # TODO: Implement actual endpoint calling logic
            # This is a placeholder - we need to integrate with lihil's routing system
            return f"Resource {func_name} accessed"

    def _auto_register_endpoint(self, route: "Route", endpoint: Any) -> None:
        """Automatically register an endpoint based on HTTP method."""
        # TODO: Implement auto-registration logic
        # POST/PUT/PATCH -> tools
        # GET -> resources
        pass

    def _generate_input_schema(self, func) -> Optional[Dict[str, Any]]:
        """Generate JSON schema for function parameters."""
        try:
            sig = inspect.signature(func)
            properties = {}
            required = []

            for param_name, param in sig.parameters.items():
                if param_name in ('self', 'cls'):
                    continue

                param_type = param.annotation
                if param_type == inspect.Parameter.empty:
                    param_type = str

                # Basic type mapping - this should be enhanced
                type_map = {
                    str: {"type": "string"},
                    int: {"type": "integer"},
                    float: {"type": "number"},
                    bool: {"type": "boolean"},
                    list: {"type": "array"},
                    dict: {"type": "object"}
                }

                properties[param_name] = type_map.get(param_type, {"type": "string"})

                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            return {
                "type": "object",
                "properties": properties,
                "required": required
            } if properties else None

        except Exception:
            return None

    @property
    def tools(self) -> Dict[str, MCPToolInfo]:
        """Get registered MCP tools."""
        return self._tools.copy()

    @property
    def resources(self) -> Dict[str, MCPResourceInfo]:
        """Get registered MCP resources."""
        return self._resources.copy()

    async def handle_mcp_request(self, scope: Dict[str, Any], receive, send) -> None:
        """Handle MCP protocol requests."""
        # TODO: Implement MCP request handling
        # This will be implemented in the transport layer
        pass
