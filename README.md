# lihil

**lihil** &nbsp;*/ˈliːhaɪl/* — a **performant**, **productive**, and **professional** web framework with a vision:

> **Making Python the mainstream programming language for web development.**

Lihil is

- **Performant** lihil is unpythonically fast, 1-3x faster than other asgi frameworks in most benchmarks, event more with its own server.

- **Productive** ergonomic API with strong typing support and built-in solutions for common problems — along with beloved features like openapi docs generation — empowers users to build their apps swiftly without sacrificing extensibility.

- **professional** Start small, move fast, achieve great, lihil follows industry standards (RFC9110, 9457, ...) and best practices (EDA, service choreography, etc) to deliver robust and scalable solutions.

## Features

- **Advanced dependency injection**, inject params, resources, plugins, extremly powerful and fast.
- **OpenAPI docs** and json schema automatically generated with accurate type information, union type, json examples, problem detail(RFC-9457) and more.
- **Great Testability**, lihil abstracts away web framework specifics objects such as `Response`, `content-type` via  annotations, you can test your endpoints like regular functions.
- **First class support for AI**, from api to architecture, lihi is built with AI in mind.

## Quick Start

### app.py

```python
from lihil import Lihil, Text, HTTPException

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

customized encoder
```python
llm = Route("llm/{model}")

@llm
async def stream(model: str="gpt-4o", question: str, client: OpenAI
) -> Annotated[Stream[Event], CustomEncoder(event_encoder)]:
    return client.responses.create(
        model=model,
        input=question,
        stream=True,
)
```

### Serve

lihil is ASGI compatible, youcan run it with an ASGI server, such as uvicorn

start a server, default to port 8000

```bash
uvicorn app:lhl
```

## Error Hanlding

use `catch` as decorator to register a error handler, error will be parsed as Problem Detail defined in RFC9457

use `route.get(errors=[UserNotFound])` to declare a endpoint response

```python
class VioletsAreBlue(HTTPException[str]):
    "I am a pythonista"


@lhl.post(errors=VioletsAreBlue)
async def roses_are_red():
    raise VioletsAreBlue("and so are you")
```

### Exception-Problem mapping

by default, lihil will generate a `Problem` with `Problem detail` based on your raised `HTTPException`

### Plugins

#### Initialization

- init at lifespan


```python
from lihil import Graph


async def lifespan(app: Lihil):
    yourplugin = await YourPlugin().__aenter__
    app.graph.register_singleton(your_plugin)
    yield
    await YourPlugin().__aexit__()

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


- init each request
```python
async def create_user(user_name: str, plugin: YourPlugin): ...
```



## Why not just FastAPI?

I have been using FastAPI since october 2020, and have built dozens of apps using it, 
I am greatly satisfied with its API design and DI system, there a few architectual decisions I'd like to change and a few functionalities I'd like to have, specificially:

### DI (dependency injection)

NOTE: `Dependens` refers to fastapi's di system

- Availability, `Depends` is simple and easy to use, but it is tightly coupled with routes and requests, which limits its usability, a DI system that can be used across different levels and components of my application is prefered to avoid creating duplicated resources.

- performance, `Depends` is resolved in a giant function which slows down dependency resolution as it does not optimize for different kind of dependency.


### Testclient

I'd like to have a finer control of how my application works, take this endpoint as an example:

```python
@todo_route.post
asyc def create_todo(data: CreateTodo, repo: TodoRepo, bus: EventBus) -> Resp[Todo, status.Created]:
    todo =  Todo.from_data(CreateTodo)
    await repo.add(todo)
    awati bus.publish(TodoCreated.from_todo(todo))
    return todo
```

I'd like to test:

- the function `create_todo`, which requires all menually inject all three params and return a `Todo`
- the endpoint `todo_route.post` which requires only `CreateTodo` without dependencies, returns a json serialized `Todo` in bytes.
- the route `todo_route` with middlewares
- the app with everything
