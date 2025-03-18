# lihil

![Lihil](./images/lihil_logo_transparent.png)

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

### http://docs.lihil.cc

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

### app.py

```python
from lihil import Lihil, Route, Stream, Text, HTTPException

lhl = Lihil()

# default to json serialization
@lhl.get
async def pingpong():
    return {"ping": "pong"}

# use type Annotation to instruct serialization and status 
@lhl.sub("/{king}").get
def kingkong(king: str) -> Resp[Text, 200]:
    return f"{king}, kong"
```

server-sent event with customized encoder

```python
llm = Route("llm/{model}")

@llm.get
async def stream(
    model: str = "gpt-4o", question: str, client: OpenAI
) -> Annotated[Stream[Event], CustomEncoder(event_encoder)]:
    return client.responses.create(
        model=model,
        input=question,
        stream=True,
)
```


## Install

lihil requires python 3.12

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