"""
MCP (Model Context Protocol) plugin for lihil framework.

This plugin enables lihil applications to expose their endpoints as MCP tools and resources,
allowing them to be used by MCP-compatible clients like Claude Code.
"""

try:
    from .config import MCPConfig
    from .server import LihilMCP
    from .decorators import mcp_tool, mcp_resource

    __all__ = ["MCPConfig", "LihilMCP", "mcp_tool", "mcp_resource"]
except ImportError as e:
    # MCP dependencies not installed
    def _mcp_not_available(*args, **kwargs):
        raise ImportError(
            "MCP functionality requires the 'mcp' package. "
            "Install it with: pip install 'lihil[mcp]' or pip install mcp"
        ) from e

    MCPConfig = _mcp_not_available
    LihilMCP = _mcp_not_available
    mcp_tool = _mcp_not_available
    mcp_resource = _mcp_not_available

    __all__ = ["MCPConfig", "LihilMCP", "mcp_tool", "mcp_resource"]
