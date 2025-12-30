![Lihil](assets/lhl_logo_ts.png)

# Lihil

**Lihil** &nbsp;_/ˈliːhaɪl/_ — a **performant**, **productive**, and **professional** web framework with a vision:

> **Making Python the mainstream programming language for web development.**

**lihil is _100%_ test covered and _strictly_ typed.**

[![codecov](https://codecov.io/gh/raceychan/lihil/graph/badge.svg?token=KOK5S1IGVX)](https://codecov.io/gh/raceychan/lihil)
[![PyPI version](https://badge.fury.io/py/lihil.svg)](https://badge.fury.io/py/lihil)
[![License](https://img.shields.io/github/license/raceychan/lihil)](https://github.com/raceychan/lihil/blob/master/LICENSE)
[![Python Version](https://img.shields.io/pypi/pyversions/lihil.svg)](https://pypi.org/project/lihil/)

# Lihil

## 📚 Docs: https://lihil.cc

## Lihil is

- **Performant**: Blazing fast across tasks and conditions—Lihil ranks among the fastest Python web frameworks, outperforming other webframeworks by 50%–100%, see reproducible, automated tests [lihil benchmarks](https://github.com/raceychan/lhl_bench), [independent benchmarks](https://web-frameworks-benchmark.netlify.app/result?l=python)

![bench](/assets/bench_ping.png)

- **Designed to be tested**: Built with testability in mind, making it easy for users to write unit, integration, and e2e tests. Lihil supports Starlette's TestClient and provides LocalClient that allows testing at different levels: endpoint, route, middleware, and application.
- **Built for large scale applications**: Architected to handle enterprise-level applications with robust dependency injection and modular design
- **AI Agent Friendly**: Designed to work seamlessly with AI coding assistants - see [LIHIL_COPILOT.md](LIHIL_COPILOT.md) for comprehensive guidance on using Lihil with AI agents
- **Productive**: Provides extensive typing information for superior developer experience, complemented by detailed error messages and docstrings for effortless debugging

## What’s New: Managed WebSocket Hub
- **SocketHub**: High-level WebSocket route with class-based channels. Subclass `ChannelBase`, declare `topic = Topic("room:{room_id}")`, and implement `on_join`, `on_message`, `on_leave`.
- **Bus fanout**: Call `await self.publish(payload, event="chat")` inside channels to broadcast to all subscribers of the resolved topic. Bus instances are resolved per connection via `bus_factory` (supports DI, nested factories).
- **Registration**: Register channels with `hub.channel(MyChannel)` and mount the hub like any other route: `app = Lihil(hub)`.
- **Demo**: `demo/ws.py` and `demo/chat.html` now show room join/leave and broadcast chat across rooms using the new hub API.
- **DI in channels**: Channels receive the hub’s `Graph`; use `self.graph.aresolve(...)` to pull dependencies (e.g., custom bus backends, services) inside `on_join/on_message/on_leave`.

## Lihil is not

- **Not a microframework**: Lihil has an ever-growing and prosperous ecosystem that provides industrial, enterprise-ready features such as throttler, timeout, auth, and more
- **Not a one-man project**: Lihil is open-minded and contributions are always welcome.you can safely assume that your PR will be carefully reviewed
- **Not experimental**: Lihil optimizes based on real-world use cases rather than benchmarks

## Install

lihil requires python>=3.10

### pip

```bash
pip install "lihil[standard]"
```

The standard version comes with uvicorn

## Qucik Start

```python
from lihil import Lihil, Route, EventStream, SSE
from openai import OpenAI
from openai.types.chat import ChatCompletionChunk as Chunk
from openai.types.chat import ChatCompletionUserMessageParam as MessageIn

gpt = Route("/gpt", deps=[OpenAI])

def chunk_to_str(chunk: Chunk) -> str:
    if not chunk.choices:
        return ""
    return chunk.choices[0].delta.content or ""

@gpt.sub("/messages").post
async def add_new_message(
    client: OpenAPI, question: MessageIn, model: str
) -> Stream[Chunk]:
    yield SSE(event="open")

    chat_iter = client.responses.create(messages=[question], model=model, stream=True)
    async for chunk in chat_iter:
        yield SSE(event="token", data={"text": chunk_to_str(chunk)})

    yield SSE(event="close")
```

what frontend would receive

```text
event: open

event: token
data: {"text":"Hello"}

event: token
data: {"text":" world"}

event: token
data: {"text":"!"}

event: close
```

### Deprecation notice (routing API)

- Prefer `Route.merge(...)` (was `include_subroutes`) and `Lihil.include(...)` (was `include_routes`). The legacy names are deprecated and will be removed in `0.3.0`.

### HTTP vs WebSocket routing (do not mix)

- Keep HTTP `Route` trees and `WebSocketRoute` trees separate; merge only like with like, then pass both top-level routes to `Lihil`.

```python
api = Route("api")
v1 = api.sub("v1")
users = v1.sub("users")

ws = WebSocketRoute("ws")
ws_v1 = ws.sub("v1")
ws_notify = ws_v1.sub("notification")

app = Lihil(api, ws)  # do NOT merge Route into WebSocketRoute or vice versa
```

## Features

- **Param Parsing & Validation**

  Lihil provides a high level abstraction for parsing request, validating rquest data against endpoint type hints. various model is supported including
  	- `msgspec.Struct`,
	- `pydantic.BaseModel`,
	- `dataclasses.dataclass`,
	- `typing.TypedDict`

  By default, lihil uses `msgspec` to serialize/deserialize json data, which is extremly fast, we maintain first-class support for `pydantic.BaseModel` as well, no plugin required.
  see [benchmarks](https://jcristharif.com/msgspec/benchmarks.html),

  - Param Parsing: Automatically parse parameters from query strings, path parameters, headers, cookies, and request bodies
  - Validation: Parameters are automatically converted to & validated against their annotated types and constraints.
  - Custom Decoders: Apply custom decoders to have the maximum control of how your param should be parsed & validated.

- **Dependency injection**:
  **Inject factories, functions, sync/async, scoped/singletons based on type hints, blazingly fast.**

- **WebSocket**
  lihil supports the usage of websocket, you might use `WebSocketRoute.ws_handler` to register a function that handles websockets.

- **OpenAPI docs & Error Response Generator**
  Lihil creates smart & accurate openapi schemas based on your routes/endpoints, union types, `oneOf` responses, all supported.

- **Powerful Plugin System**:
  Lihil features a sophisticated plugin architecture that allows seamless integration of external libraries as if they were built-in components. Create custom plugins to extend functionality or integrate third-party services effortlessly.

- **Strong support for AI featuers**:
  lihil takes AI as a main usecase, AI related features such as SSE, MCP, remote handler will be implemented in the next few patches

There will also be tutorials on how to develop your own AI agent/chatbot using lihil.

- ASGI-compatibility & Vendor types from starlette
  - Lihil is ASGI copatible and works well with uvicorn and other ASGI servers.
  - ASGI middlewares that works for any ASGIApp should also work with lihil, including those from Starlette.


## Plugin System

Lihil's plugin system enables you to integrate external libraries seamlessly into your application as if they were built-in features. Any plugin that implements the `IPlugin` protocol can access endpoint information and wrap functionality around your endpoints.

### Plugin Execution Flow

When you apply multiple plugins like `@app.sub("/api/data").get(plugins=[plugin1.dec, plugin2.dec])`, here's how they execute:

```

Plugin Application (Setup Time - Left to Right)
┌─────────────────────────────────────────────────────────────┐
│  original_func → plugin1(ep_info) → plugin2(ep_info)        │
│                                                             │
│  Result: plugin2(plugin1(original_func))                    │
└─────────────────────────────────────────────────────────────┘

Request Execution (Runtime - Nested/Onion Pattern)
┌────────────────────────────────────────────────────────────┐
│                                                            │
│   Request                                                  │
│       │                                                    │
│       ▼                                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Plugin2 (Outermost)                                 │   │
│  │ ┌─────────────────────────────────────────────────┐ │   │
│  │ │ Plugin1 (Middle)                                │ │   │
│  │ │ ┌─────────────────────────────────────────────┐ │ │   │
│  │ │ │ Original Function (Core)                    │ │ │   │
│  │ │ │                                             │ │ │   │
│  │ │ │ async def get_data():                       │ │ │   │
│  │ │ │     return {"data": "value"}                │ │ │   │
│  │ │ │                                             │ │ │   │
│  │ │ └─────────────────────────────────────────────┘ │ │   │
│  │ └─────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────┘   │
│       │                                                    │
│       ▼                                                    │
│   Response                                                 │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

#### Execution Order:
   Request → Plugin2 → Plugin1 → get_data() → Plugin1 → Plugin2 → Response

#### Real Example with Premier Plugins:
```python
   @app.sub("/api").get(plugins=[
       plugin.timeout(5),           # Applied 1st → Executes Outermost
       plugin.retry(max_attempts=3), # Applied 2nd → Executes Middle
       plugin.cache(expire_s=60),   # Applied 3rd → Executes Innermost
   ])
```

Flow: Request → timeout → retry → cache → endpoint → cache → retry → timeout → Response


### Creating a Custom Plugin

A plugin is anything that implements the `IPlugin` protocol - either a callable or a class with a `decorate` method:

```python
from lihil.plugins.interface import IPlugin, IEndpointInfo
from lihil.interface import IAsyncFunc, P, R
from typing import Callable, Awaitable

class MyCustomPlugin:
    """Plugin that integrates external libraries with lihil endpoints"""

    def __init__(self, external_service):
        self.service = external_service

    def decorate(self, ep_info: IEndpointInfo[P, R]) -> Callable[P, Awaitable[R]]:
        """
        Access endpoint info and wrap functionality around it.
        ep_info contains:
        - ep_info.func: The original endpoint function
        - ep_info.sig: Parsed signature with type information
        - ep_info.graph: Dependency injection graph
        """
        original_func = ep_info.func

        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Pre-processing with external library
            await self.service.before_request(ep_info.sig)

            try:
                result = await original_func(*args, **kwargs)
                # Post-processing with external library
                return await self.service.process_result(result)
            except Exception as e:
                # Error handling with external library
                await self.service.handle_error(e)
                raise

        return wrapper

# Usage - integrate any external library
from some_external_lib import ExternalService

plugin = MyCustomPlugin(ExternalService())

@app.sub("/api/data").get(plugins=[plugin.decorate])
async def get_data() -> dict:
    return {"data": "value"}
```

Interface
```python
class IEndpointInfo(Protocol, Generic[P, R]):
    @property
    def graph(self) -> Graph: ...
    @property
    def func(self) -> IAsyncFunc[P, R]: ...
    @property
    def sig(self) -> EndpointSignature[R]: ...

class EndpointSignature(Base, Generic[R]):
    route_path: str

    query_params: ParamMap[QueryParam[Any]]
    path_params: ParamMap[PathParam[Any]]
    header_params: ParamMap[HeaderParam[Any] | CookieParam[Any]]
    body_param: tuple[str, BodyParam[bytes | FormData, Struct]] | None

    dependencies: ParamMap[DependentNode]
    transitive_params: set[str]
    """
    Transitive params are parameters required by dependencies, but not directly required by the endpoint function.
    """
    plugins: ParamMap[PluginParam]

    scoped: bool
    form_meta: FormMeta | None

    return_params: dict[int, EndpointReturn[R]]

    @property
    def default_return(self) -> EndpointReturn[R]:
        ...

    @property
    def status_code(self) -> int: ...

    @property
    def encoder(self) -> Callable[[Any], bytes]:
        ...

    @property
    def static(self) -> bool: ...

    @property
    def media_type(self) -> str: ...

```

This architecture allows you to:
- **Integrate any external library** as if it were built-in to lihil
- **Access full endpoint context** - signatures, types, dependency graphs
- **Wrap functionality** around endpoints with full control
- **Compose multiple plugins** for complex integrations
- **Zero configuration** - plugins work automatically based on decorators

## Error Handling with HTTPException

Lihil provides a powerful and flexible error handling system based on RFC 9457 Problem Details specification. The `HTTPException` class extends `DetailBase` and allows you to create structured, consistent error responses with rich metadata.

### Basic Usage

By default, Lihil automatically generates problem details from your exception class:

```python
from lihil import HTTPException

class UserNotFound(HTTPException[str]):
    """The user you are looking for does not exist"""
    __status__ = 404

# Usage in endpoint
@app.sub("/users/{user_id}").get
async def get_user(user_id: str):
    if not user_exists(user_id):
        raise UserNotFound(f"User with ID {user_id} not found")
    return get_user_data(user_id)
```

This will produce a JSON response like:
```json
{
  "type": "user-not-found",
  "title": "The user you are looking for does not exist",
  "status": 404,
  "detail": "User with ID 123 not found",
  "instance": "/users/123"
}
```

### Customizing Problem Details

#### 1. Default Behavior
- **Problem Type**: Automatically generated from class name in kebab-case (`UserNotFound` → `user-not-found`)
- **Problem Title**: Taken from the class docstring
- **Status Code**: Set via `__status__` class attribute (defaults to 422)

#### 2. Custom Problem Type and Title

You can customize the problem type and title using class attributes:

```python
class UserNotFound(HTTPException[str]):
    """The user you are looking for does not exist"""
    __status__ = 404
    __problem_type__ = "user-lookup-failed"
    __problem_title__ = "User Lookup Failed"
```

#### 3. Runtime Customization

You can also override problem details at runtime:

```python
@app.sub("/users/{user_id}").get
async def get_user(user_id: str):
    if not user_exists(user_id):
        raise UserNotFound(
            detail=f"User with ID {user_id} not found",
            problem_type="custom-user-error",
            problem_title="Custom User Error",
            status=404
        )
    return get_user_data(user_id)
```

### Advanced Customization

#### 1. Override `__problem_detail__` Method

For fine-grained control over how your exception transforms into a `ProblemDetail` object:

```python
from lihil.interface.problem import ProblemDetail

class ValidationError(HTTPException[dict]):
    """Request validation failed"""
    __status__ = 400

    def __problem_detail__(self, instance: str) -> ProblemDetail[dict]:
        return ProblemDetail(
            type_="validation-error",
            title="Request Validation Failed",
            status=400,
            detail=self.detail,
            instance=f"users/{instance}",
        )

# Usage
@app.sub("/users/{user_id}").post
async def update_user(user_data: UserUpdate):
    validation_errors = validate_user_data(user_data)
    if validation_errors:
        raise ValidationError(title="Updating user failed")
    return create_user_in_db(user_data)
```

#### 2. Override `__json_example__` Method

Customize how your exceptions appear in OpenAPI documentation:

```python
class UserNotFound(HTTPException[str]):
    """The user you are looking for does not exist"""
    __status__ = 404

    @classmethod
    def __json_example__(cls) -> ProblemDetail[str]:
        return ProblemDetail(
            type_="user-not-found",
            title="User Not Found",
            status=404,
            detail="User with ID 'user123' was not found in the system",
            instance="/api/v1/users/user123"
        )
```

This is especially useful for providing realistic examples in your API documentation, including specific `detail` and `instance` values that Lihil cannot automatically resolve from class attributes.

### Complex Error Scenarios

#### Generic Error with Type Information

```python
from typing import Generic, TypeVar

T = TypeVar('T')

class ResourceNotFound(HTTPException[T], Generic[T]):
    """The requested resource was not found"""
    __status__ = 404

    def __init__(self, detail: T, resource_type: str):
        super().__init__(detail)
        self.resource_type = resource_type

    def __problem_detail__(self, instance: str) -> ProblemDetail[T]:
        return ProblemDetail(
            type_=f"{self.resource_type}-not-found",
            title=f"{self.resource_type.title()} Not Found",
            status=404,
            detail=self.detail,
            instance=instance
        )

# Usage
@app.sub("/posts/{post_id}").get
async def get_post(post_id: str):
    if not post_exists(post_id):
        raise ResourceNotFound(
            detail=f"Post {post_id} does not exist",
            resource_type="post"
        )
    return get_post_data(post_id)
```

### Benefits

- **Consistency**: All error responses follow RFC 9457 Problem Details specification
- **Developer Experience**: Rich type information and clear error messages
- **Documentation**: Automatic OpenAPI schema generation with examples
- **Flexibility**: Multiple levels of customization from simple to advanced
- **Traceability**: Built-in problem page links in OpenAPI docs for debugging

The error handling system integrates seamlessly with Lihil's OpenAPI documentation generation, providing developers with comprehensive error schemas and examples in the generated API docs.

## AI Agent Support

**Using AI coding assistants with Lihil?** Check out [LIHIL_COPILOT.md](LIHIL_COPILOT.md) for:

- **AI Agent Best Practices** - Comprehensive guide for AI assistants working with Lihil
- **Common Mistakes & Solutions** - Learn from real AI agent errors and how to avoid them
- **Complete Templates** - Ready-to-use patterns that AI agents can follow
- **Lihil vs FastAPI Differences** - Critical syntax differences AI agents must know
- **How to Use as Prompt** - Instructions for Claude Code, Cursor, ChatGPT, and GitHub Copilot

**Quick Setup:** Copy the entire LIHIL_COPILOT.md content and paste it as system context in your AI tool. This ensures your AI assistant understands Lihil's unique syntax and avoids FastAPI assumptions.

## Tutorials

Check our detailed tutorials at https://lihil.cc, covering

- Core concepts, create endpoint, route, middlewares, etc.
- Configuring your app via `pyproject.toml`, or via command line arguments.
- Dependency Injection & Plugins
- Testing
- Type-Based Message System, Event listeners, atomic event handling, etc.
- Error Handling
- ...and much more

## Lihil Admin & Full stack template

See how lihil works here, a production-ready full stack template that uses react and lihil,

[lihil-fullstack-solopreneur-template](https://github.com/raceychan/fullstack-solopreneur-template)

covering real world usage & best practices of lihil.
A fullstack template for my fellow solopreneur, uses shadcn+tailwindcss+react+lihil+sqlalchemy+supabase+vercel+cloudlfare to end modern slavery

## Versioning

lihil follows semantic versioning after v1.0.0, where a version in x.y.z represents:

- x: major, breaking change
- y: minor, feature updates
- z: patch, bug fixes, typing updates

## Contributing

We welcome all contributions! Whether you're fixing bugs, adding features, improving documentation, or enhancing tests - every contribution matters.

### Quick Start for Contributors

1. **Fork & Clone**: Fork the repository and clone your fork
2. **Find Latest Branch**: Use `git branch -r | grep "version/"` to find the latest development branch (e.g., `version/0.2.23`)
3. **Create Feature Branch**: Branch from the latest version branch
4. **Make Changes**: Follow existing code conventions and add tests
5. **Submit PR**: Target your PR to the latest development branch

For detailed contributing guidelines, workflow, and project conventions, see our [Contributing Guide](.github/CONTRIBUTING.md).

## Roadmap

### Road Map before v1.0.0

- [x] **v0.1.x: Feature parity** (alpha stage)

Implementing core functionalities of lihil, feature parity with fastapi

- [x] **v0.2.x: Official Plugins** (current stage)

We would keep adding new features & plugins to lihil without making breaking changes.
This might be the last minor versions before v1.0.0.

- [ ] **v0.3.x: Performance boost**

The plan is to rewrite some components in c, roll out a server in c, or other performance optimizations in 0.3.x.

If we can do this without affect current implementations in 0.2.0 at all, 0.3.x may never occur and we would go straight to v1.0.0 from v0.2.x
