# Lihil AI Copilot Guide

This guide teaches AI agents how to work effectively with the Lihil web framework, based on real experience and common mistakes. Use this as a comprehensive reference when coding with Lihil.

## How to Use This Guide as a Prompt

To ensure your AI coding assistant understands Lihil correctly, copy and paste this entire guide as a system prompt or initial context:

### For Claude Code (Anthropic)
```
Copy this entire LIHIL_COPILOT.md file and paste it at the beginning of your conversation. Claude Code will use it as context for all Lihil-related work.
```

### For Cursor (VS Code Extension)
```
1. Open Cursor settings
2. Go to "Rules for AI"
3. Add a new rule for Python/Lihil projects
4. Paste this guide in the rule content
5. Set it to apply to files with Lihil imports
```

### For ChatGPT / Claude Chat
```
Start your conversation with:
"I'm working with the Lihil web framework. Please read and follow this guide: [paste entire LIHIL_COPILOT.md content]"
```

### For GitHub Copilot
```
1. Create a .github/copilot-instructions.md file in your repo
2. Paste this guide content there
3. Copilot will use it as context for your repository
```

## Critical Differences from FastAPI

**Lihil is NOT FastAPI.** The most important difference:

### INVALID FastAPI Patterns
```python
# These patterns DO NOT work in Lihil:
@app.get("/users")           # INVALID
@app.post("/users/{id}")     # INVALID
@app.put("/api/data")        # INVALID
@app.delete("/items")        # INVALID
```

### CORRECT Lihil Patterns
```python
# Use subroutes for paths:
@app.sub("/users").get       # CORRECT
@app.sub("/users/{id}").post # CORRECT
@app.sub("/api/data").put    # CORRECT
@app.sub("/items").delete    # CORRECT

# Or create routes first:
users_route = Route("/users")
@users_route.get             # CORRECT
@users_route.post            # CORRECT
```

## Core Lihil Patterns

### 1. Route Creation First, Then HTTP Methods

```python
from lihil import Lihil, Route

# Pattern 1: Create route object first
route = Route("/api/users")
@route.get
async def list_users():
    return {"users": []}

@route.post
async def create_user(name: str):
    return {"id": 1, "name": name}

# Pattern 2: Use app subroutes
app = Lihil()

@app.sub("/health").get
async def health_check():
    return {"status": "ok"}

# Pattern 3: Nested subroutes
api = app.sub("/api")
users = api.sub("/users")
@users.get
async def get_users():
    return {"users": []}

user_detail = users.sub("/{user_id}")
@user_detail.get
async def get_user(user_id: str):
    return {"id": user_id}
```

### 2. Path Parameters

```python
# Path parameters are automatically extracted
@app.sub("/users/{user_id}").get
async def get_user(user_id: str):  # user_id extracted from path
    return {"id": user_id}

@app.sub("/posts/{post_id}/comments/{comment_id}").get
async def get_comment(post_id: str, comment_id: str):
    return {"post": post_id, "comment": comment_id}
```

### 3. Request Body & Parameters

```python
from typing import Annotated
from lihil import Param, Form, Payload

# Payload for JSON body
class UserData(Payload):
    name: str
    age: int
    email: str

@app.sub("/users").post
async def create_user(user: UserData):
    return {"created": user}

# Query parameters (automatically detected)
@app.sub("/search").get
async def search(q: str = "", page: int = 1, limit: int = 10):
    return {"query": q, "page": page, "limit": limit}

# Header parameters
@app.sub("/protected").get
async def protected_endpoint(
    auth: Annotated[str, Param("header", alias="Authorization")]
):
    return {"auth": auth}

# Form data
@app.sub("/upload").post
async def upload_file(
    file: Annotated[bytes, Form()],
    filename: Annotated[str, Form()]
):
    return {"uploaded": filename}
```

### 4. Dependency Injection

```python
from lihil import Route

# Dependencies in route constructor
route = Route("/api", deps=[DatabaseService, AuthService])

@route.get
async def get_data(db: DatabaseService, auth: AuthService):
    # db and auth are automatically injected
    return db.get_all()

# Function dependencies
async def get_current_user() -> User:
    return User(id=1, name="test")

@app.sub("/profile").get
async def get_profile(user: User = Depends(get_current_user)):
    return {"user": user}
```

### 5. Including Routes

```python
# Create separate route modules
users_route = Route("/users")
@users_route.get
async def list_users():
    return {"users": []}

posts_route = Route("/posts")
@posts_route.get
async def list_posts():
    return {"posts": []}

# Include in app
app = Lihil()
app.include_routes(users_route, posts_route)

# Or pass routes to constructor
app = Lihil(users_route, posts_route)
```

## Common AI Agent Mistakes & Solutions

### Mistake 1: Using FastAPI Decorator Syntax
```python
# Wrong - AI agents often try this
@app.get("/users")
async def get_users():
    return []

# Correct - Use subroutes
@app.sub("/users").get
async def get_users():
    return []
```

