![Lihil](docs/images/lihil_logo_transparent.png)

# Lihil
**Lihil** &nbsp;*/ˈliːhaɪl/* — a **performant**, **productive**, and **professional** web framework with a vision:

> **Making Python the mainstream programming language for web development.**

**lihil is *100%* test covered and *strictly* typed.**

[![codecov](https://codecov.io/gh/raceychan/lihil/graph/badge.svg?token=KOK5S1IGVX)](https://codecov.io/gh/raceychan/lihil)
[![PyPI version](https://badge.fury.io/py/lihil.svg)](https://badge.fury.io/py/lihil)
[![License](https://img.shields.io/github/license/raceychan/lihil)](https://github.com/raceychan/lihil/blob/master/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/lihil.svg)](https://pypistats.org/packages/lihil)
[![Python Version](https://img.shields.io/pypi/pyversions/lihil.svg)](https://pypi.org/project/lihil/)

📚 Docs: https://lihil.cc
---

Lihil is


- **Productive**: ergonomic API with strong typing support and built-in solutions for common problems — along with beloved features like openapi docs generation — empowers users to build their apps swiftly without sacrificing extensibility.
- **Professional**: Lihil comes with middlewares that are essential for enterprise development—such as authentication, authorization, event publishing, etc. Ensure productivity from day zero. Catered to modern development styles and architectures, including TDD and DDD.
- **Performant**: Blazing fast across tasks and conditions—Lihil ranks among the fastest Python web frameworks, outperforming comparable ASGI frameworks by 50%–100%, see [lihil benchmarks](https://github.com/raceychan/lhl_bench),  [independent benchmarks](https://web-frameworks-benchmark.netlify.app/result?l=python)


## Features

### **Param Parsing & Validation**


Lihil provides a high level abstraction for parsing request, validating rquest data against endpoint type hints using `msgspec`, which is extremly performant, **12x faster** and **25x more memory efficient** than pydantic v2.

see [benchmarks](https://jcristharif.com/msgspec/benchmarks.html),


- Param Parsing: Automatically parse parameters from query strings, path parameters, headers, cookies, and request bodies
- Validation: Parameters are automatically converted to & validated against their annotated types and constraints.
- Custom Decoders: Apply custom decoders to have the maximum control of how your param should be parsed & validated.

```python
from lihil import Payload, Param, Route, Meta
from .service import get_user_service, UserService

class UserPayload(Payload): # memory optimized data structure that does not involve in gc.
    user_name: Annotated[str, Param(min_length=1)] # non-empty string with length >= 1

all_users = Route("users")
all_users.factory(get_user_service)

# All parameters are automatically parsed and validated
@all_users.sub("{user_id}").post # POST /users/{user_id}
async def create_user(
    user_id: str,                                           # from URL path
    auth_token: Annotated[str, Param(alias="x-auth-token")],       # from request headers
    user_data: UserPayload,                                 # from request body
    service: UserService
) -> Resp[str, 201]: ...
```


### **Dependency injection**:

- **Inject factories, functions, sync/async, scoped/singletons based on type hints, blazingly fast.**

```python
from lihil import Route, Ignore, Param
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection

async def get_conn(engine: AsyncEngine) -> AsyncConnection:
    async with engine.connect() as conn:
        yield conn

async def get_users(conn: AsyncConnection, nums: Annotated[int, Param(lt=100)]) -> Ignore[list[User]]:
    return await conn.execute(text(f"SELECT * FROM users limit {nums}"))

all_users = Route("users")

@all_users.get
async def list_users(users: Annotated[list[User], use(get_users)], is_active: bool=True) -> list[[User]]:
    return [u for u in users if u.is_active == is_active]
```


### **WebSocket**

lihil supports the usage of websocket, you might use `WebSocketRoute.ws_handler` to register a function that handles websockets.

```python
from lihil import WebSocketRoute, WebSocket, Ignore, use

ws_route = WebSocketRoute("web_socket/{session_id}")

async def ws_factory(ws: WebSocket) -> Ignore[AsyncResource[WebSocket]]:
    await ws.accept()
    yield ws
    await ws.close()

@ws_route.ws_handler
async def ws_handler(
    ws: Annotated[WebSocket, use(ws_factory, reuse=False)],
    session_id: str,
    max_users: int,
):
    assert session_id == "session123" and max_users == 5
    await ws.send_text("Hello, world!")

lhl = Lihil[None]()
lhl.include_routes(ws_route)
```

Testing
```python
from lihil.vendors import TestClient # require httpx installed

client = TestClient(lhl)
with client:
    with client.websocket_connect(
        "/web_socket/session123?max_users=5"
    ) as websocket:
        data = websocket.receive_text()
        assert data == "Hello, world!"
```


### **OpenAPI docs & Error Response Generator**

- Lihil creates smart & accurate openapi schemas based on your routes/endpoints, union types, `oneOf` responses, all supported.

- Your exception classes are also automatically transformed to a `Problem` and genrate detailed response accordingly.

```python
class OutOfStockError(HTTPException[str]):
    "The order can't be placed because items are out of stock"
    __status__ = 422

    def __init__(self, order: Order):
        detail: str = f"{order} can't be placed, because {order.items} is short in quantity"
        super().__init__(detail)
```

when such exception is raised from endpoint, client would receive a response like this

![outofstock](/docs/images/order_out_of_stock.png)

### **Problems Page**:

Declare exceptions using route decorator and they will be displayed as route response at openapi schemas & problem page

![problem page](/docs/images/order_out_of_stock_problem_page.png)


### **Auth Builtin**:

- Lihil comes with authentification & authorization plugins out of the box.

```python
from lihil import Payload, Route
from lihil.auth.jwt import JWTAuth, JWTPayload
from lihil.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm

class UserProfile(JWTPayload):
    # get support from typehints about what are the available claims
    __jwt_claims__ = {"expires_in": 300}  # jwt expires in 300 seconds.

    user_id: str = field(name="sub")
    role: Literal["admin", "user"] = "user"

@me.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))
async def get_user(profile: JWTAuth[UserProfile]) -> User:
    assert profile.role == "user"
    return User(name="user", email="user@email.com")

@token.post
async def create_token(credentials: OAuthLoginForm) -> JWTAuth[UserProfile]:
    return UserProfile(user_id="user123")
```

> When you return `UserProfile` from `create_token` endpoint, it would automatically be serialized as a json web token.

### **Message System Bulitin**:

- Publish command/event anywhere in your app with both in-process and out-of-process event handlers. Optimized data structure for maximum efficiency, de/serialize millions events from external service within seconds.

```python
from lihil import Route, EventBus, Empty, Resp, status

@Route("users").post
async def create_user(data: UserCreate, service: UserService, bus: EventBus) -> Resp[Empty, status.Created]:
    user_id = await service.create_user(data)
    await bus.publish(UserCreated(**data.asdict(), user_id=user_id))
```


### **Great Testability**:

- bulit-in `LocalClient` to easily and independently test your endpoints, routes, middlewares, app.

### **Low memory Usage**

- lihil is deeply optimized for memory usage, significantly reduce GC overhead, making your services more robust and resilient under load.

### **Strong support for AI featuers**:

- lihil takes AI as a main usecase, AI related features such as SSE, MCP, remote handler will be implemented before 0.3.x

- [X] SSE
- [ ] MCP
- [ ] Rmote Handler

There will also be tutorials on how to develop your own AI agent/chatbot using lihil.

## ASGI-compatibility & Vendor types from starlette

- Lihil is ASGI compatible and absorbs the `Request`, `Response`, `WebSocket` interfaces from Starlette.
> Implementations of these interfaces are subject to change.

- You can declare `Request` in your endpoint and return an instance of `Response`(or its subclass).

```python
from lihil import Request, Response

@users.post
async def create_user(req: Request):
    return Response(content=b"hello, world")
```

- ASGI middlewares that works for any ASGIApp should also work with lihil, including those from Starlette.

## Quick Start

```python
from lihil import Lihil

lhl = Lihil()

@lhl.get
async def hello():
    return {"hello": "world!"}
```

```python
from lihil import Lihil, Route, use, EventBus, Param

chat_route = Route("/chats/{chat_id}")
message_route = chat_route / "messages"
UserToken = NewType("UserToken", str)

chat_route.factory(UserService)
message_route.factory(get_chat_service)

@chat_route.factory
def parse_access_token(
    service: UserService, token: UserToken
) -> ParsedToken:
    return service.decrypt_access_token(token)

@message_route.post
async def stream(
   service: ChatService,  # get_chat_service gets called and inject instance of ChatService here.
   profile: JWTAuth[UserProfile], # Auth Bearer: {jwt_token}` Header gets validated into UserProfile.
   bus: EventBus,
   chat_id: Annotated[str, Param[min_length=1]], # validates the path param `chat_id` has to be a string with length > 1.
   data: CreateMessage # request body
) -> Annotated[Stream[GPTMessage], CustomEncoder(gpt_encoder)]: # returns server side events
    chat = service.get_user_chat(profile.user_id)
    chat.add_message(data)
    answer = service.ask(chat, model=data.model)
    buffer = []
    async for word in answer:
        buffer.append(word)
        yield word
    await bus.publish(NewMessageCreated(chat, buffer))
```

## Install

lihil(currently) requires python>=3.10

### pip

```bash
pip install lihil
```

### uv

if you want to install lihil using uv

[uv install guide](https://docs.astral.sh/uv/getting-started/installation/#installation-methods)

1. init your web project with `project_name`

```bash
uv init project_name
```

2. install lihil via uv, this will solve all dependencies for your in a dedicated virtual environment.

```bash
uv add lihil
```

## Serve your application

### Serve with lihil

#### app.py

```python
from lihil import Lihil

# your application code

lhl = Lihil()

if __name__ == "__main__":
    lhl.run(__file__)
```

then in command line

```python
uv run python -m myproject.app --server.port=8080
```

This allows you to override configurations using command-line arguments.

If your app is deployed in a containerized environment, such as Kubernetes, providing secrets this way is usually safer than storing them in files.

use `--help` to see available configs.

### Serve with uvicorn

lihil is ASGI compatible, you can run it with an ASGI server, such as uvicorn
start a server with `app.py`, default to port 8000

1. create `__main__.py` under your project root.
2. use uvicorn to run you app in your `__main__.py`

```python
import uvicorn

uvicorn.run(app)
```

## Versioning

lihil follows semantic versioning, where a version in x.y.z represents:

- x: major, breaking change
- y: minor, feature updates
- z: patch, bug fixes, typing updates

Thecnically, **v1.0.0 will be the first stable major version. However, breaking changes from 0.4.x onwards is highly unlikely.

## Tutorials

check detailed tutorials at https://lihil.cc/lihil/tutorials/, covering

- Core concepts, create endpoint, route, middlewares, etc.
- Configuring your app via `pyproject.toml`, or via command line arguments.
- Dependency Injection & Plugins
- Testing
- Type-Based Message System, Event listeners, atomic event handling, etc.
- Error Handling
- ...and much more

## Contribution & RoadMap

No contribution is trivial, and every contribution is appreciated. However, our focus and goals vary at different stages of this project.

### version 0.1.x: Feature Parity (alpha-stage)

- Feature Parity: we should offer core functionalities of a web framework ASAP, similar to what fastapi is offering right now. Given both fastapi and lihil uses starlette, this should not take too much effort.

- Correctness: We should have a preliminary understanding of lihil's capabilities—knowing what should be supported and what shouldn't. This allows us to distinguish between correct and incorrect usage by users.

- Test Coverage: There's no such thing as too many tests. For every patch, we should maintain at least 99% test coverage, and 100% for the last patch of 0.1.x. For core code, 100% coverage is just the baseline—we should continuously add test cases to ensure reliability.

Based on the above points, in version v0.1.x, we welcome contributions in the following areas:

- Documentation: Fix and expand the documentation. Since lihil is actively evolving, features may change or extend, and we need to keep the documentation up to date.

- Testing: Contribute both successful and failing test cases to improve coverage and reliability.

- Feature Requests: We are open to discussions on what features lihil should have or how existing features can be improved. However, at this stage, we take a conservative approach to adding new features unless there is a significant advantage.


### version 0.2.x: Cool Stuff (beta-stage)

- Out-of-process event system (RabbitMQ, Kafka, etc.).
- A highly performant schema-based query builder based on asyncpg
- Local command handler(http rpc) and remote command handler (gRPC)
- More middleware and official plugins (e.g., throttling, caching, auth).


### version 0.3.x: Bug Fixes & Performance boost

Premature optimization is the root of all eveil, we will not do heavy optimization unless lihil has almost every feature we want.
We might deliver our own server in c, also rewrite some hot-spot classes such as `Request` and `Response`.
Experiments show that this would make lihil as fast as some rust webframworks like actix and axum, but the price for that is the speed of iteration gets much slower.

### version 0.4.x onwards:  production ready
