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

or by inheriting `lihil.config.AppConfig` instance manually,

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

Note that, currently only `Form[bytes]` and `Form[DataModel]` is accepted, where DataModel is any subclass of `Struct`

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

- lazy analysis on endpoint, now dependencies declare in the endpoint won't be analyzed until lifespan event. this is for better analysis on dependencies, for example:

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

## version 0.1.14

### Fix

- fix a bug where if user defined a Route with path "/"(the root route), it will be ignored.

```python
from lihil import Route, Lihil
root = Route("/")
root.get(lambda : "root")

lhl = Lihil(routes=[root])

assert not lhl.root.endpoints
```

This is because the previously we always create a root route in lhl before including any other route.

and when we include the user created root route, it will be ignored by lihil.

- fix a bug where static route would replace an existing route instead of being added as a new route.

- fix a bug where if calling `Lihil.include_routes` with both parent route and child route would cause error.

### Improvements

- better repr for `Lihil`

- now user might add `headers` to `HttpException` and its subclass, it would be returned to the client

```python
@root.get
async def get_user():
    raise UserNotFoundError("user not found", headers={"error-id": "random-id"})
```

## version 0.1.14

### Feature

- register plugin by inheritance: now user might inherit from `PluginBase` and use is as metadata, example

```python
@lhl.get("/me")
async def read_users_me(
    token: Annotated[str, OAuth2PasswordFlow(token_url="token")],
):
    return token
```

where `OAuth2PasswordFlow` is a subclass of `PluginBase`

- `LocalClient.submit_form` for testing endpoint with form data.

```python
lc = LocalClient()
res = await lc.submit_form(
    form_ep, form_data={"username": "user", "password": "pass"}
)
```

## version 0.1.15

### Fix

- fix a bug where if `lifespan` is not provided and app starup fails, it will fail silently.

- fix a bug where if endponit returns non-stream response, media-type would be lost, no will include the media-type of first response.

### Features

- automatic generate oauth2-compatible access token based on user returns

```python
from lihil import Lihil, Payload, Route, field
from lihil.config import AppConfig, SecurityConfig
from lihil.auth.jwt import JWTAuth, JWTPayload
from lihil.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm

me = Route("me")
token = Route("token")


class UserPayload(JWTPayload):
    __jwt_claims__ = {"expires_in": 300}

    user_id: str = field(name="sub")


class User(Payload):
    name: str
    email: str


@me.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))
async def get_user(token: JWTAuth[UserPayload]) -> User:
    assert token.user_id == "user123"
    return User(name="user", email="user@email.com")


@token.post
async def create_token(credentials: OAuthLoginForm) -> JWTAuth[UserPayload]:
    assert credentials.username == "admin" and credentials.password == "admin"
    return UserPayload(user_id="user123")


lhl = Lihil[None](
    routes=[users, token],
    app_config=AppConfig(
        security=SecurityConfig(jwt_secret="mysecret", jwt_algorithms=["HS256"])
    ),
)
```

### Improvements

- No longer automatically drops resonse body when status code < 200 or in (204, 205, 304), instead, user should declare its return with `lihil.Empty`

## version 0.2.0

### improvements:

- upgrade ididi to 1.6.0

- now meta data of annotated type would be resolved in the order they appear(used to be reversed orderl).

```python
type MARK_ONE = Annotated[str, "ONE"]
type MARK_TWO = Annotated[MARK_ONE, "TWO"]
type MARK_THREE = Annotated[MARK_TWO, "THREE"]


def test_get_origin_pro_unpack_annotated_in_order():
    res = get_origin_pro(Annotated[str, 1, Annotated[str, 2, Annotated[str, 3]]])
    assert res == (str, [1, 2, 3])


def test_get_origin_pro_unpack_textalias_in_order():
    res = get_origin_pro(MARK_THREE)
    assert res == (str, ["ONE", "TWO", "THREE"])
```

This means that user now might override decoder by Annotated original param type with new custom decoder

