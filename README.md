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

@lhl.get
async def pingpong():
    return {"ping": "pong"}

@lhl.sub("/{king}").get
def kingkong(king: str) -> Text:
    return f"{king}, kong"

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
- init at middleware

plugin can be initialized and injected into middleware,
middleware can be bind to differernt route,
for example `Throttle`

- init each request
