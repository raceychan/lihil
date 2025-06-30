# MCP Integration Plan for Lihil

## Overview

This document outlines the plan for integrating Model Context Protocol (MCP) functionality into the lihil framework. The integration will allow lihil applications to expose their endpoints as MCP tools and resources, similar to how fastapi_mcp works but tailored to lihil's architecture.

## Goals

1. **Minimal Configuration**: Expose lihil endpoints as MCP tools with zero or minimal configuration
2. **Native Integration**: Build on lihil's existing architecture (routing, dependency injection, middleware)
3. **Preserve Functionality**: Keep all existing lihil features intact while adding MCP capabilities
4. **Authentication Support**: Leverage lihil's auth plugins for MCP authentication
5. **Type Safety**: Maintain lihil's strong typing and schema generation

## Architecture Analysis

### Lihil Framework Structure
- **Main App Class**: `Lihil` (lihil/lihil.py:92)
- **Routing System**: `Route` and `RouteBase` classes (lihil/routing.py)
- **ASGI Interface**: `ASGIBase` with middleware support
- **Dependency Injection**: `Graph` system using ididi library
- **Configuration**: `AppConfig` with structured configuration
- **Plugin System**: Extensible plugin architecture (lihil/plugins/)

### MCP SDK Structure
- **Core Components**: Tools, Resources, Prompts
- **Server API**: FastMCP-style server creation
- **Transport**: ASGI-compatible transport layer
- **Dependencies**: Only requires `mcp` package

## Proposed Implementation Plan

### Phase 1: Core MCP Extension

#### 1.1 Create MCP Plugin Structure
```
lihil/plugins/mcp/
├── __init__.py
├── server.py       # Main MCP server implementation
├── decorators.py   # MCP-specific decorators
├── transport.py    # ASGI transport for MCP
├── config.py       # MCP configuration
└── types.py        # MCP-specific types
```

#### 1.2 Core Classes Design

**LihilMCP Class** (lihil/plugins/mcp/server.py)
- Integrate with existing `Lihil` app instance
- Wrap lihil routes as MCP tools/resources
- Handle MCP protocol communication
- Support both embedded and standalone modes

**MCPRoute Class** (lihil/plugins/mcp/server.py)
- Extend `RouteBase` to support MCP metadata
- Automatic tool/resource generation from endpoint signatures
- Preserve lihil's parameter parsing and validation

#### 1.3 Configuration Integration
```python
# lihil/plugins/mcp/config.py
from lihil.config import IAppConfig
from msgspec import Struct

class MCPConfig(Struct):
    enabled: bool = False
    server_name: str = "lihil-mcp-server"
    expose_docs: bool = True
    auto_expose: bool = True
    auth_required: bool = False
    transport: str = "asgi"  # or "stdio"
```

### Phase 2: Integration with Lihil Core

#### 2.1 Lihil Class Extensions
Extend the main `Lihil` class to support MCP:

```python
# Addition to lihil/lihil.py
from lihil.plugins.mcp import LihilMCP, MCPConfig

class Lihil(ASGIBase):
    def __init__(self, ..., mcp_config: MCPConfig | None = None):
        # ... existing initialization
        self._mcp_server: LihilMCP | None = None
        if mcp_config and mcp_config.enabled:
            self._mcp_server = LihilMCP(self, mcp_config)

    def enable_mcp(self, config: MCPConfig | None = None) -> LihilMCP:
        """Enable MCP functionality for this app"""
        config = config or MCPConfig(enabled=True)
        self._mcp_server = LihilMCP(self, config)
        return self._mcp_server
```

#### 2.2 Route Enhancement
Enhance existing routes to support MCP metadata:

```python
# Addition to lihil/routing.py
class Route(RouteBase):
    def mcp_tool(self, **kwargs):
        """Mark endpoint as MCP tool"""
        def decorator(func):
            func._mcp_meta = {"type": "tool", **kwargs}
            return self.post(func)  # or appropriate method
        return decorator

    def mcp_resource(self, uri_template: str, **kwargs):
        """Mark endpoint as MCP resource"""
        def decorator(func):
            func._mcp_meta = {"type": "resource", "uri": uri_template, **kwargs}
            return self.get(func)
        return decorator
```

### Phase 3: MCP Server Implementation

#### 3.1 MCP Protocol Handler
```python
# lihil/plugins/mcp/server.py
from mcp.server.fastmcp import FastMCP
from mcp import Context

class LihilMCP:
    def __init__(self, app: Lihil, config: MCPConfig):
        self.app = app
        self.config = config
        self.mcp_server = FastMCP(config.server_name)
        self._setup_mcp_tools()

    def _setup_mcp_tools(self):
        """Convert lihil routes to MCP tools/resources"""
        for route in self.app.routes:
            if hasattr(route, 'endpoints'):
                for endpoint in route.endpoints:
                    self._register_endpoint(route, endpoint)

    def _register_endpoint(self, route: Route, endpoint):
        """Register a lihil endpoint as MCP tool or resource"""
        func = endpoint.func
        mcp_meta = getattr(func, '_mcp_meta', None)

        if mcp_meta and mcp_meta['type'] == 'tool':
            self._register_as_tool(route, endpoint, mcp_meta)
        elif mcp_meta and mcp_meta['type'] == 'resource':
            self._register_as_resource(route, endpoint, mcp_meta)
        elif self.config.auto_expose:
            self._auto_register_endpoint(route, endpoint)
```

