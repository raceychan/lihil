import uuid
from types import GenericAlias, UnionType
from typing import Annotated, Any, Literal

import pytest
from ididi import AsyncScope, Graph, Ignore, use
from starlette.requests import Request

from lihil import (
    Cookie,
    Empty,
    Form,
    Header,
    Json,
    Meta,
    Payload,
    Query,
    Request,
    Resolver,
    Resp,
    Route,
    Stream,
    Text,
    UploadFile,
    Use,
    field,
    status,
)
from lihil.interface import CustomDecoder
from lihil.auth.jwt import JWTAuth, JWTPayload, jwt_decoder_factory
from lihil.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm
from lihil.config import AppConfig, SecurityConfig
from lihil.errors import (
    InvalidParamTypeError,
    MissingDependencyError,
    NotSupportedError,
    StatusConflictError,
)
from lihil.plugins.registry import PluginBase, PluginParam
from lihil.plugins.testclient import LocalClient
from lihil.utils.threading import async_wrapper
from lihil.utils.typing import is_nontextual_sequence


class User(Payload, kw_only=True):
    id: int
    name: str
    email: str


# class Engine: ...


@pytest.fixture
def rusers() -> Route:
    return Route("users/{user_id}")


@pytest.fixture
def testroute() -> Route:
    return Route("test")


@pytest.fixture
def lc() -> LocalClient:
    return LocalClient()


def add_q(q: str, user_id: str) -> Ignore[str]:
    return q


async def create_user(
    user: User,
    req: Request,
    user_id: str,
    func_dep: Annotated[str, use(add_q)],
) -> Resp[Json[User], status.CREATED]:
    return User(id=user.id, name=user.name, email=user.email)


def test_return_status(rusers: Route):
    rusers.post(create_user)
    ep = rusers.get_endpoint(create_user)
    ep.setup()
    assert "q" in ep.sig.query_params
    assert "func_dep" in ep.sig.dependencies
    assert "user_id" in ep.sig.path_params

    ep_ret = ep.sig.return_params[201]
    assert ep_ret.type_ is User


def test_status_conflict(rusers: Route):

    async def get_user(
        user_id: str,
    ) -> Annotated[Resp[str, status.NO_CONTENT], "hello"]:
        return "hello"

    rusers.get(get_user)
    with pytest.raises(StatusConflictError):
        ep = rusers.get_endpoint(get_user)
        ep.setup()


def test_annotated_generic(rusers: Route):

    async def update_user(user_id: str) -> Annotated[dict[str, str], "aloha"]: ...

    rusers.put(update_user)
    ep = rusers.get_endpoint(update_user)
    ep.setup()
    repr(ep)
    assert ep.sig.return_params[200].type_ == dict[str, str]


def sync_func():
    return "ok"


async def test_async_wrapper():
    awrapped = async_wrapper(sync_func)
    assert await awrapped() == "ok"


async def test_async_wrapper_dummy():
    awrapped = async_wrapper(sync_func, threaded=False)
    assert await awrapped() == "ok"


async def test_ep_raise_httpexc():
    client = LocalClient()

    class UserNotFound(Exception): ...

    async def update_user(user_id: str) -> Annotated[dict[str, str], "aloha"]:
        raise UserNotFound()

    rusers = Route("users/{user_id}")
    rusers.put(update_user)

    rusers.get_endpoint(update_user)
    with pytest.raises(UserNotFound):
        await client.call_route(rusers, method="PUT", path_params=dict(user_id="5"))


async def test_sync_generator_endpoint():
    """Test an endpoint that returns a sync generator"""

    def stream_data() -> Stream[str]:
        """Return a stream of text data"""
        yield "Hello, "
        yield "World!"
        yield " This "
        yield "is "
        yield "a "
        yield "test."

    client = LocalClient()

    # Make the request
    route = Route("/stream")
    route.get(stream_data)

    ep = route.get_endpoint("GET")
    response = await client.call_endpoint(ep)

    # Check response status
    assert response.status_code == 200

    # Check content type
    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    ans = ""

    async for res in response.stream():
        ans += res.decode()

    # Check the full response content
    assert ans == "Hello, World! This is a test."


