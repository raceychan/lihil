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

📚 Docs: https://lihil.cc/lihil
---

Lihil is

- **Performant**: lihil is fast, 50%-100% faster than ASGI frameworks offering similar functionalities, even more with its own server. see [benchmarks](https://github.com/raceychan/lhl_bench)
- **Productive**: ergonomic API with strong typing support and built-in solutions for common problems — along with beloved features like openapi docs generation — empowers users to build their apps swiftly without sacrificing extensibility.
- **Professional**: lihil is designed for enterprise web development, deliver robust&scalable solutions with best practices in microservice architecture and related patterns.

## Features

- **Dependency injection**: inject factories, functions, sync/async, scoped/singletons based on type hints, blazingly fast.

```python
async def get_conn(engine: Engine):
    async with engine.connect() as conn:
        yield conn

async def get_users(conn: AsyncConnection):
    return await conn.execute(text("SELECT * FROM users"))

@Route("users").get
async def list_users(users: Annotated[list[User], use(get_users)], is_active: bool=True):
    return [u for u in users if u.is_active == is_active]
```

- **OpenAPI docs & Error Response Generator**

lihil creates smart & accurate openapi schemas based on your routes/endpoints, union types, `oneOf` responses, all supported.

your exception classes are also automatically transformed to a `Problem` and genrate detailed response accordingly.

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

- **Problems Page**: declare exceptions using route decorator and they will be displayed as route response at openapi schemas & problem page

![problem page](/docs/images/order_out_of_stock_problem_page.png)

- **Data validation&Param Parsing**: using `msgspec`, which is about 12x faster than pydantic v2 for valiation and 25x memory efficient than pydantic v2, see [benchmarks](https://jcristharif.com/msgspec/benchmarks.html)

![msgspec_vs_others](/docs/images/msgspec_others.png)

- **Message System Bulitin**: publish command/event anywhere in your app with both in-process and out-of-process event handlers. Optimized data structure for maximum efficiency, de/serialize millions events from external service within seconds.

- **Great Testability**: bulit-in `LocalClient` to easily test your endpoints, routes, middlewares, app, everything.

- **Strong support for AI featuers**: lihil takes AI as a main usecase, AI related features such as SSE, remote handler will be well supported, there will also be tutorials on how to develop your own AI agent/chatbot using lihil.


## Compatability with starlette

Lihil is ASGI compatible and uses starlette as ASGI toolkit, which means that:

- starlette `Request`, `Response` and its subclasses, should work just fine with lihil.

However, this should be treated as an implementation detail, in other words, lihil might replace `starlette.Request` with somethings sharing the same interface.

asgi middlewares should always work tho.

## Quick Start

```python
from lihil import Lihil

lhl = Lihil()

@lhl.get
async def hello():
    return {"hello": "world!"}
```

a more realistic example would be

```python
from lihil import Lihil, Route, use, EventBus

chat_route = Route("/chats/{chat_id}")
message_route = chat_route / "messages"
UserToken = NewType("UserToken", str)

@chat_route.factory
def parse_access_token(
    service: UserService, token: UserToken
) -> ParsedToken:
    return service.decrypt_access_token(token)

@message_route.post
async def stream(
   service: ChatService,
   token: ParsedToken,
   bus: EventBus,
   chat_id: str,
   data: CreateMessage
) -> Annotated[Stream[GPTMessage], CustomEncoder(gpt_encoder)]:
    chat = service.get_user_chat(token.sub)
    chat.add_message(data)
    answer = service.ask(chat, model=data.model)
    buffer = []
    async for word in answer:
        buffer.append(word)
        yield word
    await bus.publish(NewMessageCreated(chat, buffer))
```

## Install

lihil(currently) requires python>=3.12

### pip

```bash
pip install lihil
```

### uv

if you want to install this project with uv

[uv install guide](https://docs.astral.sh/uv/getting-started/installation/#installation-methods)

1. init your web project with `project_name`

```bash
uv init project_name
```

2. install lihil via uv, this will solve all dependencies for your in a dedicated venv.

```bash
uv add lihil
```

## serve your application

### serve with lihil

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

This provides you the advantage to override configuration using command line arguments.

### serve with uvicorn

lihil is ASGI compatible, you can run it with an ASGI server, such as uvicorn
start a server with `app.py`, default to port 8000

1. create `__main__.py` under your project root.
2. use uvicorn to run you app in your `__main__.py`

```python
import uvicorn

uvicorn.run(app)
```

## versioning

lihil follows semantic versioning, where a version in x.y.z represents:

- x: major, breaking change
- y: minor, feature updates
- z: patch, bug fixes, typing updates

**v1.0.0** will be the first stable major version.

## Tutorials

check detailed tutorials at https://lihil.cc/lihil/tutorials/, covering

- Configuring your app via `pyproject.toml`, or via command line arguments.
- Dependency Injection & Plugins
- Testing
- Type-Based Message System, Event listeners, atomic event handling, etc.
- Error Handling
- ...and much more

## RoadMap

### version 0.1.x

complete core functionalities and make sure lihil is well tested, we will reach 100% test coverage before moving to 0.2.x.

### version 0.2.x

- Tutorials & videos on lihil and web dev in general
- Out-of-process event system (RabbitMQ, Kafka, etc.).
- A highly performant schema-based query builder based on asyncpg
- Local command handler(http rpc) and remote command handler (gRPC)
- More middleware and official plugins (e.g., throttling, caching, auth).

### version 0.3.x

- roll out our own server written in c & cython, 60K RPS+
