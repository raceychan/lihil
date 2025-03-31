# CHANGELOG

## version 0.1.1

This is the very first version of lihil, but we already have a working version that users can play around with.

### Features

- core functionalities of an ASGI webserver, routing, http methods, `GET`, `POST`, `PUT`, `DELETE`
- ASGI middleware support
- various response and encoding support, json response, text response, stream response, etc.
- bulit-in json serialization/deserialization using `msgspec`
- `CustomEncoder` and `CustomDecoder` support
- Performant and powerful dependency injection using `ididi`
- Built-in message support, `EventBus` that enables user to publish events to multiple listeners.
- auto generated OpenAPI schemas and swagger web-ui documentation
- rfc-9457 problem details and problems web-ui documentation
- many other things, stay tuned to our docs!

## version 0.1.2

### Improvements

- `InvalidRequestErrors` is now a sublcass of `HTTPException`

### Fix

- fix a bug where `problem.__name__` is used for search param instead of `problem.__problem_type__`
- no longer import our experimental server by default

## version 0.1.3

### Fix

- fix a bug where if lifespan is not provided, callstack won't be built
- remove `loguru.logger` as dependency.

### Improvements

- `static` now works with `uvicorn`


## version 0.1.4

### Fix

- a quick fix for not catching HttpException when sub-exception is a generic exception


## version 0.1.5

### Feature

- User can now alter app behavior by assigning a config file

```python
lhl = Lihil(config_file="pyproject.toml")
```
Note: currently only toml file is supported

or by inheriting `lihil.config.AppConfig` instance menually,

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

### improvements

- now user can directly import `Body` from lihil

```python
from lihil import Body
```

## version 0.1.6

### Feature

- user can now override configuration with cli arguments.

example:

```python
python app.py --oas.title "New Title" --is_prod true
```

would override `AppConfig.oas.title` and `AppConfig.is_prod`.

this comes handy when for overriding configs that are differernt according to the deployment environment.

- add a test helper `Route.has_listener` to check if a listener is registered.

- `LocalClient.call_route`, a test helper for testing routes.

### Fix

- fix a bug with request param type being GenericAliasType

we did not handle GenericAliasType case and treat it as `Annotated` with `deannnotate`.

and we think if a type have less than 2 arguments then it is not `Annotated`,
but thats not the case with GenericAlias

- fix a bug with request param type optional type

we used to check if a type is union type by checking

```python
isinstance(type, UnionType)
```

However, for type hint like this

```python
a: int | None
```

it will be interpreted as `Optional`, which is a derived type of `Union`

- fix a bug where `CustomerDecoder` won't be use
previously whenever we deal with `Annotated[Path[int], ...]`

we treat it as `Path[int]` and ignore its metadatas, where decoder will be placed, this is now fixed as we detect and perserve the decoder before discarding the matadata.

- fix a bug where `Route.listen` will fail silently when listener does not match condition, meaning it has not type hint of derived event class.

Example:

```python
async def listen_nothing(event):
    ...

Rotue.listen(listen_nothing)
```

This would fail silently before this fix

- Fix a bug with `Lihil.static` where if content is instance of str, and content type is `text` it will still be encoded as json

## version 0.1.7

### Feature

#### `Lihil.run` (beta)

use `Lihil.run` instead of uvicorn.run so that user can pass command line arguments to `AppConfig`

```python
from lihil import Lihil

lihil = Lilhil()

if __name__ == "__main__":
    lhl.run(__file__)
```

#### ServerConfig

- `lihil.config.AppConfig.server`

```python
class ServerConfig(ConfigBase):
    host: str | None = None
    port: int | None = None
    workers: int | None = None
    reload: bool | None = None
    root_path: str | None = None
```

if set, these config will be passed to uvicorn

##### Usage

```bash
uv run python -m app --server.port=8005 --server.workers=4
```

