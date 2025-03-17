![Lihil](docs/lihil_logo_transparent.png)

# Lihil
**Lihil** &nbsp;*/ˈliːhaɪl/* — a **performant**, **productive**, and **professional** web framework with a vision:

> **Making Python the mainstream programming language for web development.**

GitHub Page: [lihil](https://github.com/raceychan/lihil)

---

Lihil is

- **Performant**: lihil is fast, 50%-100% faster than ASGI frameworks offering similar funcitonalities, even more with its own server. see [benchmarks](https://github.com/raceychan/lhl_bench)

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

## Error Hanlding

- use `route.get(errors=VioletsAreBlue)` to declare a endpoint response

```python
class VioletsAreBlue(HTTPException[str]):
    "how about you?"
    __status__ = 418


@lhl.post(errors=VioletsAreBlue)
async def roses_are_red():
    raise VioletsAreBlue("I am a pythonista")
```

- use `lihil.problems.problem_solver` as decorator to register a error handler, error will be parsed as Problem Detail.

```python
from lihil.problems import problem_solver

# NOTE: you can use type union for exc, e.g. UserNotFound | status.NOT_FOUND
@problem_solver
def handle_404(req: Request, exc: Literal[404]):
    return Response("resource not found", status_code=404)
```

A solver that handles a specific exception type (e.g., `UserNotFound`) takes precedence over a solver that handles the status code (e.g., `404`).

### Exception-Problem mapping

lihil automatically generates a response and documentation based on your HTTPException,
Here is the generated doc for the endpoint `roses_are_red`

![roses_are_red](/docs/roses_are_red_link.png)

click url under `External documentation` tab

we will see the detailed problem page

![problem page](/docs/roses_are_red_problempage.png)

By default, every endpoint will have at least one response with code `422` for `InvalidRequestErrors`.

Here is one example response of `InvalidRequestErrors`.

```json
{
  "type_": "invalid-request-errors",
  "status": 422,
  "title": "Missing",
  "detail": [
    {
      "type": "MissingRequestParam",
      "location": "query",
      "param": "q",
      "message": "Param is Missing"
    },
    {
      "type": "MissingRequestParam",
      "location": "query",
      "param": "r",
      "message": "Param is Missing"
    }
  ],
  "instance": "/users"
}
```

- To alter the creation of the response, use `lihil.problems.problem_solver` to register your solver.
- To change the documentation, override `DetailBase.__json_example__` and `DetailBase.__problem_detail__`.
- To extend the error detail, provide typevar when inheriting `HTTPException[T]`.

### Extraordinary typing support

typing plays a significant role in the world of `lihil`, lihil combines generics, function overriding, paramspec and other advanced typing features to give you the best typing support possible.

with its dedicated, insanely detailed typing support, lihil will give you something to smile about.

![typing](/docs/good_typing_status.png)

![typing2](/docs/good_typing2.png)

### Type-Based Message System

Lihil has built-in support for both in-process message handling (Beta) and out-of-process message handling (implementing), it is recommended to use `EventBus` over `BackGroundTask` for event handling.

There are three primitives for event:

1. publish: asynchronous and blocking event handling that shares the same scoep with caller.
2. emit: non-blocking asynchrounous event hanlding, has its own scope.
3. sink: a thin wrapper around external dependency for data persistence, such as message queue or database.

```python
from lihil import Resp, Route, status
from lihil.plugins.bus import Event, EventBus
from lihil.plugins.testclient import LocalClient


class TodoCreated(Event):
    name: str
    content: str


async def listen_create(created: TodoCreated):
    assert created.name
    assert created.content


async def listen_twice(created: TodoCreated):
    assert created.name
    assert created.content


bus_route = Route("/bus", listeners=[listen_create, listen_twice])


@bus_route.post
async def create_todo(name: str, content: str, bus: EventBus) -> Resp[None, status.OK]:
    await bus.publish(TodoCreated(name, content))
```

### Plugins

#### Initialization

- init at lifespan

```python
from lihil import Graph

async def lifespan(app: Lihil):
    async with YourPlugin() as up:
        app.graph.register_singleton(up)
        yield

lhl = LIhil(lifespan=lifespan)
```

use it anywhere with DI

- init at middleware

plugin can be initialized and injected into middleware,
middleware can be bind to differernt route, for example `Throttle`

```python
# pseudo code
class ThrottleMiddleware:
    def __init__(self, app: Ignore[ASGIApp], redis: Redis):
        self.app = app
        self.redis = redis

    async def __call__(self, app):
        await self.redis.run_throttle_script
        await self.app

lihil.add_middleware(lambda app: app.graph.resolve(ThrottleMiddleware))
```

- use it at your endpoints

```python
async def create_user(user_name: str, plugin: YourPlugin): ...
```

## Why not just FastAPI?

I have been using FastAPI since october 2020, and have built dozens of apps using it.
I am greatly satisfied with its API design and DI system, there a few architectual decisions I'd like to change and a few functionalities I'd like to have, specificially:

### DI (dependency injection)

NOTE: `Depends` refers to fastapi's di system

- Availability, `Depends` is simple and easy to use, but it is tightly coupled with routes and requests, which limits its usability, a DI system that can be used across different levels and components of my application is prefered to avoid creating duplicated resources.

- performance, `Depends` is resolved in a giant function which slows down dependency resolution as it does not optimize for different kind of dependency.

### Data validation

From my project experiences, using msgspec over pydantic for data deserialization and validation brought more than 10x performance boost.

`msgspec.Struct` is extremly performant, it is faster to create than a plain python class, and is often faster than a regular `dict` for non-trivial cases.

### Testing

I'd like to have a finer control of how my application works, take this endpoint as an example:

```python
@todo_route.post
asyc def create_todo(data: CreateTodo, repo: TodoRepo, bus: EventBus) -> Resp[Todo, status.Created]:
    todo =  Todo.from_data(CreateTodo)
    await repo.add(todo)
    awati bus.publish(TodoCreated.from_todo(todo))
    return todo
```

Starlette/FastAPI provies a `TestClient`(which lihil also supports), that goes through your whole app, but it takes quite a lot of efforts to mock everything.

You can test these with lihil

- the function `create_todo`, which requires all menually inject all three params and return a `Todo`
- the endpoint `todo_route.post` which requires only `CreateTodo` without dependencies, returns a json serialized `Todo` in bytes.
- the route `todo_route` with middlewares
- the app with everything

---

## Tutorials

### Config

You can alter app behavior by `lihil.config.AppConfig`

#### via config file

```python
lhl = Lihil(config_file="pyproject.toml")
```

This will look for `tool.lihil` table in the `pyproject.toml` file
extra/unkown keys will be forbidden to help prevent misconfiging

Note: currently only toml file is supported

#### build `lihil.config.AppConfig` instance menually

```python
lhl = Lihil(app_config=AppConfig(version="0.1.1"))
```

this is particularly useful if you want to inherit from AppConfig and extend it.

```python
from lihil.config import AppConfig

class MyConfig(AppConfig):
    app_name: str

config = MyConfig.from_file("myconfig.toml")
```

You can override config with command line arguments:

```example
python app.py --oas.title "New Title" --is_prod true
```

use `.` to express nested fields
