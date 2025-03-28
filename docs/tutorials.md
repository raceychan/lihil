# Tutorial

## Basics

### Enpoint

An `endpoint` is the most atomic ASGI component in `lihil`, registered under `Route` with `Route.{http method}`, such as `Route.get`. It defines how clients interact with the resource exposed by the `Route`.

In the [ASGI callchain](./minicourse.md) the `endpoint` is typically at the end.

Let's start with a function that creates a `User` in database.

#### Expose a function as an endpoint

**`app/users/api.py`**

```python
from msgspec import Struct
from sqlalchemy.ext.asyncio import AsyncEngine
from .users.db import user_sql

class UserDB(UserData):
    user_id: str

def get_engine() -> AsyncEngine:
    return AsyncEngine()

async def create_user(user: UserData, engine: AsyncEngine) -> UserDB:
    user_id = str(uuid4())
    sql = user_sql(user=user, id_=user_id)
    async with engine.begin() as conn:
        await conn.execute(sql)
    return UserDB.from_user(user, id=user_id)
```

To expose this function as an endpoint:


```python
from lihil import Route

users_route = Route("/users")
users_route.factory(get_engine)
users_route.post(create_user)
```

With just three lines, we:

1. Create a Route with the path "/users".
2. Register `AsyncEngine` as a dependency, using `get_engine` as its factory.
3. Register create_user as the POST endpoint.


You might also use python decorator syntax to register an endpoint

```python
users_route = Route("/users")

@users_route.post
async def create_user(): ...
```


#### Declare endpoint meta using marks

Often you would like to change status code, or content type, to do so, you can use one or a combination of several `return marks`. for example, to change stauts code:

```python
from lihil import Resp, status

async def create_user(user: UserData, engine: Engine) -> Resp[UserDB, status.Created]:
    ...
```

Now `create_user` would return a status code `201`, instead of the default `200`.

##### Return Marks

There are several other return marks you might want to use:

- `Json[T]` for response with content-type `application/json`, the default case
- `Text` for response with content-type `text/plain`
- `HTML` for response with content-type `text/html`
- `Empty` for empty response

**Compound Case**

- `Resp[T, 200]` for response with status code `200`. where `T` can be anything json serializable, or another return mark.

for instance, in the `create_user` example, we use `Resp[UserDB, status.Created]` to declare our return type, here `T` is `UserDB`.

by default, the return convert is json-serialized, so that it is equiavlent to `Resp[Json[UserDB], status.Created]`.

if you would like to return a response with content type `text/html`, you might use `HTML`

```python
async def hello() -> HTML:
    return "<p>hello, world!</p>"
```

##### Return Union

it is valid to return union of multiple types, they will be shown as `anyOf` schemas in the open api specification.

```python
async def create_user() -> User | TemporaryUser: ...
```

#### Param Parsing & Dependency Injection

You can also use marks provide meta data for your params. for example:

```python
from lihil import use, Ignore
from typing import Annotated, NewType
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

async def get_conn(engine: AsyncEngine) -> AsyncConnection:
    async with engine.begin() as conn:
        yield conn

UserID = NewType("UserID", str)

def user_id_factory() -> UserID:
    return UserID(str(uuid4()))

async def create_user(
    user: UserData, user_id: UserID, conn: AsyncConnection
) -> Resp[UserDB, stauts.Created]:

    sql = user_sql(user=user, id_=user_id)
    await conn.execute(sql)
    return UserDB.from_user(user, id=user_id)

users_route.factory(get_conn)
users_route.factory(user_id_factory, reuse=False)
```

Here,

1. `user_id` will be created by `user_id_factory` and return a uuid in str.
2. `conn` will be created by `get_conn` and return an instance of `AsyncConnection`, where the the connection will be returned to engine after request.
3. `UserDB` will be json-serialized, and return a response with content-type being `application/json`, status code being `201`.


##### Param Marks

- `Query` for query param, the default case
- `Path` for path param
- `Header` for header param
- `Body` for body param
- `Form` for body param with content type `multipart/from-data`
- `Use` for dependency

##### Param Parsing Rules

if a param is not declared with any param mark, the following rule would apply to parse it:

- if the param name appears in route path, it is interpreted as a path param.
- if the param type is a subclass of `msgspec.Struct`, it is interpreted as a body param.
- if the param type is registered in the route graph, or is a lihil-builtin type, it will be interpered as a dependency and will be resolved by lihil
- otherise, it is interpreted as a query param.

