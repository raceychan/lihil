#

![Lihil](./images/lihil_logo_transparent.png)

**Lihil** &nbsp;*/ˈliːhaɪl/* — a **performant**, **productive**, and **professional** web framework with a vision:

> **Making Python the mainstream programming language for web development.**

[![codecov](https://codecov.io/gh/raceychan/lihil/graph/badge.svg?token=KOK5S1IGVX)](https://codecov.io/gh/raceychan/lihil)
[![PyPI version](https://badge.fury.io/py/lihil.svg)](https://badge.fury.io/py/lihil)
[![License](https://img.shields.io/github/license/raceychan/lihil)](https://github.com/raceychan/lihil/blob/master/LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/lihil.svg)](https://pypistats.org/packages/lihil)
[![Python Version](https://img.shields.io/pypi/pyversions/lihil.svg)](https://pypi.org/project/lihil/)

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


checkout [features page](./features.md) for detailed explaination with scrrenshot & code examples.


## First impression

```python
from lihil import Lihil, Route, EventBus, Event, status
from msgspec import field, Struct

from .users.infra import UserService

user_route = Route("/users")

class UserSignup(Payload):
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str

class UserCreated(Event):
    id: str
    name: str

@user_route.post
async def singup_user(
    data: UserSignup, service: UserService, bus: EventBus
) -> Resp[str, status.Created]:
    user = await service.signup(data)
    event = UserCreated(id=user.id, name=user.name)
    await bus.publish(event)
    return user.id

lhl = Lihil(routes=[user_route])

if __name__ == "__main__":
    lhl.run()
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



## versioning

lihil follows semantic versioning, where a version in x.y.z represents:

- x: major, breaking change
- y: minor, feature updates
- z: patch, bug fixes, typing updates

**v1.0.0** will be the first stable major version.