async def test_endpoint_return_agen(rusers: Route, lc: LocalClient):
    async def get():
        yield

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    await lc.call_endpoint(ep)


async def test_scoped_endpoint(rusers: Route, lc: LocalClient):
    class Engine: ...

    def get_engine() -> Engine:
        yield Engine()

    rusers.factory(get_engine)

    async def get(engine: Engine):
        yield

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    await lc.call_endpoint(ep)


async def test_ep_drop_body(rusers: Route, lc: LocalClient):

    async def get() -> Resp[Empty, 400]:
        return "asdf"

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    res = await lc.call_endpoint(ep)

    assert res.status_code == 400
    assert await res.body() == b""


async def test_ep_requiring_form(rusers: Route, lc: LocalClient):

    class UserInfo(Payload):
        username: str
        email: str

    async def get(req: Request, fm: Form[UserInfo]) -> Resp[str, status.OK]:
        return fm

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

    # Correctly formatted multipart body
    multipart_data = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="username"\r\n\r\n'
        f"john_doe\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="email"\r\n\r\n'
        f"john.doe@example.com\r\n"
        f"--{boundary}--\r\n"
    ).encode(
        "utf-8"
    )  # Convert to bytes

    # Content-Type header
    content_type = f"multipart/form-data; boundary={boundary}"

    res = await lc.call_endpoint(
        ep,
        body=multipart_data,
        headers={f"content-type": content_type},
    )
    assert res.status_code == 200
    assert res


async def test_ep_requiring_missing_param(rusers: Route, lc: LocalClient):

    class UserInfo(Payload):
        username: str
        email: str

    async def get(req: Request, fm: Form[UserInfo]) -> Resp[str, 200]:
        return fm

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

    # Correctly formatted multipart body
    multipart_data = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="username"\r\n\r\n'
        f"john_doe\r\n"
        f"--{boundary}--\r\n"
    ).encode(
        "utf-8"
    )  # Convert to bytes

    # Content-Type header
    content_type = f"multipart/form-data; boundary={boundary}"

    res = await lc.call_endpoint(
        ep,
        body=multipart_data,
        headers={f"content-type": content_type},
    )
    assert res.status_code == 422
    body = await res.body()
    assert b"invalid-request-errors" in body


async def test_ep_requiring_upload_file(rusers: Route, lc: LocalClient):

    class UserInfo(Payload):
        username: str
        email: str

    async def get(req: Request, myfile: UploadFile) -> Resp[str, 200]:
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
    assert result.status_code == 200


async def test_ep_requiring_upload_file_fail(rusers: Route, lc: LocalClient):
    async def get(req: Request, myfile: UploadFile) -> Resp[str, 200]:
        return None

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    result = await lc.call_endpoint(ep)
    assert result.status_code == 422


async def test_ep_requiring_file_bytse(rusers: Route, lc: LocalClient):
    async def get(by_form: Form[bytes]) -> Resp[Text, 200]:
        assert isinstance(by_form, bytes)
        return "ok"

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

    # Correctly formatted multipart body
    multipart_data = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="username"\r\n\r\n'
        f"john_doe\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="email"\r\n\r\n'
        f"john.doe@example.com\r\n"
        f"--{boundary}--\r\n"
    ).encode(
        "utf-8"
    )  # Convert to bytes

    # Content-Type header
    content_type = f"multipart/form-data; boundary={boundary}"

    res = await lc.call_endpoint(
        ep,
        body=multipart_data,
        headers={f"content-type": content_type},
    )
    assert await res.text() == "ok"
    assert res.status_code == 200


async def test_ep_requiring_form_invalid_type(rusers: Route, lc: LocalClient):
    async def get(by_form: Form[list[int]]) -> Resp[Text, 200]:
        assert isinstance(by_form, bytes)
        return "ok"

    rusers.get(get)
    with pytest.raises(NotSupportedError):
        rusers.get_endpoint("GET").setup()


async def test_ep_requiring_form_sequence_type(rusers: Route, lc: LocalClient):
    class UserInfo(Payload):
        name: str
        phones: list[str]

    async def get(by_form: Form[UserInfo]) -> Resp[Text, status.OK]:
        assert isinstance(by_form, UserInfo)
        return "ok"

    rusers.get(get)


