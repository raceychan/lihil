"""MCP decorators for marking lihil endpoints as MCP tools and resources."""

from typing import Any, Callable, Dict, Optional, TypeVar
from functools import wraps

from .types import MCPMetadata

F = TypeVar("F", bound=Callable[..., Any])


def mcp_tool(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    **extra: Any
) -> Callable[[F], F]:
    """Decorator to mark a lihil endpoint as an MCP tool.

    Args:
        title: Optional title for the MCP tool
        description: Optional description for the MCP tool
        **extra: Additional metadata for the tool

    Example:
        @app.post("/send-email")
        @mcp_tool(title="Send Email", description="Send an email to a recipient")
        async def send_email(to: str, subject: str, body: str) -> str:
            # Email sending logic
            return f"Email sent to {to}"
    """
    def decorator(func: F) -> F:
        metadata = MCPMetadata(
            type="tool",
            title=title,
            description=description,
            extra=extra
        )
        func._mcp_meta = metadata  # type: ignore
        return func

    return decorator


def mcp_resource(
    uri_template: str,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    mime_type: Optional[str] = None,
    **extra: Any
) -> Callable[[F], F]:
    """Decorator to mark a lihil endpoint as an MCP resource.

    Args:
        uri_template: URI template for the resource (e.g., "users://{user_id}")
        title: Optional title for the MCP resource
        description: Optional description for the MCP resource
        mime_type: Optional MIME type for the resource
        **extra: Additional metadata for the resource

    Example:
        @app.get("/users/{user_id}")
        @mcp_resource("users://{user_id}", title="User Profile", description="Get user profile")
        async def get_user(user_id: int) -> dict:
            return {"id": user_id, "name": "User"}
    """
    def decorator(func: F) -> F:
        metadata = MCPMetadata(
            type="resource",
            title=title,
            description=description,
            uri_template=uri_template,
            extra={"mime_type": mime_type, **extra} if mime_type else extra
        )
        func._mcp_meta = metadata  # type: ignore
        return func

    return decorator


def is_mcp_endpoint(func: Callable[..., Any]) -> bool:
    """Check if a function is marked as an MCP endpoint."""
    return hasattr(func, "_mcp_meta")


def get_mcp_metadata(func: Callable[..., Any]) -> Optional[MCPMetadata]:
    """Get MCP metadata from a function if it exists."""
    return getattr(func, "_mcp_meta", None)