```python
def decoder1(c: str) -> str: ...
def decoder2(c: str) -> str: ...


type ParamP1 = Annotated[Query[str], CustomDecoder(decoder1)]
type ParamP2 = Annotated[ParamP1, CustomDecoder(decoder2)]


def test_param_decoder_override(param_parser: ParamParser):
    r1 = param_parser.parse_param("test", ParamP1)[0]
    assert r1.decoder is decoder1

    r2 = param_parser.parse_param("test", ParamP2)[0]
    assert r2.decoder is decoder2
```

- now if `JWTAuth` fail to validate, raise `InvalidTokenError` with order status 401. This error would be displayed in swagger ui for endpoints that requires `auth_scheme`.

- making `lihil.auth` a top level package

- separate `Configuration` and `Properties`, rename `RouteConfig` to `RouteProps`, `EndpointConfig` to `EndpointProps`

- support `lihil.status` for `HTTPException` without `lihil.status.code`

```python
from lihil import HTTPException, status

## before
err = HTTPException(problem_status=status.code(status.NOT_FOUND))

## after
err = HTTPException(problem_status=status.NOT_FOUND)
assert err.status == 404
```

- `lihil.plugin.testclient.LocalClient` now has a new helper functions
  `make_endpoint` that receives a function and returns a endpoint.

```python
async def f() -> Resp[str, status.OK] | Resp[int | list[int], status.CREATED]: ...
lc = LocalClient()
ep = lc.make_endpoint(f)
```

### Fixes

- fix a bug where if config_file is None, config through cli arguments won't be read.

## version 0.2.1

### Improvements

- rename `JWToken` to `JWTAuth`, we might have `BasicAuth`, `DigestAuth` later

- refactor decoder for textual params, including header, query, path, etc.
  use msgspec.convert instead of msgspec.json.decode

### Fixes:

- now support multi value query & headers, declare your query | header param with non-textual sequence such as list, tuple, set and lihil would validate the param accordingly.

### Feature

- Single param constraint

## version 0.2.2

## Fixes

- fix a bug where command line arguments for security does not work

## improvements

- better help docs for config

```bash
uv run python -m docs.example --help

lihil application configuration

options:
  -h, --help            show this help message and exit
  --is_prod             Whether the current environment is production
  --version VERSION     Application version
  --max_thread_workers MAX_THREAD_WORKERS
                        Maximum number of thread workers
  --oas.oas_path OAS.OAS_PATH
                        Route path for OpenAPI JSON schema
  --oas.doc_path OAS.DOC_PATH
                        Route path for Swagger UI
  --oas.title OAS.TITLE
                        Title of your Swagger UI
  --oas.problem_path OAS.PROBLEM_PATH
                        Route path for problem page
  --oas.problem_title OAS.PROBLEM_TITLE
                        Title of your problem page
  --oas.version OAS.VERSION
                        Swagger UI version
  --server.host SERVER.HOST
                        Host address to bind to (e.g., '127.0.0.1')
  --server.port SERVER.PORT
                        Port number to listen on
  --server.workers SERVER.WORKERS
                        Number of worker processes
  --server.reload       Enable auto-reloading during development
  --server.root_path SERVER.ROOT_PATH
                        Root path to mount the app under (if behind a proxy)
  --security.jwt_secret SECURITY.JWT_SECRET
                        Secret key for encoding and decoding JWTs
  --security.jwt_algorithms SECURITY.JWT_ALGORITHMS
                        List of accepted JWT algorithms
```

- better typing support

now you might declare more complex type such as

```python
type Pair[K, V] = tuple[K, V]


async def get_user(p: Pair[int, float]): ...
```

- add `exclude_none`, `exclude_unset` to `Base.asdict`.

## Feature

- `AppConfig` is now a global singleton, and can be accessed anywhere via `lihil.config.get_config`

usage

```python
from lihil.config import get_config, AppConfig

assert isinstance(get_config(), AppConfig)
```

## version 0.2.3

### Fixex

- [x] `Route.sub` and `Lihil.sub` would avoid duplicate sub being added to route