```bash
INFO:     Uvicorn running on http://127.0.0.1:8005 (Press CTRL+C to quit)
INFO:     Started parent process [16243]
INFO:     Started server process [16245]
INFO:     Started server process [16247]
INFO:     Started server process [16246]
INFO:     Started server process [16248]
```

## version 0.1.8

### Improvements

- check if body is a subclass of `Struct` instead of `Payload`
- `Payload` is now frozen and gc-free by default.

### Fix

- fix a bug where when endpoint might endpoint having different graph as route

- fix a bug where if param type is a union of types return value would be None.

- fix a bug where a param type is a generic type then it will be treated as text type

```python
def _(a: dict[str, str]):
    ...
```

here a will be treated as:

```python
def _(a: str):
    ...
```

- fix a bug where if return type is Annotated with resp mark, it will always be encoded as json unless custom encoder is provided, for example:

```python
async def new_todo() -> Annotated[Text, "1"]:
    ...
```

before v0.1.8, here return value will be encoded as json.

same thing goes with Generator


```python
async def new_todo() -> Generator[Text, None, None]:
    ...
```


## version 0.1.9

### Improvements

`EventBus` can now be injected into event handlers as dependency

### Fix

fix a bug where `Envelopment.build_decoder` would return a decoder that only decodes None


## version 0.1.10

### Improvements

- Problem Page now has a new `View this as Json` button
- now prioritize param mark over param resolution rule

### Features

- user can now declare form data using `Form` in their endpoint.

```python
from lihil import Form, Resp



class UserInfo(Payload):
    name: str
    password: str

@Route("/token").post
async def post(login_form: Form[UserInfo]) -> Resp[Text, status.OK]:
    assert isinstance(login_form, UserInfo)
    return "ok"
```

Note that, currently only `Form[bytes]` and `Form[DataModel]` is accpeted, where DataModel is any subclass of `Struct`

- user can now declare `UploadFile` in their endpoint.

```python
from lihil import UploadFile

@Route("/upload").post
async def post(myfile: UploadFile) -> Resp[Text, 200]:
    file_path = f"/tmp/{myfile.filename}"  # Adjust the path as needed
    with open(file_path, "wb") as f:
        f.write(await myfile.read())
    return "ok"
```


## version 0.1.11

### Improvements

- now `add_middleware` will append new middleware to the tail of the call chain.
- add `middlewares: list[MiddlewareFactory[Any]] | None` param to the constructor of `Lihil` and `Route`, default to None
- add `MiddlewareBuildError`, which will be raised when calling middleware factory fail
- add `NotSupportedError` for usage not currently supported, such a multiple return params.
- add `InvalidParamTypeError` for invalid param type, such as `Literal[3.14]`


### Feat:

- add `Empty` to indicate where Response should be empty

```python
async def test_route_with_nested_empty_response():
    route = Route("empty")

    async def post_empty() -> Resp[Empty, status.NO_CONTENT]: ...

    route.post(post_empty)

    lc = LocalClient()

    ep = route.get_endpoint("POST")

    res = await lc.call_route(route, method="POST")
    assert res.status_code == 204
    assert await res.body() == b""
```

- add `Resolver` to lhl singleton, meaning that user can now inject `Graph`, `AsyncScope` in their endpoint.

example:

```python
from lihil import Route, LocalClient, use

async def test_ep_require_resolver(rusers: Route, lc: LocalClient):

    side_effect = []

    async def call_back() -> None:
        nonlocal side_effect
        side_effect.append(1)

    class Engine: ...

    @rusers.factory
    def get_engine() -> Engine:
        eng = Engine()
        yield eng

    async def get(
        user_id: str, engine: Engine, resolver: AsyncScope
    ) -> Resp[Text, status.OK]:
        resolver.register_exit_callback(call_back)
        return "ok"

    rusers.get(get)

    res = await lc.call_endpoint(rusers.get_endpoint("GET"), path_params={"user_id": "123"})
    assert res.status_code == 200
    assert side_effect == [1]
```


This is a powerful feature where user can define what will be called after leaving current scope.