Example:

```python
from lihil import Route, Payload, Use, EventBus

user_route = Route("/users/{user_id}")

class UserUpdate(Payload): ...
class Engine: ...
class Cache: ...

user_route.factory(Cache)

@user_route.put
async def update_user(user_id: str, engine: Use[Engine], cache: Cache, bus: EventBus):
    return "ok"
```

In this example:

- `user_id` appears in the route path, so it is a path param
- `engine` is annotated with the `Use` mark, so it is a dependency
- `cache` is registered in the user_route, so it is also a dependency
- `bus` is a lihil-builtin type, it is therefore a dependency as well.

Only `user_id` needs to be provided by the client request, rest will be resolved by lihil.

Since return param is not declared, `"ok"` will be serialized as json `'"ok"'`, status code will be `200`.

#### Data validation and Custom Encoder/Decoder

lihil provide you data validation functionalities out of the box using msgspec, you can also use your own customized encoder/decoder for request params and function return.

To use them, annotate your param type with `CustomDecoder` and your return type with `CustomEncoder`

```python
from lihil.di import CustomEncoder, CustomDecoder

user_route = @Route(/users/{user_id})

async def get_user(
    user_id: Annotated[MyUserID, CustomDecoder(decode_user_id)]
) -> Annotated[MyUserId, CustomEncoder(encode_user_id)]:
    return user_id
```

```python
def decoder[T](param: str | bytes) -> T: ...
```

- `decoder` should expect a single param with type either `str`, for non-body param, or `bytes`, for body param, and returns required param type, in the `decode_user_id` case, it is `str`.

```python
def encoder[T](param: T) -> bytes: ...
```

- `encoder` should expect a single param with any type that the endpoint function returns, in the `encode_user_id` case, it is `str`, and returns bytes.


#### Configuring your endpoint

```python
@router.get(errors=[UserNotFoundError, UserInactiveError])
async get_user(user_id: str): ...
```

Endpoint can be configured with these options:

```python
errors: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]]
"""Errors that might be raised from the current `endpoint`. These will be treated as responses and displayed in OpenAPI documentation."""

in_schema: bool
"""Whether to include this `endpoint` in the OpenAPI documentation."""

to_thread: bool
"""Whether this `endpoint` should run in a separate thread. Only applies to synchronous functions."""

scoped: Literal[True] | None
"""Whether the current `endpoint` should be scoped."""
```

- `scoped`: if an endpoint requires any dependency that is an async context manager, or its factory returns an async generator, the endpoint would be scoped, and setting scoped to None won't change that, however, for an endpoint that is not scoped, setting `scoped=True` would make it scoped.


### Route

When you define a route, you expose a resource through a specific **path** that clients can request. you then add an `Endpoint` on the route to determin what clients can do with the resource.

Take url `https://dontclickme.com/users` as an example, path `/users` would locate resource `users`.

#### Defining an route

```python
from lihil import Route

users_route = Route("/users")
```

If you have existing `lihil.Graph` and `lihil.MessageRegistry` that you would like to use, put then in the route constructor.

This is useful when, say if you have keep dependencies and event listeners in separate files, example:

```python
from project.users.deps import user_graph
from project.users.listeners import user_eventregistry

user_route = Route(graph=uesr_graph, registry=user_eventregistry)
```

You might also add middlewares to route if you want the middlewares only take effect in the current route.

##### register endpoint to an route.

In previous dicussion, we expose `create_user` as an endpoint for `POST` request of `users_route`.
we can also declare other http methods with similar syntax, this includes:

- `GET`
- `POST`
- `HEAD`
- `OPTIONS`
- `TRACE`
- `PUT`
- `DELETE`
- `PATCH`
- `CONNECT`

This means that an route can have 0-9 endpoints.

to expose a function for multiple http methods

- apply multiple decorators to the function

- or, equivalently, use `Route.add_endpoint`

```python

users_route.add_endpoint("GET", "POST", ...,  create_user)
```

#### Defining an sub-route

In previous discussion, we created a route for `users`, a collection of the user resource,
to expose an specific user resource,

```python
user_route = users_route.sub("{user_id}")

@user_route.get
async def get_user(user_id: str, limit: int = 1): ...
```

