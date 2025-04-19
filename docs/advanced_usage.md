# Advanced Usage



## Authentification


### Auth header

### Json Web Token

### OAuth


## Plugins & Param Processor

### Plugins

### Initialization

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
middleware can be bind to different route, for example `Throttle`

```python
# pseudo code
class ThrottleMiddleware:
    def __init__(self, app: Ignore[ASGIApp], redis: Redis):
        self.app = app
        self.redis = redis

    async def __call__(self, app):
        await self.redis.run_throttle_script
        await self.app

```

lihil accepts a factory to build your middleware, so that you can use di inside the factory, and it will perserve typing info as well. Anything callable that requires only one positonal argument can be a factory, which include most ASGI middleware classes.

```python
lihil.add_middleware(lambda app: app.graph.resolve(ThrottleMiddleware))
```

- Use it at your endpoints

```python
async def create_user(user_name: str, plugin: YourPlugin): ...
```
