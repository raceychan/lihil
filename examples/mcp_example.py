"""
Example demonstrating MCP integration with lihil framework.

This example shows how to:
1. Enable MCP functionality in a lihil application
2. Create MCP tools and resources using decorators
3. Auto-expose endpoints as MCP tools/resources

To run this example:
1. Install MCP dependencies: pip install 'lihil[mcp]'
2. Run the server: python examples/mcp_example.py
3. Access the MCP endpoint at http://localhost:8000/mcp
"""

from lihil import Lihil
from lihil.routing import Route
from lihil.plugins.mcp import MCPConfig

# Create lihil app with MCP enabled
app = Lihil()

# Enable MCP functionality
mcp_config = MCPConfig(
    enabled=True,
    server_name="lihil-demo-server",
    auto_expose=True,  # Automatically expose endpoints as MCP tools/resources
    mcp_path_prefix="/mcp"
)
mcp_server = app.enable_mcp(mcp_config)


# Example 1: MCP Tool - Send Email
email_route = Route("/send-email")
@email_route.post
@app.mcp_tool(title="Send Email", description="Send an email to a recipient")
async def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email to the specified recipient."""
    # Simulate email sending
    return {
        "status": "sent",
        "to": to,
        "subject": subject,
        "message": f"Email sent successfully to {to}"
    }


# Example 2: MCP Resource - User Profile
users_route = Route("/users/{user_id}")
@users_route.get
@app.mcp_resource("users://{user_id}", title="User Profile", description="Get user profile information")
async def get_user(user_id: int) -> dict:
    """Get user profile by ID."""
    return {
        "id": user_id,
        "name": f"User {user_id}",
        "email": f"user{user_id}@example.com",
        "status": "active"
    }


# Example 3: MCP Tool - Calculate Sum
calc_route = Route("/calculate/sum")
@calc_route.post
@app.mcp_tool(title="Calculate Sum", description="Calculate the sum of two numbers")
async def calculate_sum(a: float, b: float) -> dict:
    """Calculate the sum of two numbers."""
    result = a + b
    return {
        "operation": "sum",
        "inputs": [a, b],
        "result": result
    }


# Example 4: Regular endpoint (will be auto-exposed as MCP resource if auto_expose=True)
health_route = Route("/health")
@health_route.get
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy", "service": "lihil-mcp-demo"}


# Example 5: MCP Resource - Configuration
config_route = Route("/config")
@config_route.get
@app.mcp_resource("config://app", title="App Configuration", description="Get application configuration")
async def get_config() -> dict:
    """Get application configuration."""
    return {
        "mcp_enabled": True,
        "server_name": mcp_config.server_name,
        "auto_expose": mcp_config.auto_expose,
        "endpoints": {
            "mcp": "/mcp",
            "health": "/health",
            "users": "/users/{user_id}",
            "send_email": "/send-email",
            "calculate": "/calculate/sum"
        }
    }

# Include all routes in the app
app.include_routes(email_route, users_route, calc_route, health_route, config_route)


if __name__ == "__main__":
    # Print MCP server info
    print(f"MCP Server: {mcp_server.mcp_server.server_name}")
    print(f"MCP Tools: {list(mcp_server.tools.keys())}")
    print(f"MCP Resources: {list(mcp_server.resources.keys())}")

    # Run the server
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