Here,
we define a sub route of `users_route`, when we include an route into our `Lihil`, all of its sub-routes will also be included recursively.

Route are unique to path, thus, you might call it constructor with same path multiple times.

```python
@users_route.sub("{user_id}").get
async def get_user(user_id: str, limit: int = 1): ...

@users_route.sub("{user_id}").put
async def update_user(data: UserUpdate): ...
```

here both `get_user` and `update_user` are under the same route.

#### The root route

an route with path `/` is the root route, if not provided, root route is created with `Lihil` by default, anything registered via `Lihil.{http method}` is the under the root route.

### Middlewares

Both `Lihil` and `Route` has `add_middleware` API that accept one, or a sequence of `MiddlewareFactory`.

a `MiddlewareFactory` is a callable that receives one positional argument of type `ASGIApp` and returns a `ASGIApp`. for example:

```python
# This piece of code is for demonstration only.

def tracingmw_factory(next_app: ASGIApp) -> ASGIApp:
    async def tracemw(scope, receive, send):
        scope["trace_id"] = str(uuid.uuid4())
        await next_app(scope, receive, send)
    return trace_mw
```

lihil uses starlette internally, you can directly import middlewares from starlette, for example:

```python
from starlette.middleware.cors import CORSSMiddleware

lhl = Lihil(middlewares=[lambda app: CORSMiddleware(app, add_methods="*")])
```

for complex middleware that require many external dependencies, you might to construct them inside lifespan.

## Config Your App

You can alter app behavior by `lihil.config.AppConfig`

### via config file

```python
lhl = Lihil(config_file="pyproject.toml")
```

This will look for `tool.lihil` table in the `pyproject.toml` file
extra/unkown keys will be forbidden to help prevent misconfiging

Note: currently only toml file is supported

### build `lihil.config.AppConfig` instance menually

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

![roses_are_red](./images/roses_are_red_link.png)

click url under `External documentation` tab

we will see the detailed problem page

![problem page](./images/roses_are_red_problempage.png)

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

## Message System

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


async def listen_create(created: TodoCreated, ctx):
    assert created.name
    assert created.content


async def listen_twice(created: TodoCreated, ctx):
    assert created.name
    assert created.content


bus_route = Route("/bus", listeners=[listen_create, listen_twice])


@bus_route.post
async def create_todo(name: str, content: str, bus: EventBus) -> Resp[None, status.OK]:
    await bus.publish(TodoCreated(name, content))
```

An event can have multiple event handlers, they will be called in sequence, config your `BusTerminal` with `publisher` then inject it to `Lihil`.

- An event handler can have as many dependencies as you want, but it should at least contain two params: a sub type of `Event`, and a sub type of `MessageContext`.

- if a handler is reigstered with a parent event, it will listen to all of its sub event.
for example,

- a handler that listens to `UserEvent`, will also be called when `UserCreated(UserEvent)`, `UserDeleted(UserEvent)` event is published/emitted.

- you can also publish event during event handling, to do so, declare one of your dependency as `EventBus`,

```python
async def listen_create(created: TodoCreated, _: Any, bus: EventBus):
    if is_expired(created.created_at):
        event = TodoExpired.from_event(created)
        await bus.publish(event)
```

### DI (dependency injection)

lihil uses ididi(https://lihil.cc/ididi) for dependency injection.


#### Usage in lihil

#### register a dependency with a route

If a dependency is registered with any route, it will be available in every route included in `Lihil`.

```python
class Engine: ...
def get_engine() -> Engine: ...

user_route = Route("/user")
user_route.add_nodes(get_engine) # register Engine as a dependency in user_route

order_route = Route("/order") # order will use `get_engine` to resolve `Engine` as well.

lhl = Lihil(routes=[user_route, order_route])
```

- use `Route.factory` to add a dependency, or `Route.add_nodes` to add many dependencies.
- It is recommended to register dependency where you use them, but you can register them to any route if you want.
- You might create a `ididi.Graph` first, register dependencies with it, then inject it into any route.

#### Declare dependency with endpoint signature

If you would like to declare dependencies directly in your endpoint function:
(as opposed to register with route)

##### Use `lihil.Use` mark to declare a class as a dependency.

```python
route = Route("/users")

