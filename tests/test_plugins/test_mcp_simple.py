"""
Simplified tests for the MCP (Model Context Protocol) plugin.

This focuses on testing the core functionality that actually exists.
"""

import pytest
from unittest.mock import Mock, patch

from lihil import Lihil
from lihil.routing import Route
from lihil.local_client import LocalClient


class TestMCPDecorators:
    """Test MCP decorators functionality."""

    def test_mcp_tool_decorator(self):
        """Test @mcp_tool decorator functionality."""
        from lihil.plugins.mcp.decorators import mcp_tool, get_mcp_metadata

        @mcp_tool(title="Test Tool", description="A test tool")
        async def test_function():
            return "test"

        metadata = get_mcp_metadata(test_function)
        assert metadata is not None
        assert metadata.type == "tool"
        assert metadata.title == "Test Tool"
        assert metadata.description == "A test tool"

    def test_mcp_resource_decorator(self):
        """Test @mcp_resource decorator functionality."""
        from lihil.plugins.mcp.decorators import mcp_resource, get_mcp_metadata

        @mcp_resource("test://resource", title="Test Resource")
        async def test_function():
            return {"data": "test"}

        metadata = get_mcp_metadata(test_function)
        assert metadata is not None
        assert metadata.type == "resource"
        assert metadata.title == "Test Resource"
        assert metadata.uri_template == "test://resource"

    def test_is_mcp_endpoint(self):
        """Test is_mcp_endpoint function."""
        from lihil.plugins.mcp.decorators import mcp_tool, is_mcp_endpoint

        @mcp_tool(title="Test")
        async def mcp_function():
            return "test"

        async def regular_function():
            return "test"

        assert is_mcp_endpoint(mcp_function) is True
        assert is_mcp_endpoint(regular_function) is False


class TestMCPTypes:
    """Test MCP type classes."""

    def test_mcp_tool_info_creation(self):
        """Test MCPToolInfo creation."""
        from lihil.plugins.mcp.types import MCPToolInfo

        tool_info = MCPToolInfo(
            name="test_tool",
            description="A test tool",
            inputSchema={"type": "object", "properties": {}}
        )

        assert tool_info.name == "test_tool"
        assert tool_info.description == "A test tool"
        assert tool_info.inputSchema == {"type": "object", "properties": {}}

    def test_mcp_resource_info_creation(self):
        """Test MCPResourceInfo creation."""
        from lihil.plugins.mcp.types import MCPResourceInfo

        resource_info = MCPResourceInfo(
            uri="test://resource",
            name="Test Resource",
            description="A test resource",
            mimeType="application/json"
        )

        assert resource_info.uri == "test://resource"
        assert resource_info.name == "Test Resource"
        assert resource_info.description == "A test resource"
        assert resource_info.mimeType == "application/json"

    def test_mcp_error(self):
        """Test MCPError exception."""
        from lihil.plugins.mcp.types import MCPError

        error = MCPError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_mcp_registration_error(self):
        """Test MCPRegistrationError exception."""
        from lihil.plugins.mcp.types import MCPRegistrationError

        error = MCPRegistrationError("Registration failed")
        assert str(error) == "Registration failed"
        assert isinstance(error, Exception)


class TestLihilMCPServer:
    """Test LihilMCP server class."""

    @patch('lihil.plugins.mcp.server.MCP_AVAILABLE', True)
    @patch('lihil.plugins.mcp.server.FastMCP')
    def test_lihil_mcp_creation(self, mock_fastmcp):
        """Test LihilMCP server creation."""
        from lihil.plugins.mcp.server import LihilMCP
        from lihil.plugins.mcp.config import MCPConfig

        app = Lihil()
        config = MCPConfig(enabled=True, server_name="test-server")

        mock_fastmcp_instance = Mock()
        mock_fastmcp.return_value = mock_fastmcp_instance

        mcp_server = LihilMCP(app, config)

        assert mcp_server.app == app
        assert mcp_server.config == config
        assert mcp_server.mcp_server == mock_fastmcp_instance
        mock_fastmcp.assert_called_once_with("test-server")

    def test_lihil_mcp_import_error(self):
        """Test LihilMCP raises ImportError when MCP not available."""
        from lihil.plugins.mcp.config import MCPConfig

        with patch('lihil.plugins.mcp.server.MCP_AVAILABLE', False):
            from lihil.plugins.mcp.server import LihilMCP

            app = Lihil()
            config = MCPConfig()

            with pytest.raises(ImportError, match="MCP functionality requires"):
                LihilMCP(app, config)

    @patch('lihil.plugins.mcp.server.MCP_AVAILABLE', True)
    @patch('lihil.plugins.mcp.server.FastMCP')
    def test_generate_input_schema(self, mock_fastmcp):
        """Test input schema generation for function parameters."""
        from lihil.plugins.mcp.server import LihilMCP
        from lihil.plugins.mcp.config import MCPConfig

        app = Lihil()
        config = MCPConfig()
        mcp_server = LihilMCP(app, config)

        async def test_function(name: str, age: int, active: bool = True):
            return {"name": name, "age": age, "active": active}

        schema = mcp_server._generate_input_schema(test_function)

        expected_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "active": {"type": "boolean"}
            },
            "required": ["name", "age"]
        }

        assert schema == expected_schema


