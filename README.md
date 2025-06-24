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

Lihil is

- **Professional**: Lihil comes with production-ready components that works with distributed systems.

  - **Authentication**,
  - **API resilience tools**: throttling, cache, retry, timeout, etc.
  - **Event Publishing**
  - ... and more

- **Productive**: Lihil provides as much typing information as possible to deliver best developer experience, complemented by extremly detailed error messages and docsstrings to let you debug at ease
- **Performant**: Blazing fast across tasks and conditions—Lihil ranks among the fastest Python web frameworks, outperforming other webframeworks by 50%–100%, see [lihil benchmarks](https://github.com/raceychan/lhl_bench), [independent benchmarks](https://web-frameworks-benchmark.netlify.app/result?l=python)

## Install

lihil requires python>=3.10

### pip

```bash
pip install "lihil[standard]"
```

This includes uvicorn and pyjwt

## Qucik Start

```python
from lihil import Lihil, Route, Stream
from openai import OpenAI
from openai.types.chat import ChatCompletionChunk as Chunk
from openai.types.chat import ChatCompletionUserMessageParam as MessageIn

gpt = Route("/gpt", deps=[OpenAI])

def message_encoder(chunk: Chunk) -> bytes:
    if not chunk.choices:
        return b""
	return chunk.choices[0].delta.content.encode() or b""

@gpt.sub("/messages").post(encoder=message_encoder)
async def add_new_message(
	client: OpenAPI, question: MessageIn, model: str
) -> Stream[Chunk]:
    chat_iter = client.responses.create(messages=[question], model=model, stream=True)
    async for chunk in chat_iter:
        yield chunk
```

## Features

- **Performance**

  Lihil is on average 50%-100% faster than other ASGI web frameworks, and is the fastest webframework in python running on uvicorn, see benchmarks [lhl benchmarks](https://github.com/raceychan/lhl_bench)

- **Param Parsing & Validation**

  Lihil provides a high level abstraction for parsing request, validating rquest data against endpoint type hints. various model is supported including
  	- `msgspec.Struct`,
	- `pydantic.BaseModel`,
	- `dataclasses.dataclass`,
	- `typing.TypedDict`

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


This architecture allows you to:
- **Integrate any external library** as if it were built-in to lihil
- **Access full endpoint context** - signatures, types, dependency graphs
- **Wrap functionality** around endpoints with full control
- **Compose multiple plugins** for complex integrations
- **Zero configuration** - plugins work automatically based on decorators


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

## Contributions & Roadmap

All contributions are welcome

Road Map before v1.0.0

- [x] v0.1.x: Feature parity (alpha stage)

Implementing core functionalities of lihil, feature parity with fastapi

- [x] v0.2.x: Official Plugins (current stage)

We would keep adding new features & plugins to lihil without making breaking changes.
This might be the last minor versions before v1.0.0.

- [ ] v0.3.x: Performance boost

The plan is to rewrite some components in c, roll out a server in c, or other performance optimizations in 0.3.x.

If we can do this without affect current implementations in 0.2.0 at all, 0.3.x may never occur and we would go stright to v1.0.0 from v0.2.x