async def test_ep_mark_override_others(rusers: Route, lc: LocalClient):
    class UserInfo(Payload):
        name: str
        phones: list[str]

    async def get(user_id: Query[UserInfo]) -> Resp[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    ep.setup()
    assert ep.sig.query_params
    assert not ep.sig.path_params


async def test_ep_with_random_annoated_query(rusers: Route, lc: LocalClient):

    async def get(aloha: Annotated[int, "aloha"]) -> Resp[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    ep.setup()
    assert ep.sig.query_params
    assert "aloha" in ep.sig.query_params
    assert ep.sig.query_params["aloha"].type_ is int


async def test_ep_with_random_annoated_path1(rusers: Route, lc: LocalClient):

    async def get(user_id: Annotated[int, "aloha"]) -> Resp[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    ep.setup()
    assert ep.sig.path_params
    assert "user_id" in ep.sig.path_params
    assert ep.sig.path_params["user_id"].type_ is int


async def test_ep_with_random_annoated_path2(rusers: Route, lc: LocalClient):
    class UserInfo(Payload):
        name: str
        phones: list[str]

    async def get(user: Annotated[UserInfo, "aloha"]) -> Resp[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    ep.setup()
    assert ep.sig.body_param
    assert ep.sig.body_param[1].type_ is UserInfo


async def test_ep_require_resolver(rusers: Route, lc: LocalClient):

    side_effect: list[int] = []

    async def call_back() -> Ignore[None]:
        nonlocal side_effect
        side_effect.append(1)

    class Engine: ...

    async def get(
        user_id: str, engine: Engine, resolver: Graph
    ) -> Resp[Text, status.OK]:
        await resolver.aresolve(call_back)
        return "ok"

    rusers.factory(Engine)
    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    res = await lc.call_endpoint(ep, path_params={"user_id": "123"})
    assert res.status_code == 200
    assert side_effect == [1]


async def test_config_nonscoped_ep_to_be_scoped(rusers: Route, lc: LocalClient):
    class Engine: ...

    async def get(
        user_id: str, engine: Use[Engine], resolver: AsyncScope
    ) -> Resp[Text, status.OK]:
        with pytest.raises(AssertionError):
            assert isinstance(resolver, AsyncScope)
        return "ok"

    rusers.get(get)
    res = await lc.call_endpoint(
        rusers.get_endpoint("GET"), path_params={"user_id": "123"}
    )

    text = await res.text()
    assert text == "ok"

    async def post(
        user_id: str, engine: Use[Engine], resolver: AsyncScope
    ) -> Resp[Text, status.OK]:
        assert isinstance(resolver, AsyncScope)
        return "ok"

    rusers.post(post, scoped=True)
    res = await lc.call_endpoint(
        rusers.get_endpoint("POST"), path_params={"user_id": "123"}
    )

    text = await res.text()
    assert text == "ok"


type GET_RESP = Resp[Text, status.OK]


async def test_endpoint_with_resp_alias(rusers: Route, lc: LocalClient):

    async def get(user_id: str) -> GET_RESP:
        return "ok"

    rusers.get(get)
    res = await lc.call_endpoint(
        rusers.get_endpoint("GET"), path_params={"user_id": "123"}
    )

    text = await res.text()
    assert text == "ok"


class UserProfile(JWTPayload):
    __jwt_claims__ = {"expires_in": 3600}

    user_id: str = field(name="sub")
    user_name: str


async def test_endpoint_returns_jwt_payload(testroute: Route, lc: LocalClient):

    async def get_token(form: OAuthLoginForm) -> JWTAuth[UserProfile]:
        return UserProfile(user_id="1", user_name=form.username)

    testroute.post(get_token)

    ep = testroute.get_endpoint(get_token)

    testroute.app_config = AppConfig(
        security=SecurityConfig(jwt_secret="mysecret", jwt_algorithms=["HS256"])
    )
    ep.setup()

    res = await lc.submit_form(
        ep, form_data={"username": "user", "password": "pasword"}
    )

    token = await res.json()

    decoder = jwt_decoder_factory(
        secret="mysecret", algorithms=["HS256"], payload_type=UserProfile
    )

    content = f"{token["token_type"].capitalize()} {token["access_token"]}"

    payload = decoder(content)
    assert isinstance(payload, UserProfile)


async def test_oauth2_not_plugin():

    async def get_user(token: Header[str, Literal["Authorization"]]): ...

    route = Route("me")
    route.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))(get_user)

    ep = route.get_endpoint("GET")
    ep.setup()

    pg = ep.sig.plugins
    assert not pg


async def test_endpoint_with_jwt_decode_fail(testroute: Route, lc: LocalClient):
    async def get_me(token: JWTAuth[UserProfile]):
        assert isinstance(token, UserProfile)

    testroute.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))(get_me)

    testroute.app_config = AppConfig(
        security=SecurityConfig(jwt_secret="mysecret", jwt_algorithms=["HS256"])
    )

    ep = testroute.get_endpoint(get_me)
    ep.setup()

    res = await lc(ep, headers={"Authorization": "adsfjaklsdjfklajsdfkjaklsdfj"})
    assert res.status_code == 401