```python

all_users = Route("users")

@all_users.sub("{user_id}").get
async def get_user(): ...

@all_users.sub("{user_id}").post
async def create_user(): ...
```

This used to result in two same `Route(f"users/{user_id}")` being added to `Route("users")`

- [x] fix a bug where the default lifespan of lihil would not emit "lifespan.shutdown" event

### Features

- [x] `Cookie` Param

```python
from lihil import Cookie

async def get_user(
    refresh_token: Annotated[Cookie[str, Literal["refresh-token"]], Meta(min_length=1)], user_id: Annotated[str, Meta(min_length=5)]
): ...
```

- [x] websocket

```python
from lihil import WebSocketRoute, WebSocket
ws_route = WebSocketRoute("web_socket/{session_id}")

async def ws_factory(ws: Ignore[WebSocket]) -> Ignore[AsyncResource[WebSocket]]:
    await ws.accept()
    yield ws
    await ws.close()

async def ws_handler(
    ws: Annotated[WebSocket, use(ws_factory, reuse=False)], session_id: str, max_users: int
):
    assert session_id == "session123" and max_users == 5
    await ws.send_text("Hello, world!")

ws_route.ws_handler(ws_handler)

lhl = Lihil[None]()
lhl.include_routes(ws_route)

client = TestClient(lhl)
with client:
    with client.websocket_connect(
        "/web_socket/session123?max_users=5"
    ) as websocket:
        data = websocket.receive_text()
        assert data == "Hello, world!"
```

the websocket usage is pretty close to regular route, except

- websocket handler can't have body param
- websocket only accepts get method

### Improvement

- [x] now lihil primitives might be used with function dependency for

```python
async def ws_factory(ws: Ignore[WebSocket]) -> Ignore[AsyncResource[WebSocket]]:
    await ws.accept()
    yield ws
    await ws.close()

async def ws_handler(
    ws: Annotated[WebSocket, use(ws_factory, reuse=False)], session_id: str, max_users: int
):
    assert session_id == "session123" and max_users == 5
    await ws.send_text("Hello, world!")
```

NOTE that for this to work, both `ws_handler` and `ws_factory` should name `WebSocket` with a same name, which is `ws` in this case.

- [x] now `lihil.use` would set "reuse" default to False

## version 0.2.4

A simple, daily maintainence patch, mainly for refactoring.

### Improvements

- [x] graph ignore lihil primitives(Request, Websocket, ...) by default

- [x] static response

now static response with non-generator returns would return `StaticResponse` instead.

### Refactors

- [x] No longer cache Route by path.

previously, instances of `Route` will be cached by their path

```python
assert Route("user") is Route("user")
```

This was for the sake of convenience, so that user do

```python
@Route("/user").get
def get_user(): ...

@Route("/user").post
def create_user(): ...
```

But the fundamental flaws of this design is that:

1. users might not expect this.
2. testing is harder.

- [x] specialized param meta

## version 0.2.5

- refactor signature attributes
- supports python version >= 3.10

### Improvements

1. separate `read_config` from `set_config`

### Fxies

- Fix a bug where if an exception happens in user provided lifespan(if there is one) before yield, it would not be raised and the app would continue to run

- Fix a bug where if a param is declared in dependency but not in endpoint function, request will fail.

### Refactor

- remove `PluginParam`

```python
async def authenticator(scheme: str, credentials: str)->Any:
    ...


@post
async def create_user(cred: Authorization[str, CustomDecoder]):
    ...
```

- [x] Removed param marks, such as `Body`, `Query`, `Path`, `Header`, `Cookie`, `Form`, `Use`.
- [x] Added `Param` for all param types, including `Body`, `Query`, `Path`, `Header`, `Cookie`, `Form`, etc.

Usage:

```python
from typing import Annotated
from lihil import Param

async def create_user(
    user_id: str,
    auth_token: Annotated[str, Param("header", alias="x-auth-token")],
    user_data: UserPayload,
    service: UserService
) -> Resp[str, 201]:
    ...
```

## version 0.2.6

### Fixes

