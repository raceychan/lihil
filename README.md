# lihil

**lihil** [/ˈliːhaɪl/] is a performant, productive and professional web framework with a vision: making python the mainstream programming language for web development..

Lihil is

- *Performant* 1-x faster than other asgi frameworks in most benchmarks.
- *Productive* strong typing supports and built-in solutions enable users to make their app ASAP.
- *professional* This framework follows industry best practices to deliver robust and scalable solutions: DDD, CQRS, MQ, Serverless, etc.

## Features

- **Advanced dependency injection**, inject params, resources, plugins, extremly powerful and fast.
- **OpenAPI docs** and json schema automatically generated with accurate type information, union type, json examples, problem detail(RFC-9457) and more.
- **Great Testability**, test at every level, your endpoint function, endpoint, route, middleware, application, everything is designed to be **testable**.

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

stream_route = Route("stream")

@stream_route
async def stream() -> Stream:
    const = ["hello", "world"]
    for c in const:
        yield c
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