note that only resource would require scope, unless specifically configured via endpoint config

- add `scoped` to endpoint config

```
from lihil import Route
from ididi import AsyncScope

class Engine: ...


@Route("users).get(scoped=True)
async def get_user(engine: Engine, resolver: AsyncScope):
    assert isinstance(resolver, AsyncScope)


@Route("users).post
async def create_user(engine: Engine, resolver: AsyncScope):
    assert not isinstance(resolver, AsyncScope) # here resolver is Graph since `Engine` is not scoped.
```

## version 0.1.12

This patch focuses on refactoring to improve code maintainence

### Improvements

- lazy analysis on endpoint, now dependencies declare in the endpoint won't be analyzed untill lifespan event. this is for better analysis on dependencies, for example:

```python

user_route = Route("user")

@user_route.factory
class Engine: ...

order_route = Route("order")

@order_route.get
async def get_order(engine: Engine):
    ...
```

before this change, when `get_order` is added to `order_route`, `Engine` will be recognized as a query param, as `Engine` is registered through `user_route`

- chain up middlewares after lifespan, this means that user might add middlewares inside lifespan function, the benefit of doing so is that user can use graph to resolve and manage complex dependencies (if the middleware need them to be built).


- add http methods `connect`, `trace` to `Lihil` and `Route`.
- add `endpoint_factory` param to `Route`, where user can provide a endpoint factory to generate custom endpoint.


### Fix

- fix a bug where `lihil.utils.typing.is_nontextual_sequence` would negate generic sequence type such as `list[int]`



## version 0.1.13


### Improvements

- lihil is now capable of handling more complex type variable

```python
type Base[T] = Annotated[T, 1]
type NewBase[T] = Annotated[Base[T], 2]
type AnotherBase[T, K] = Annotated[NewBase[T], K, 3]


def test_get_origin_nested():
    base = get_origin_pro(Base[str])
    assert base[0] == str and base[1] == [1]

    nbase = get_origin_pro(NewBase[str])
    assert nbase[0] == str and nbase[1] == [2, 1]

    res = get_origin_pro(AnotherBase[bytes | float, str] | list[int])
    assert res[0] == Union[bytes, float, list[int]]
    assert res[1] == [str, 3, 2, 1]
```

This is mainly to support user defined nested type alias.

For Example

```python
from lihil import Resp, status

type ProfileReturn = Resp[User, status.OK] | Resp[Order, status.CREATED] | Resp[
    None,
    status.NOT_ACCEPTABLE
    | Resp[int, status.INTERNAL_SERVER_ERROR]
    | Resp[str, status.LOOP_DETECTED]
    | Resp[list[int, status.INSUFFICIENT_STORAGE]],
]

@rprofile.post
async def profile(
    pid: str, q: int, user: User, engine: Engine
) -> ProfileReturn:
    return User(id=user.id, name=user.name, email=user.email)
```

### Features

- now supports multiple responses

```python
@rprofile.post
async def profile(
    pid: str, q: int, user: User, engine: Engine
) -> Resp[User, status.OK] | Resp[Order, status.CREATED]:
    return User(id=user.id, name=user.name, email=user.email)
```

now openapi docs would show that `profile` returns `User` with `200`, `Order` with `201`


- `PluginProvider`, use might now provide customized mark

```python
from lihil import Request, Resolver

type Cached[T] = Annotated[T, param_mark("cached")]


class CachedProvider:
    def load(self, request: Request, resolver: Resolver) -> str:
        return "cached"

    def parse(self, name: str, type_: type, default, annotation, param_meta)->PluginParam[str]:
        return PluginParam(type_=type_, name=name, loader=self.load)


def test_param_provider(param_parser: ParamParser):
    provider = CachedProvider()
    param_parser.register_provider(Cached[str], provider)

    param = param_parser.parse_param("data", Cached[str])[0]
    assert isinstance(param, PluginParam)
    assert param.type_ == str
```