- [x] fix a bug where if a header param is declared as a union of types, it would not be treated as a sequence type even if the union contains a sequence type.

```python
async def test_ep_with_multiple_value_header():
    lc = LocalClient()

    async def read_items(x_token: Annotated[list[str] | None, Param("header")] = None):
        return {"X-Token values": x_token}

    ep = lc.make_endpoint(read_items)
    resp = await lc.request(
        ep,
        method="GET",
        path="",
        multi_headers=[("x-token", "value1"), ("x-token", "value2")],
    )
    assert resp.status_code == 200
```

The above test would fail before this fix, as `x-token` is a union of list[str] and None, it would be treated as a str instead of list[str].

### Features

User now can combine `UploadFile` and `Form` to set constraints on files

```python
async def test_ep_requiring_upload_file_exceed_max_files(
    rusers: Route, lc: LocalClient
):

    async def get(
        req: Request, myfile: Annotated[UploadFile, Form(max_files=0)]
    ) -> Annotated[str, status.OK]:
        assert isinstance(myfile, UploadFile)
        return None

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

    file_content = b"Hello, this is test content!"  # Example file content
    filename = "test_file.txt"

    multipart_body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="myfile"; filename="{filename}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
        + file_content.decode()  # File content as string
        + f"\r\n--{boundary}--\r\n"
    ).encode("utf-8")

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    result = await lc.call_endpoint(ep, body=multipart_body, headers=headers)
    assert result.status_code == 422
    data = await result.json()
    assert data["detail"][0]["type"] == "InvalidFormError"
```

## version 0.2.7

- Features

- Plugin system

now user can add plugin in EndpointProps to route and endpoint.

Plugin Interface

```
class IPlugin(Protocol):
    async def __call__(
        self,
        graph: Graph,
        func: IFunc,
        sig: EndpointSignature[Any],
        /,
    ) -> IFunc: ...
```

API

```python
@route.get(plugins=[my_plugin])
async def create_user():
    ...
```

- PremierPlugin

```python
from lihil.plugins.premier import PremierPlugin, throttler, AsyncDefaultHandler
from lihil.plugins.testclient import LocalClient

async def test_throttling():
    async def hello():
        print("called the hello func")
        return "hello"

    lc = LocalClient()

    throttler.config(aiohandler=AsyncDefaultHandler())

    plugin = PremierPlugin(throttler)

    ep = await lc.make_endpoint(hello, plugins=[plugin.fix_window(1, 1)])

    await lc(ep)

    with pytest.raises(QuotaExceedsError):
        for _ in range(2):
            await lc(ep)
```

## version 0.2.8

- Refactor

- [x] remove `registry` and `listeners` from `Route`

- [x] merge props from `Route` and `Endpoint` instead of update

- [x] deduplicate plugins

```python
async def test_route_merge_endpoint_plugin():
    called: list[str] = []

    async def dummy_plugin(*args):
        called.append("plugin called")

    route = Route(props=EndpointProps(plugins=[dummy_plugin]))

    async def dummy_handler(): ...

    route.get(dummy_handler, plugins=[dummy_plugin])

    await route.setup()

    ep = route.get_endpoint(dummy_handler)

    # merged plugin from route and endpoint so we have two plugins
    assert ep.props.plugins == [dummy_plugin, dummy_plugin]

    # but only one plugin called since we deduplicate using id(plugin)
    assert called == ["plugin called"]
```

-[x] `Lihil(max_thread_workers=x)` would set max thread workers to x, this would be used in `Graph` and `Endpoint` for executing sync function in thread workers.

- Fixes

- [x] fix a bug where if lihil will not read config from cli upon initialization.

## version 0.2.9

- Features

  1. supbase integration(see doc for details)
     Code Example

