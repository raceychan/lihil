## Notes for Agents

- When tests depend on optional third-party packages, perform imports inside a `try` block at module scope and call `pytest.skip(..., allow_module_level=True)` in the `except ModuleNotFoundError` handler. This skips the entire test module cleanly when the dependency is missing.

  ```python
  # tests/test_optional_feature.py
  import pytest

  pytestmark = pytest.mark.optional_feature

  try:
      from optional_lib import FeatureClient
  except ModuleNotFoundError as exc:
      pytest.skip(f"optional_lib unavailable: {exc}", allow_module_level=True)

  async def test_feature_happy_path():
      client = FeatureClient()
      result = await client.do_work()
      assert result.ok
  ```

# Lihil Project Information

## Available Make Commands

### Development & Running
- `make run` - Run the main application using uvicorn
- `make demo` - Run demo application with reload
- `make fast` - Run fast demo application
- `make example` - Run auth example with reload

### Testing
- `make test` - Run tests with pytest: `uv run python -m pytest -vx --capture=sys tests/`
- `make cov` - Run tests with coverage: `uv run python -m pytest --capture=sys tests/ --cov=lihil --cov-report term-missing`
- `make debug` - Run debug tests: `uv run python -m pytest -m debug tests/`

### Documentation
- `make docs` - Serve documentation with mkdocs: `uv run mkdocs serve`

### Profiling
- `make profile` - Profile main app with pyinstrument
- `make profile_fast` - Profile fast app with pyinstrument
- `make spy` - Monitor with py-spy

### Release Management
- `make release VERSION=x.x.x` - Full release process
- `make build` - Build the package: `uv build`
- `make pypi-release` - Publish to PyPI


## Common Commands
- Run tests: `uv run pytest -vx --capture=sys tests/`
- Run with coverage: `uv run pytest --capture=sys tests/ --cov=lihil --cov-report term-missing`
- Build package: `uv build`
- Serve docs: `uv run mkdocs serve`

## Lihil Framework Usage Patterns

### Core Concepts

**IMPORTANT:** Routes in lihil are created first, then decorated with HTTP methods. The correct pattern is:

```python
route = Route("/path")
@route.post  # NOT @route.post("/path")
async def handler():
    return response
```

### 1. Route Creation

```python
from lihil.routing import Route

# Basic route
route = Route("/users")

# Route with path parameters
route = Route("/users/{user_id}")

# Route with middleware
route = Route("/api", middlewares=[middleware1, middleware2])

# Route with dependencies
route = Route("/service", deps=[ServiceClass])
```

### 2. HTTP Method Decorators

```python
route = Route("/api")

@route.get
async def get_handler():
    return {"method": "GET"}

@route.post
async def post_handler(data: dict):
    return {"method": "POST", "data": data}

@route.put
async def put_handler():
    return {"method": "PUT"}

@route.delete
async def delete_handler():
    return {"method": "DELETE"}
```

### 3. Application Setup

```python
from lihil import Lihil

# Basic app
app = Lihil()

# App with routes
app = Lihil(users_route, posts_route)

# App with middleware
app = Lihil(middlewares=[middleware1, middleware2])
```

### 4. Route Registration Patterns

```python
# Method 1: Direct app methods
@app.get
async def root():
    return {"message": "root"}

# Method 2: Subroutes
users_route = app.sub("users")
@users_route.get
async def get_users():
    return {"users": []}

# Method 3: Including separate routes
separate_route = Route("/posts")
@separate_route.get
async def get_posts():
    return {"posts": []}

app.include(separate_route)

# Method 4: Nested subroutes
api_route = Route("/api")
users_route = api_route.sub("users")
user_detail = users_route.sub("{user_id}")
```

### 5. Parameter Handling

```python
from typing import Annotated
from lihil import Param, Form, Payload

# Path parameters (auto-detected)
async def get_user(user_id: str):
    return {"id": user_id}

# Query parameters
async def search(q: str = "", page: int = 1):
    return {"query": q, "page": page}

# Header parameters
async def with_header(
    user_agent: Annotated[str, Param("header", alias="User-Agent")]
):
    return {"user_agent": user_agent}

# Body parameters
class UserData(Payload):
    name: str
    age: int

async def create_user(user: UserData):
    return {"created": user}
```

### 6. Complete Example

```python
from lihil import Lihil
from lihil.routing import Route

# Create app
app = Lihil()

# Root endpoint
@app.get
async def root():
    return {"message": "API"}

# API routes
api_route = Route("/api/v1")
users_route = api_route.sub("users")

@users_route.get
async def list_users():
    return {"users": []}

@users_route.post
async def create_user(name: str, age: int):
    return {"id": 1, "name": name, "age": age}

# User detail route
user_route = users_route.sub("{user_id}")

@user_route.get
async def get_user(user_id: str):
    return {"id": user_id}

# Include routes
app.include(api_route)
```

### Common Mistakes to Avoid

1. **Wrong:** `@route.post("/path")`
   **Correct:** `route = Route("/path")` then `@route.post`

2. **Wrong:** Creating routes inside decorators
   **Correct:** Create Route object first, then apply decorators

3. **Wrong:** Mixing route paths in decorators and Route constructor
   **Correct:** Path only in Route constructor, decorators specify HTTP method only

4. **CRITICAL:** `@app.get("/path")` is INVALID syntax in lihil
   **Correct:** Use `@app.sub("/path").get` instead

   **Examples:**
   ```python
   # WRONG - This will NOT work
   @app.get("/users")
   async def get_users():
       return {"users": []}

   # CORRECT - Use subroutes
   @app.sub("/users").get
   async def get_users():
       return {"users": []}

   # OR create a route first
   users_route = app.sub("/users")
   @users_route.get
   async def get_users():
       return {"users": []}
   ```

   This applies to ALL HTTP methods: `.get()`, `.post()`, `.put()`, `.delete()`, etc.