@route.get
async def get_user(engine: Use[Engine]) : ...
```

##### Use `typing.Annotated[T, use(Callable[..., T]])` to declare a factory in your endpoint

```python
from lihil import use

@route.get
async def get_user(engine: Annotated[Engine, use(get_engine)]) : ...
```

##### Use `Ignore` in return annotation to declare a function dependencies

You can create function as dependency by `Annotated[Any, use(your_function)]`. Do note that you will need to annotate your dependency function return type with `Ignore` like this

```python
async def get_user(token: UserToken) -> Ignore[User]: ...
```

#### Tehcnical details

- If your factory function is a generator(function that contains `yield` keyword), it will be treated as `scoped`, meaning that it will be created before your endpoint function and destoried after. you can use this to achieve business purpose via clients that offer `atomic operation`, such as database connection.


- if your function is a sync generator, it will be solved within a separate thread.

- all graph will eventually merged into the main graph holding by `Lihil`, which means that, if you register a dependency with a factory in route `A`, the same factory can be used in every other route if it is required.

#### Ididi cheatsheet

This cheatsheet is designed to give you a quick glance at some of the basic usages of ididi.

```python
from ididi import Graph, Resolver, Ignore

class Base:
    def __init__(self, source: str="class"):
        self.source = source

class CTX(Base):
    def __init__(self, source: str="class"):
        super().__init__(source)
        self.status = "init"
    async def __aenter__(self):
        self.status = "started"
        return self
    async def __aexit__(self, *args):
        self.status = "closed"

class Engine(Base): ...

class Connection(CTX):
    def __init__(self, engine: Engine):
        super().__init__()
        self.engine = engine

def get_engine() -> Engine:
    return Engine("factory")

async def get_conn(engine: Engine) -> Connection:
    async with Connection(engine) as conn:
        yield conn

async def func_dep(engine: Engine, conn: Connection) -> Ignore[int]:
    return 69

async def test_ididi_cheatsheet():
    dg = Graph()
    assert isinstance(dg, Resolver)

    engine = dg.resolve(Engine)  # resolve a class
    assert isinstance(engine, Engine) and engine.source == "class"

    faq_engine = dg.resolve(get_engine)  # resolve a factory function of a class
    assert isinstance(faq_engine, Engine) and faq_engine.source == "factory"

    side_effect: list[str] = []
    assert not side_effect

    async with dg.ascope() as ascope:
        ascope.register_exit_callback(random_callback)
        # register a callback to be called when scope is exited
        assert isinstance(ascope, Resolver)
        # NOTE: scopes are also resolvers, thus can have sub-scope
        conn = await ascope.aresolve(get_conn)
        # generator function will be transformed into context manager and can only be resolved within scope.
        assert isinstance(conn, Connection)
        assert conn.status == "started"
        # context manager is entered when scoped is entered.
        res = await ascope.aresolve(func_dep)
        assert res == 69
        # function dependencies are also supported

    assert conn.status == "closed"
    # context manager is exited when scope is exited.
    assert side_effect[0] == "callbacked"
    # registered callback will aslo be called.
```


## Plugins

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

```

lihil accepts a factory to build your middleware, so that you can use di inside the factory, and it will perserve typing info as well. anything callble that requires only one positonal argument can be a factory, which include most ASGI middleware classes.

```python
lihil.add_middleware(lambda app: app.graph.resolve(ThrottleMiddleware))
```

- Use it at your endpoints

```python
async def create_user(user_name: str, plugin: YourPlugin): ...
```

### Testing

Lihil provide you two technques for testing, `TestClient` and `LocalClient`

#### `TestClient`

`TestClient` provide you something that is close to menually constructing a request as client and post it to your server.

For integration testing where each request should go through every part of your application, `TestClient` keep your test close to user behavior.

However, if you want something less verbose and with smaller granularity, you can check out `LocalClient`

#### `LocalClient`

`LocalClient` is more a test helper than a full-fledged request client as opposed to `TestClient`, you might use it to call `Lihil` instance, `Route`, and `Endpoint` locally in a fast and ergonomic manner.

```python
from lihil import LocalClient

...TBC
```

## openapi docs

default ot `/docs`, change it via `AppConfig.oas`

## problem page

default to `/problems`, change it via `AppConfig.oas`

### What else you would like to know?

Have not found what you are looking for? please let us know by posting in the discussion.
