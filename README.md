# lihil

**lihil** [/ˈliːhaɪl/] is a performant, productive and professional web framework with a vision: making python the mainstream programming language for web development..


Lihil is 

- *Performant* multiple times faster than other python web framework 
- *Productive* strong typing supports and built-in solutions enable users to make their app ASAP.
- *professional* This framework follows industry best practices to deliver robust and scalable solutions: DDD, CQRS, MQ, Serverless, etc.


## Features

- Performant, excellently, one of the fastest web frameworks available in Python.
- Elegant, adheres to best practices while maintaining code clarity.
- Feature-rich, comes with a Django-like, vibrant ecosystem.
- Built-in support for messaging system. 


## Quick Start

```python
from lihil import Lihil, Text, HTTPException

lhl = Lihil()

@lhl.get
async def pingpong():
    return {"ping": "pong"}

@lhl.sub("/{king}").get
def kingkong(king: str) -> Text:
    return f"{king}, kong"


class VioletsAreBlue(HTTPException[str]):
    "I am a pythonista"


@lhl.get(errors=VioletsAreBlue)
async def roses_are_red():
    raise VioletsAreBlue("and so are you")

```

start a server, default to port 8000
```bash
lhl run
```

## Error Hanlding

use `catch` as decorator to register a error handler, error will be parsed as Problem Detail defined in RFC9457

use `route.get(errors=[UserNotFound])` to declare a endpoint response


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
