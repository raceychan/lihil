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

- **Data validation** using `msgspec`, which is about 12x faster than pydantic v2 for valiation and 25x memory efficient than pydantic v2, see [benchmarks](https://jcristharif.com/msgspec/benchmarks.html)
- **Advanced dependency injection**, using `ididi` written in cython, inject params, resources, plugins, extremly powerful and fast.
- **OpenAPI docs** and json schema automatically generated with accurate type information, union type, json examples, problem detail(RFC-9457) and more.
- **Great Testability**, lihil is designed to be tested, however you want, web framework specifics objects such as `Response`, `content-type` is abstracted away(you can still use them) via `Marks`, you can test your endpoints like regular functions.
- **Strong support for AI featuers**, lihil takes AI as a main usecase, AI related features such as SSE, remote handler will be well supported, there will also be tutorials on how to develop your own AI agent/chatbot using lihil.

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
) -> Annotated[Resp[Stream[str], 201], CustomEncoder(answer_encoder)]:
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

lihil requires python>=3.12

### pip

```bash
pip install lihil
```

### uv

0. [uv install guide](https://docs.astral.sh/uv/getting-started/installation/#installation-methods)

1. init project with `project_name`

```bash
uv init project_name
```

2. install lihil

```bash
uv add lihil
```

### Serve your application

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

**v0.1.3** is the first working version of lihil
**v1.0.0** will be the first stable major version.