class TestMCPIntegration:
    """Integration tests for MCP with actual lihil routes."""

    async def test_mcp_decorated_endpoint_works_normally(self):
        """Test that MCP-decorated endpoints work as normal lihil endpoints."""
        from lihil.plugins.mcp.decorators import mcp_tool, mcp_resource

        # Create app with MCP-decorated routes
        app = Lihil()

        # Tool endpoint
        calc_route = Route("/calculate")

        @calc_route.post
        @mcp_tool(title="Calculator", description="Perform calculations")
        async def calculate(x: float, y: float, operation: str = "add") -> dict:
            if operation == "add":
                result = x + y
            elif operation == "multiply":
                result = x * y
            else:
                result = 0
            return {"result": result, "operation": operation}

        # Resource endpoint
        users_route = Route("/users/{user_id}")

        @users_route.get
        @mcp_resource("users://{user_id}", title="User Profile")
        async def get_user(user_id: int) -> dict:
            return {
                "id": user_id,
                "name": f"User {user_id}",
                "email": f"user{user_id}@example.com"
            }

        app.include_routes(calc_route, users_route)

        # Test with LocalClient - these should work as normal lihil endpoints
        client = LocalClient()

        # Test tool endpoint
        calc_response = await client.call_app(app, "POST", "/calculate",
                                               query_params={"x": 5, "y": 3, "operation": "add"})
        assert calc_response.status_code == 200
        calc_data = await calc_response.json()
        assert calc_data["result"] == 8
        assert calc_data["operation"] == "add"

        # Test resource endpoint
        user_response = await client.call_app(app, "GET", "/users/123")
        assert user_response.status_code == 200
        user_data = await user_response.json()
        assert user_data["id"] == 123
        assert user_data["name"] == "User 123"
        assert user_data["email"] == "user123@example.com"

    async def test_mixed_mcp_and_regular_endpoints(self):
        """Test app with both MCP-decorated and regular endpoints."""
        from lihil.plugins.mcp.decorators import mcp_tool

        app = Lihil()

        # MCP-decorated endpoint
        api_route = Route("/api/send-email")

        @api_route.post
        @mcp_tool(title="Send Email", description="Send email to recipient")
        async def send_email(to: str, subject: str, body: str) -> dict:
            return {
                "status": "sent",
                "to": to,
                "subject": subject,
                "message": f"Email sent to {to}"
            }

        # Regular endpoint (no MCP decoration)
        health_route = Route("/health")

        @health_route.get
        async def health_check() -> dict:
            return {"status": "healthy"}

        app.include_routes(api_route, health_route)

        # Test both endpoints work normally
        client = LocalClient()

        # Test MCP endpoint
        email_response = await client.call_app(app, "POST", "/api/send-email", query_params={
            "to": "test@example.com",
            "subject": "Test",
            "body": "Test message"
        })
        assert email_response.status_code == 200
        email_data = await email_response.json()
        assert email_data["status"] == "sent"
        assert email_data["to"] == "test@example.com"

        # Test regular endpoint
        health_response = await client.call_app(app, "GET", "/health")
        assert health_response.status_code == 200
        health_data = await health_response.json()
        assert health_data["status"] == "healthy"

    async def test_app_works_without_mcp(self):
        """Test that lihil apps work normally without any MCP functionality."""
        app = Lihil()
        test_route = Route("/test")

        @test_route.get
        async def test_endpoint() -> dict:
            return {"message": "works without MCP"}

        app.include_routes(test_route)

        client = LocalClient()
        response = await client.call_app(app, "GET", "/test")

        assert response.status_code == 200
        data = await response.json()
        assert data["message"] == "works without MCP"