```python
from supabase import AsyncClient

from lihil import Lihil
from lihil.config import AppConfig, lhl_get_config, lhl_read_config
from lihil.plugins.auth.supabase import signin_route_factory


class ProjectConfig(AppConfig, kw_only=True):
    SUPABASE_URL: str
    SUPABASE_API_KEY: str


def supabase_factory() -> AsyncClient:
    config = lhl_get_config(config_type=ProjectConfig)
    return AsyncClient(
        supabase_url=config.SUPABASE_URL, supabase_key=config.SUPABASE_API_KEY
    )


async def lifespan(app: Lihil):
    app.config = lhl_read_config(".env", config_type=ProjectConfig)
    app.graph.analyze(supabase_factory)
    app.include_routes(signin_route_factory(route_path="/login"))
    yield


lhl = Lihil(lifespan=lifespan)

if __name__ == "__main__":
    lhl.run(__file__)
```

2. ParamPack, when combine Structualred data type(msgspec.Struct, Typeddict, dataclass) with header, cookie, path, query param, would split the param collection into params.

- Improvements

  1. merge param meta
     These two params are equivalent

  ```python
  Annotated[str, Param("header"), Param(alias="x-auth-token"), Param(decoder=lambda x: x)]
  Annotated[str, Param("header", alias="x-auth-token", decoder=lambda x: x)]
  ```

  2. now for query, header, cookie param with sequence default value, such as list, would perform a deep copy operation to avoid changing mutable values.

  3. adding support for typeddict and dataclass

- Refactors

  - change AppConfig attribute names to uppercase
  - change JWTAuth to a plugin

- Fixes
  - Fix a bug where openapi doc would not recognize form body param and shows content-type as "application/json"

## version 0.2.10

- Features

    - [x] `Route.include_subroutes` that includes subroutes, works like fastapi `include_router`

    ```python
    def app_factory():
        lhl = Lihil()
        lhl.config = lhl_read_config(".env", config_type=ProjectConfig)
        lhl.graph.analyze(supabase_factory)
        root = Route("/api/v0")
        root.get(hello)
        root.include_subroutes(
            signin_route_factory(route_path="/login"),
            signup_route_factory(route_path="/signup"),
        )
        lhl.include_routes(root)
        return lhl


    if __name__ == "__main__":
        app_factory().run(__file__)
    ```

- Refactor:
    - [x] change Lihil.routes to variadic arguments, e.g.: `Lihil(routes=[r1, r2])` changes to `Lihil(r1, r2)`

## version 0.2.11


Features:

- [x] add `pydantic.BaseModel` as supported structured data types

- [x] add `hash_password` and `verify_password` to `lihil.plugins.auth.utils`

Improvements:

- [x] now `supabase` plugin is easier to use

```python
from lihil.plugins.auth.supabase import SupabaseConfig, signin_route_factory


async def lifespan(app: Lihil):
    app.config = lhl_read_config(
        ".env", config_type=SupabaseConfig
    )  # read config from .env file as convert it to `ProjectConfig` object.
    app.include_routes(signin_route_factory(route_path="/login"))
    yield
```

Fixes:
- [x] fix a bug where return value from `lihil.plugins.auth.supabase.signin_route_factory` can't be properly encoded as json.


## version 0.2.12

Improvements

- [x] supports more complicated pydantic type such as `list[BaseModel]`
- [x] add `Lihil.generate_oas` to generate an openapi schema for current routes.

## version 0.2.13

Fixes:

- [x] fix a bug introduced in 0.2.12 that would cause builtin routes(/docs, /problem_page) invisibile to users


## version 0.2.14

Improvements:

- [x] add `audience` and `issuer` to `jwt_auth_plugin.decode_plugin`, now user need to add `jwt_auth_plugin.decode_plugin` to plugin as `jwt_auth_plugin.decode_plugin()` :

```python
    @testroute.get(
        auth_scheme=OAuth2PasswordFlow(token_url="token"),
        plugins=[jwt_auth_plugin.decode_plugin()],
    )
    async def get_me(
        token: Annotated[UserProfile, JWTAuthParam],
    ) -> Annotated[Text, status.OK]:
        assert token.user_id == "1" and token.user_name == "2"
        return "ok"
```


Fixes:

- [x] fix a bug where swagger ui would show `Authorize` button even when there is no securitySchemes

- [x] fix a bug where swagger ui would always show single value param as required
