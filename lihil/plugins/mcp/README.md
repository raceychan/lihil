# MCP Plugin for Lihil

This plugin enables Model Context Protocol (MCP) functionality in lihil applications, allowing them to expose endpoints as MCP tools and resources for use with MCP-compatible clients like Claude Code.

## Installation

Install with MCP support:

```bash
pip install 'lihil[mcp]'
```

Or install the MCP package separately:

```bash
pip install lihil mcp
```

## Quick Start

### Basic Usage

```python
from lihil import Lihil
from lihil.routing import Route
from lihil.plugins.mcp import MCPConfig

# Create app and enable MCP
app = Lihil()
mcp = app.enable_mcp(MCPConfig(enabled=True))

# Create an MCP tool
email_route = Route("/send-email")
@email_route.post
@app.mcp_tool(title="Send Email")
async def send_email(to: str, subject: str, body: str) -> str:
    return f"Email sent to {to}"

# Create an MCP resource
users_route = Route("/users/{user_id}")
@users_route.get
@app.mcp_resource("users://{user_id}", title="User Profile")
async def get_user(user_id: int) -> dict:
    return {"id": user_id, "name": f"User {user_id}"}

app.include_routes(email_route, users_route)
```

### Configuration Options

```python
from lihil.plugins.mcp import MCPConfig

config = MCPConfig(
    enabled=True,                    # Enable MCP functionality
    server_name="my-lihil-server",   # MCP server name
    auto_expose=True,                # Auto-expose all endpoints
    auth_required=False,             # Require authentication
    mcp_path_prefix="/mcp",          # URL prefix for MCP endpoints
    transport="asgi"                 # Transport protocol
)

app.enable_mcp(config)
```

## Features

### 🛠️ **MCP Tools**
Expose POST/PUT/PATCH endpoints as executable MCP tools:

```python
calc_route = Route("/calculate")
@calc_route.post
@app.mcp_tool(title="Calculator", description="Perform calculations")
async def calculate(operation: str, x: float, y: float) -> float:
    if operation == "add":
        return x + y
    elif operation == "multiply":
        return x * y
    # ... more operations

app.include_routes(calc_route)
```

### 📄 **MCP Resources**
Expose GET endpoints as readable MCP resources:

```python
docs_route = Route("/docs/{doc_id}")
@docs_route.get
@app.mcp_resource("docs://{doc_id}", title="Document", mime_type="text/plain")
async def get_document(doc_id: str) -> str:
    return f"Content of document {doc_id}"

app.include_routes(docs_route)
```

### 🔄 **Auto-Exposure**
Automatically expose all endpoints when `auto_expose=True`:
- GET endpoints → MCP Resources
- POST/PUT/PATCH endpoints → MCP Tools

### 🔐 **Authentication**
Leverage lihil's existing auth system for MCP operations:

```python
config = MCPConfig(enabled=True, auth_required=True)
# Uses lihil's JWT/OAuth plugins automatically
```

## Implementation Status

### ✅ **Completed Features**
- Basic MCP plugin structure
- Configuration system (`MCPConfig`)
- MCP decorators (`@mcp_tool`, `@mcp_resource`)
- Integration with main Lihil class
- ASGI transport wrapper
- Auto-exposure of endpoints
- Type safety and schema generation

### 🚧 **In Progress**
- Full MCP protocol implementation
- Route-to-MCP conversion logic
- Authentication integration
- Error handling and logging

### 📋 **Planned Features**
- Streaming responses
- Context integration
- OpenAPI schema as MCP resources
- Multiple transport support (stdio, WebSocket)
- Performance optimization
- Comprehensive testing

## Architecture

```
lihil/plugins/mcp/
├── __init__.py          # Main exports
├── config.py            # Configuration classes
├── decorators.py        # @mcp_tool, @mcp_resource
├── server.py            # LihilMCP main server
├── transport.py         # ASGI transport layer
├── types.py             # MCP-specific types
└── README.md            # This file
```

## Examples

See `examples/mcp_example.py` for a complete working example.

## Protocol Compliance

This implementation aims for full compatibility with the MCP specification:
- JSON-RPC 2.0 over HTTP/ASGI
- Standard MCP tools and resources
- Proper error handling and responses
- Compatible with MCP clients like Claude Code

## Contributing

When contributing to the MCP plugin:

1. Follow lihil's coding conventions
2. Maintain type safety
3. Add tests for new features
4. Update documentation
5. Ensure MCP protocol compliance

## Dependencies

- `mcp>=1.8.1` - Official Python MCP SDK
- Existing lihil framework components
- Optional: Authentication plugins for secured MCP operations
