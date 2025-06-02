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

🌐 Choose your language：

- 🇨🇳 [中文README](README_CN.md)

## 📚 Docs: https://lihil.cc

Lihil is

- **Productive**: ergonomic API with strong typing support and built-in solutions for common problems — along with beloved features like openapi docs generation — empowers users to build their apps swiftly without sacrificing extensibility.
- **Professional**: Lihil comes with middlewares that are essential for enterprise development—such as authentication, authorization, event publishing, etc. Ensure productivity from day zero. Catered to modern development styles and architectures, including TDD and DDD.
- **Performant**: Blazing fast across tasks and conditions—Lihil ranks among the fastest Python web frameworks, outperforming comparable ASGI frameworks by 50%–100%, see [lihil benchmarks](https://github.com/raceychan/lhl_bench), [independent benchmarks](https://web-frameworks-benchmark.netlify.app/result?l=python)

## Install

lihil requires python>=3.10

### pip

```bash
pip install "lihil[standard]"
```

This includes uvicorn and pyjwt

## Qucik Start

```python
from lihil import Lihil, Route, Text

root = Route()

@root.get
def hello(world: str = "world") -> Annotated[Text, 200]:
    return f"hello, {world}!"

if __name__ == "__main__":
    lhl = Lihil(root)
    lhl.run(__file__)
```

## Features

- **Performance**

  Lihil is on average 50%-100% faster than other ASGI web frameworks, and is the fastest webframework in python running on uvicorn, see benchmarks [lhl benchmarks](https://github.com/raceychan/lhl_bench)

- **Param Parsing & Validation**

  Lihil provides a high level abstraction for parsing request, validating rquest data against endpoint type hints. various model is supported including `msgspec.Struct`, `pydantic.BaseModel`, `dataclasses.dataclass`, ... etc.

  By default, lihil uses `msgspec` to serialize/deserialize json data, which is extremly fast.
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

- **Bettery included**:
  Lihil comes with authentification & authorization, throttling, messaging and other plugins.

- **Low memory Usage**
  lihil is deeply optimized for memory usage, significantly reduce GC overhead, making your services more robust and resilient under load.

- **Strong support for AI featuers**:
  lihil takes AI as a main usecase, AI related features such as SSE, MCP, remote handler will be implemented in the next few patches

  - [x] SSE
  - [ ] MCP
  - [ ] Rmote Handler

There will also be tutorials on how to develop your own AI agent/chatbot using lihil.

- ASGI-compatibility & Vendor types from starlette
  - Lihil is ASGI copatible and works well with uvicorn and other ASGI servers.
  - ASGI middlewares that works for any ASGIApp should also work with lihil, including those from Starlette.

## Tutorials

Check our detailed tutorials at https://lihil.cc, covering

- Core concepts, create endpoint, route, middlewares, etc.
- Configuring your app via `pyproject.toml`, or via command line arguments.
- Dependency Injection & Plugins
- Testing
- Type-Based Message System, Event listeners, atomic event handling, etc.
- Error Handling
- ...and much more

## Versioning

lihil follows semantic versioning, where a version in x.y.z represents:

- x: major, breaking change
- y: minor, feature updates
- z: patch, bug fixes, typing updates

Lihil will have at max 10 minor version, which means if lihil reach v0.9.x, then there will be no minor version before v1.0.0.


<!-- Thecnically, **v1.0.0** will be the first stable major version. However, breaking changes from 0.4.x onwards is highly unlikely. -->