### Mistake 2: Mixing Path in Decorator and Route
```python
# Wrong - Path specified in both places
route = Route("/users")
@route.get("/profile")  # Don't add path here!
async def get_profile():
    return {}

# Correct - Path only in Route
route = Route("/users")
@route.get
async def get_profile():
    return {}

# Or use subroutes for nested paths
users_route = Route("/users")
@users_route.sub("/profile").get
async def get_profile():
    return {}
```

### Mistake 3: Not Understanding Route Structure
```python
# Wrong - Creating new routes unnecessarily
@app.get("/")  # Invalid syntax
async def root():
    return {}

@Route("/users").get("/")  # Confusing path structure
async def users():
    return {}

# Correct - Clear route structure
@app.sub("/").get  # Root endpoint
async def root():
    return {}

users_route = Route("/users")
@users_route.get  # /users endpoint
async def get_users():
    return {}

@users_route.sub("/{user_id}").get  # /users/{user_id} endpoint
async def get_user(user_id: str):
    return {}
```

## Complete Example Template

Here's a complete template AI agents should follow:

```python
from lihil import Lihil, Route, Payload
from typing import Annotated
from lihil import Param

# App setup
app = Lihil()

# Root endpoint
@app.sub("/").get
async def root():
    return {"message": "Welcome to Lihil API"}

# Health check
@app.sub("/health").get
async def health():
    return {"status": "healthy"}

# API routes
api_route = Route("/api/v1")

# Users endpoints
users_route = api_route.sub("/users")

class UserCreate(Payload):
    name: str
    email: str
    age: int

@users_route.get
async def list_users(page: int = 1, limit: int = 10):
    return {"users": [], "page": page, "limit": limit}

@users_route.post
async def create_user(user: UserCreate):
    return {"id": 1, **user.dict()}

# User detail endpoints
user_detail = users_route.sub("/{user_id}")

@user_detail.get
async def get_user(user_id: str):
    return {"id": user_id, "name": "John", "email": "john@example.com"}

@user_detail.put
async def update_user(user_id: str, user: UserCreate):
    return {"id": user_id, **user.dict()}

@user_detail.delete
async def delete_user(user_id: str):
    return {"deleted": user_id}

# Include routes
app.include_routes(api_route)

# Run with: uvicorn main:app --reload
```

## Testing Patterns

```python
from lihil.testing import TestClient

def test_users_endpoint():
    client = TestClient(app)

    # Test GET
    response = client.get("/api/v1/users")
    assert response.status_code == 200

    # Test POST
    user_data = {"name": "John", "email": "john@example.com", "age": 30}
    response = client.post("/api/v1/users", json=user_data)
    assert response.status_code == 200

    # Test path parameters
    response = client.get("/api/v1/users/123")
    assert response.status_code == 200
    assert response.json()["id"] == "123"
```

## Error Handling

```python
from lihil import HTTPException

class UserNotFound(HTTPException[str]):
    """The user you are looking for does not exist"""
    __status__ = 404

@app.sub("/users/{user_id}").get
async def get_user(user_id: str):
    if not user_exists(user_id):
        raise UserNotFound(f"User {user_id} not found")
    return get_user_data(user_id)
```

## Middleware & Plugins

```python
from lihil.middleware import CORSMiddleware

# App-level middleware
app = Lihil(middlewares=[CORSMiddleware])

# Route-level plugins
@app.sub("/protected").get(plugins=[auth_plugin])
async def protected_endpoint():
    return {"message": "Protected"}
```

## AI Agent Checklist

When working with Lihil, AI agents should:

1. **Never use `@app.get("/path")` syntax** - Use `@app.sub("/path").get` instead
2. **Create Route objects first** - Then apply HTTP method decorators
3. **Use Payload for request bodies** - Note that BaseModel, dataclasses,typeddict are supported
4. **Check existing patterns** - Look at how the codebase structures routes
5. **Include routes properly** - Use `app.include_routes()` or pass to constructor
6. **Handle path parameters correctly** - They're extracted automatically
7. **Use proper imports** - `from lihil import Lihil, Route, Payload`
8. **Follow nested route patterns** - Use subroutes for hierarchical APIs
9. **Test endpoints** - Use TestClient for validation
10. **Handle errors with HTTPException** - Follow Lihil's error patterns

## Performance Tips

- Use `msgspec.Struct` for maximum performance instead of Payload when needed
- Leverage dependency injection for database connections and services
- Use streaming responses for large data: `Stream[T]`
- Apply caching plugins for frequently accessed endpoints

## Resources

- **Main Documentation**: https://lihil.cc
- **GitHub Repository**: https://github.com/raceychan/lihil
- **Benchmarks**: https://github.com/raceychan/lhl_bench
- **Full Stack Template**: https://github.com/raceychan/fullstack-solopreneur-template

Remember: When in doubt, check the existing codebase patterns and always prefer the explicit Lihil way over FastAPI assumptions!