async def test_endpoint_with_jwt_fail_without_security_config(
    testroute: Route, lc: LocalClient
):
    async def get_me(token: JWTAuth[UserProfile]):
        assert isinstance(token, UserProfile)

    testroute.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))(get_me)

    ep = testroute.get_endpoint(get_me)

    with pytest.raises(MissingDependencyError):
        ep.setup()


async def test_endpoint_login_and_validate(testroute: Route, lc: LocalClient):
    from lihil.config import lhl_set_config

    async def get_me(token: JWTAuth[UserProfile]) -> Resp[Text, status.OK]:
        assert token.user_id == "1" and token.user_name == "2"
        return "ok"

    async def login_get_token(login_form: OAuthLoginForm) -> JWTAuth[UserProfile]:
        return UserProfile(user_id="1", user_name="2")

    testroute.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))(get_me)
    testroute.post(login_get_token)
    lhl_set_config(
        app_config=AppConfig(
            security=SecurityConfig(jwt_secret="mysecret", jwt_algorithms=["HS256"])
        )
    )
    testroute.setup()

    login_ep = testroute.get_endpoint(login_get_token)

    res = await lc.submit_form(
        login_ep, form_data={"username": "user", "password": "test"}
    )

    token_data = await res.json()

    token_type, token = token_data["token_type"], token_data["access_token"]
    token_type: str

    lc.update_headers({"Authorization": f"{token_type.capitalize()} {token}"})

    meep = testroute.get_endpoint(get_me)

    res = await lc(meep)

    assert res.status_code == 200
    assert await res.text() == "ok"


@pytest.mark.skip("not implemented")
async def test_endpoint_login_and_validate_with_str_resp(
    testroute: Route, lc: LocalClient
):
    async def get_me(token: JWTAuth[str]) -> Resp[Text, status.OK]:
        assert token == "user_id"
        return "ok"

    async def login_get_token(login_form: OAuthLoginForm) -> JWTAuth[str]:
        return "user_id"

    testroute.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))(get_me)
    testroute.post(login_get_token)
    set_config(
        AppConfig(
            security=SecurityConfig(jwt_secret="mysecret", jwt_algorithms=["HS256"])
        )
    )
    testroute.setup()

    login_ep = testroute.get_endpoint(login_get_token)

    res = await lc.submit_form(
        login_ep, form_data={"username": "user", "password": "test"}
    )

    token_data = await res.json()

    token_type, token = token_data["token_type"], token_data["token"]
    token_type: str

    lc.update_headers({"Authorization": f"{token_type.capitalize()} {token}"})

    meep = testroute.get_endpoint(get_me)

    res = await lc(meep)

    assert res.status_code == 200
    assert await res.text() == "ok"


async def test_ep_with_plugin_type(testroute: Route, lc: LocalClient):

    class MyPlugin(PluginBase): ...

    async def myep(param: Annotated[str, MyPlugin]): ...

    testroute.get(myep)

    with pytest.raises(NotSupportedError):
        testroute.setup()


