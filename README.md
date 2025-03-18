![Lihil](docs/images/lihil_logo_transparent.png)

# Lihil
**Lihil** &nbsp;*/ˈliːhaɪl/* — a **performant**, **productive**, and **professional** web framework with a vision:

> **Making Python the mainstream programming language for web development.**

[![codecov](https://codecov.io/gh/raceychan/lihil/graph/badge.svg?token=KOK5S1IGVX)](https://codecov.io/gh/raceychan/lihil)
[![PyPI version](https://badge.fury.io/py/lihil.svg)](https://badge.fury.io/py/lihil)
[![License](https://img.shields.io/github/license/raceychan/lihil)](https://github.com/raceychan/lihil/blob/master/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/lihil.svg)](https://pypistats.org/packages/lihil)
[![Python Version](https://img.shields.io/pypi/pyversions/lihil.svg)](https://pypi.org/project/lihil/)

---

## Source

### https://github.com/raceychan/lihil

## Docs

### https://lihil.cc/lihil

---

Lihil is

- **Performant**: lihil is fast, 50%-100% faster than ASGI frameworks offering similar functionalities, even more with its own server. see [benchmarks](https://github.com/raceychan/lhl_bench)

- **Productive**: ergonomic API with strong typing support and built-in solutions for common problems — along with beloved features like openapi docs generation — empowers users to build their apps swiftly without sacrificing extensibility.

- **professional**: Start small, move fast, achieve great, lihil follows industry standards (RFC9110, 9457, ...) and best practices (EDA, service choreography, etc) to deliver robust and scalable solutions.

## Features

- **Data validation&Param Parsing**: using `msgspec`, which is about 12x faster than pydantic v2 for valiation and 25x memory efficient than pydantic v2, see [benchmarks](https://jcristharif.com/msgspec/benchmarks.html)
- **Dependency injection**: inject factories, functions, sync/async, scoped/singletons based on type hints, blazingly fast. 
- **OpenAPI docs**: create smart & accurate openapi schemas based on your routes/endpoints, union types, `oneOf` responses, all supported. 
- **Problems Page**: transform your exceptions into nicely documented ProblemDetails, where client can search via your response. 
- **Great Testability**: bulit-in `LocalClient` to easily test your endpoints, routes, middlewares, app, everything.  
- **Strong support for AI featuers**: lihil takes AI as a main usecase, AI related features such as SSE, remote handler will be well supported, there will also be tutorials on how to develop your own AI agent/chatbot using lihil.

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
ParsedToken = NewType("ParsedToken", str)

@chat_route.factory
def parse_access_token(
    service: UserService, token: UserToken
) -> AccessToken:
    return service.decrypt_access_token(token)

@message.post
async def stream(
   service: ChatService,  
   token: ParsedToken, 
   bus: EventBus,
   chat_id: str, 
   data: CreateMessage
) -> Annotated[Stream[Event], CustomEncoder(event_encoder)]:
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

uv is the recommended way of using this project, you can install it with a single command [uv install guide](https://docs.astral.sh/uv/getting-started/installation/#installation-methods)

1. init your web project with `project_name`

```bash
uv init project_name
```

2. install lihil via uv, this will solve all dependencies for your in a dedicated venv.

```bash
uv add lihil
```

## serve your application

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

check detailed tutorials at https://lihil.cc/lihil/tutorial, covering

- Configuring your app via `pyproject.toml`, or via command line arguments.
- Dependency Injection & Plugins
- Testing
- Type-Based Message System, Event listeners, atomic event handling, etc.
- Error Handling
- ...and much more