#### 3.2 ASGI Transport Integration
```python
# lihil/plugins/mcp/transport.py
from mcp.server.asgi import ASGIServerTransport

class LihilMCPTransport:
    def __init__(self, mcp_server: LihilMCP):
        self.mcp_server = mcp_server
        self.transport = ASGIServerTransport(mcp_server.mcp_server)

    async def __call__(self, scope, receive, send):
        """ASGI application for MCP protocol"""
        if scope.get('path', '').startswith('/mcp'):
            return await self.transport(scope, receive, send)
        else:
            # Fallback to main app
            return await self.mcp_server.app(scope, receive, send)
```

### Phase 4: Authentication Integration

#### 4.1 Leverage Lihil Auth Plugins
```python
# Integration with lihil/plugins/auth/
class LihilMCP:
    def _setup_auth(self):
        """Use lihil's existing auth system for MCP"""
        if self.config.auth_required:
            # Integrate with lihil's JWT/OAuth plugins
            from lihil.plugins.auth import get_current_user

            @self.mcp_server.middleware
            async def mcp_auth_middleware(request, call_next):
                # Use lihil's auth system
                user = await get_current_user(request)
                if not user:
                    raise UnauthorizedError()
                return await call_next(request)
```

### Phase 5: Advanced Features

#### 5.1 Dynamic Resource Generation
- Expose OpenAPI schema as MCP resources
- Dynamic tool generation from endpoint signatures
- Support for streaming responses

#### 5.2 Context Integration
- Integration with lihil's dependency injection system
- Context passing between MCP and lihil endpoints
- Progress reporting for long-running operations

## Implementation Steps

### Step 1: Basic Structure (Week 1)
1. Create plugin directory structure
2. Implement basic `MCPConfig` class
3. Create skeleton `LihilMCP` class
4. Add MCP dependency to pyproject.toml

### Step 2: Core Integration (Week 2)
1. Implement MCP decorators (`@mcp_tool`, `@mcp_resource`)
2. Create basic route-to-MCP conversion logic
3. Implement ASGI transport wrapper
4. Basic testing framework

### Step 3: Advanced Features (Week 3)
1. Authentication integration
2. Auto-exposure of existing endpoints
3. OpenAPI schema integration
4. Error handling and logging

### Step 4: Documentation and Examples (Week 4)
1. Create usage examples
2. Write comprehensive documentation
3. Create migration guide from fastapi_mcp
4. Performance testing and optimization

## Usage Examples

### Basic Usage
```python
from lihil import Lihil
from lihil.plugins.mcp import MCPConfig

app = Lihil()
mcp_config = MCPConfig(enabled=True, server_name="my-api")
mcp = app.enable_mcp(mcp_config)

@app.get("/users/{user_id}")
@app.mcp_resource("users://{user_id}", title="User Profile")
async def get_user(user_id: int) -> dict:
    return {"id": user_id, "name": "User"}

@app.post("/send-email")
@app.mcp_tool(title="Send Email")
async def send_email(to: str, subject: str, body: str) -> str:
    # Email sending logic
    return f"Email sent to {to}"
```

### Auto-Exposure Mode
```python
app = Lihil()
# Automatically expose all GET endpoints as resources
# and POST endpoints as tools
mcp = app.enable_mcp(MCPConfig(enabled=True, auto_expose=True))
```

## Testing Strategy

1. **Unit Tests**: Test individual components (decorators, config, etc.)
2. **Integration Tests**: Test MCP server integration with lihil apps
3. **Protocol Tests**: Verify MCP protocol compliance
4. **Performance Tests**: Ensure minimal overhead
5. **Compatibility Tests**: Test with different MCP clients

## Dependencies

### Required
- `mcp>=1.8.1` - Official Python MCP SDK

### Optional
- Authentication plugins (existing lihil auth system)
- Additional transport layers if needed

## Migration from FastAPI-MCP

For users coming from fastapi_mcp, provide:
1. Migration guide
2. Compatibility layer (if needed)
3. Feature comparison matrix
4. Example conversions

## Risks and Mitigations

### Risks
1. **Performance Impact**: Adding MCP layer might slow down regular HTTP requests
2. **Complexity**: Additional configuration surface area
3. **Maintenance**: Keeping up with MCP protocol changes

### Mitigations
1. **Lazy Loading**: Only initialize MCP when explicitly enabled
2. **Optional**: Keep MCP functionality completely optional
3. **Clean Architecture**: Isolate MCP code in plugin system
4. **Documentation**: Comprehensive docs and examples

## Future Enhancements

1. **Multi-Transport Support**: Support for stdio, WebSocket transports
2. **Advanced Routing**: MCP-specific routing capabilities
3. **Monitoring**: Built-in metrics and monitoring for MCP usage
4. **Template System**: Prompt templates and reusable patterns
5. **Client SDK**: Built-in MCP client for inter-service communication

## Conclusion

This plan provides a comprehensive approach to integrating MCP functionality into lihil while maintaining the framework's core principles of simplicity, performance, and developer experience. The plugin-based approach ensures that MCP functionality doesn't affect users who don't need it, while providing powerful capabilities for those who do.