async def test_ep_is_scoped(testroute: Route):
    class Engine: ...

    def engine_factory() -> Engine:
        yield Engine()

    def func(engine: Annotated[Engine, use(engine_factory)]): ...

    testroute.get(func)
    ep = testroute.get_endpoint(func)
    ep.setup()

    assert ep.scoped


async def test_ep_with_plugin(testroute: Route):
    class MyParamProcessor(PluginBase):
        def __init__(self, name: str):
            self.name = name

        async def process(
            self, params: dict[str, Any], request: Request, resolver: Resolver
        ) -> None:
            params[self.name] = "processed"

    called: bool = False

    def func(p: Annotated[str, MyParamProcessor("p")]):
        nonlocal called
        called = True
        assert p == "processed"

    testroute.get(func)

    ep = testroute.get_endpoint(func)
    ep.setup()

    assert ep.sig.plugins

    await LocalClient()(ep)
    assert called


async def test_plugin_without_processor(testroute: Route):

    class MyPlugin(PluginBase):
        def parse(
            self,
            name: str,
            type_: type | UnionType | GenericAlias,
            annotation: Any,
            default: Any,
        ) -> PluginParam:
            return PluginParam(
                type_=type_,
                annotation=annotation,
                name=name,
                default=default,
                plugin=self,
            )

    async def f(p: Annotated[str, MyPlugin()]): ...

    lc = LocalClient()
    with pytest.raises(InvalidParamTypeError):
        await lc(lc.make_endpoint(f))


async def test_endpoint_with_list_query():
    called = False

    async def get_cart(names: list[int]) -> Empty:
        nonlocal called
        assert all(isinstance(n, int) for n in names)
        called = True

    lc = LocalClient()
    res = await lc.request(
        lc.make_endpoint(get_cart),
        method="GET",
        path="/",
        query_string="names=5&names=6",
    )

    res = await res.text()
    assert called


async def test_endpoint_with_tuple_query():
    called = False

    async def get_cart(names: tuple[int, ...]) -> Empty:
        nonlocal called
        assert isinstance(names, tuple)
        assert all(isinstance(n, int) for n in names)
        called = True

    lc = LocalClient()
    res = await lc.request(
        lc.make_endpoint(get_cart),
        method="GET",
        path="/",
        query_string=b"names=5&names=6",
    )

    res = await res.text()
    assert called


def test_set_1d_iterable():
    for t in (set, frozenset, tuple, list):
        assert is_nontextual_sequence(t)


async def test_ep_with_constraints():
    called: bool = False

    async def get_user(
        n: Annotated[int, Meta(gt=0)], user_id: Annotated[str, Meta(min_length=5)]
    ):
        nonlocal called
        called = True

    lc = LocalClient()

    ep = lc.make_endpoint(get_user, path="/{user_id}")
    resp = await lc(ep, path_params={"user_id": "user"}, query_params={"n": -1})
    res = await resp.json()
    assert not called


async def test_ep_with_cookie():
    called: bool = False

    async def get_user(
        refresh_token: Annotated[
            Cookie[str, Literal["refresh-token"]], Meta(min_length=1)
        ],
        user_id: Annotated[str, Meta(min_length=5)],
    ):
        nonlocal called
        assert len(user_id) >= 5
        called = True
        return True

    lc = LocalClient(headers={"cookie": "refresh-token=asdf"})

    ep = lc.make_endpoint(get_user, path="/{user_id}")
    resp = await lc(ep, path_params={"user_id": "user123"})
    res = await resp.json()
    assert res
    assert called

async def test_ep_with_cookie2():
    called: bool = False

    async def get_user(
        refresh_token: Annotated[Cookie[str], Meta(min_length=1)],
        user_id: Annotated[str, Meta(min_length=5)],
    ):
        nonlocal called
        called = True
        return True

    lc = LocalClient(headers={"cookie": "refresh-token=asdf"})

    ep = lc.make_endpoint(get_user, path="/{user_id}")
    resp = await lc(ep, path_params={"user_id": "user123"})
    res = await resp.json()
    assert res
    assert called


async def tests_calling_ep_query_without_default():
    lc = LocalClient()

    async def get_user(user_id: int):
        ...

    resp = await lc(lc.make_endpoint(get_user))
    assert resp.status_code == 422
