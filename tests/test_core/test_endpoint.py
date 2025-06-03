import uuid
from typing import Annotated

import pytest
from ididi import AsyncScope, Graph, Ignore, use
from starlette.requests import Request

from lihil import (
    Empty,
    Form,
    Json,
    Param,
    Payload,
    Request,
    Route,
    Stream,
    Text,
    UploadFile,
    field,
    status,
)
from lihil.config import DEFAULT_CONFIG, lhl_set_config
from lihil.errors import InvalidParamError, StatusConflictError
from lihil.interface import Base
from lihil.local_client import LocalClient
from lihil.plugins.auth.jwt import JWTAuthParam, JWTAuthPlugin, JWTConfig
from lihil.plugins.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm
from lihil.signature.parser import EndpointParser
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
    app_config = JWTConfig(JWT_SECRET="mysecret", JWT_ALGORITHMS=["HS256"])
    lhl_set_config(app_config)
    route = Route("test")
    route.endpoint_parser = EndpointParser(route.graph, route.path)
    yield route
    lhl_set_config(DEFAULT_CONFIG)


@pytest.fixture
def lc() -> LocalClient:
    return LocalClient()


def add_q(q: str, user_id: str) -> Ignore[str]:
    return q


async def test_return_status(rusers: Route):
    async def create_user(
        user: User,
        req: Request,
        user_id: str,
        func_dep: Annotated[str, use(add_q)],
    ) -> Annotated[Json[User], status.CREATED]:
        return User(id=user.id, name=user.name, email=user.email)

    rusers.post(create_user)
    await rusers.setup()
    ep = rusers.get_endpoint(create_user)
    assert "q" in ep.sig.query_params
    assert "func_dep" in ep.sig.dependencies
    assert "user_id" in ep.sig.path_params

    ep_ret = ep.sig.return_params[201]
    assert ep_ret.type_ is User


async def test_status_conflict(rusers: Route):

    async def get_user(
        user_id: str,
    ) -> Annotated[Annotated[str, status.NO_CONTENT], "hello"]:
        return "hello"

    rusers.get(get_user)
    with pytest.raises(StatusConflictError):
        rusers.get_endpoint(get_user)
        await rusers.setup()


async def test_annotated_generic(rusers: Route):

    async def update_user(user_id: str) -> Annotated[dict[str, str], "aloha"]: ...

    rusers.put(update_user)
    ep = rusers.get_endpoint(update_user)
    await rusers.setup()
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

    async def get() -> Annotated[Empty, status.BAD_REQUEST]:
        return "asdf"

    rusers.get(get)
    await rusers.setup()
    ep = rusers.get_endpoint("GET")

    res = await lc.call_endpoint(ep)

    assert res.status_code == 400
    assert await res.body() == b""


async def test_ep_requiring_form(rusers: Route, lc: LocalClient):

    class UserInfo(Payload):
        username: str
        email: str

    async def get(
        req: Request, fm: Annotated[UserInfo, Form()]
    ) -> Annotated[str, status.OK]:
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


async def test_ep_requiring_missing_Param(rusers: Route, lc: LocalClient):

    class UserInfo(Payload):
        username: str
        email: str

    async def get(
        req: Request, fm: Annotated[UserInfo, Form()]
    ) -> Annotated[str, status.OK]:
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

    async def get(
        req: Request, myfile: Annotated[UploadFile, Form()]
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
    assert result.status_code == 200


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


async def test_ep_requiring_upload_file_fail(rusers: Route, lc: LocalClient):
    async def get(req: Request, myfile: UploadFile) -> Annotated[str, status.OK]:
        return None

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    result = await lc.call_endpoint(ep)
    assert result.status_code == 422


async def test_ep_requiring_file_bytse(rusers: Route, lc: LocalClient):
    async def get(
        by_form: Annotated[list[int], Form()],
    ) -> Annotated[Text, status.OK]:
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

    with pytest.raises(InvalidParamError):
        await lc.call_endpoint(
            ep,
            body=multipart_data,
            headers={f"content-type": content_type},
        )


async def test_ep_requiring_form_invalid_type(rusers: Route, lc: LocalClient):
    async def get(
        by_form: Annotated[list[int], Form()],
    ) -> Annotated[Text, status.OK]:
        assert isinstance(by_form, bytes)
        return "ok"

    rusers.get(get)
    with pytest.raises(InvalidParamError):
        await rusers.setup()


async def test_ep_requiring_form_sequence_type(rusers: Route, lc: LocalClient):
    class UserInfo(Payload):
        name: str
        phones: list[str]

    async def get(
        by_form: Annotated[UserInfo, Param()],
    ) -> Annotated[Text, status.OK]:
        assert isinstance(by_form, UserInfo)
        return "ok"

    rusers.get(get)


async def test_ep_mark_override_others(rusers: Route, lc: LocalClient):
    class UserInfo(Payload):
        name: str
        phones: list[str]

    async def get(
        user_id: Annotated[UserInfo, Param("query")],
    ) -> Annotated[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    await rusers.setup()
    assert ep.sig.query_params
    assert not ep.sig.path_params


async def test_ep_with_random_annoated_query(rusers: Route, lc: LocalClient):

    async def get(aloha: Annotated[int, "aloha"]) -> Annotated[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    await rusers.setup()
    assert ep.sig.query_params
    assert "aloha" in ep.sig.query_params
    assert ep.sig.query_params["aloha"].type_ is int


async def test_ep_with_random_annoated_path1(rusers: Route, lc: LocalClient):

    async def get(user_id: Annotated[int, "aloha"]) -> Annotated[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    await rusers.setup()
    assert ep.sig.path_params
    assert "user_id" in ep.sig.path_params
    assert ep.sig.path_params["user_id"].type_ is int


async def test_ep_with_random_annoated_path2(rusers: Route, lc: LocalClient):
    class UserInfo(Payload):
        name: str
        phones: list[str]

    async def get(user: Annotated[UserInfo, "aloha"]) -> Annotated[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    await rusers.setup()
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
    ) -> Annotated[Text, status.OK]:
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
        user_id: str, engine: Annotated[Engine, use(Engine)], resolver: AsyncScope
    ) -> Annotated[Text, status.OK]:
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
        user_id: str, engine: Annotated[Engine, use(Engine)], resolver: AsyncScope
    ) -> Annotated[Text, status.OK]:
        assert isinstance(resolver, AsyncScope)
        return "ok"

    rusers.post(post, scoped=True)
    res = await lc.call_endpoint(
        rusers.get_endpoint("POST"), path_params={"user_id": "123"}
    )

    text = await res.text()
    assert text == "ok"


GET_RESP = Annotated[Text, status.OK]


async def test_endpoint_with_resp_alias(rusers: Route, lc: LocalClient):

    async def get(user_id: str) -> GET_RESP:
        return "ok"

    rusers.get(get)
    res = await lc.call_endpoint(
        rusers.get_endpoint("GET"), path_params={"user_id": "123"}
    )

    text = await res.text()
    assert text == "ok"


class UserProfile(Base):

    user_id: str = field(name="sub")
    user_name: str


# async def test_endpoint_returns_jwt_payload(testroute: Route, lc: LocalClient):

#     async def get_token(data: OAuthLoginForm) -> JWTAuth[UserProfile]:
#         return UserProfile(user_id="1", user_name=data.username)

#     testroute.post(get_token)

#     ep = testroute.get_endpoint(get_token)

#     app_config = JWTConfig(JWT_SECRET="mysecret", JWT_ALGORITHMS=["HS256"])
#     lhl_set_config(app_config)
#     await testroute.setup()

#     res = await lc.submit_form(
#         ep, form_data={"username": "user", "password": "pasword"}
#     )

#     token = await res.json()

#     decoder = jwt_decoder_factory(payload_type=UserProfile)
#     token_type, token = token["token_type"], token["access_token"]
#     content = f"{token_type.capitalize()} {token}"

#     payload = decoder(content)
#     assert isinstance(payload, UserProfile)


async def test_oauth2_not_plugin():

    async def get_user(
        token: Annotated[str, Param("header", alias="Authorization")],
    ): ...

    route = Route("me")
    route.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))(get_user)

    ep = route.get_endpoint("GET")
    await route.setup()

    assert ep.sig.header_params


@pytest.fixture
def jwt_auth_plugin():
    return JWTAuthPlugin(jwt_secret="mysecret", jwt_algorithms="HS256")


async def test_endpoint_with_jwt_decode_fail(
    testroute: Route, lc: LocalClient, jwt_auth_plugin: JWTAuthPlugin
):
    async def get_me(
        token: Annotated[
            UserProfile,
            Param("header", alias="Authorization", extra_meta=dict(skip_unpack=True)),
        ],
    ):
        assert isinstance(token, UserProfile)

    testroute.get(
        auth_scheme=OAuth2PasswordFlow(token_url="token"),
        plugins=[jwt_auth_plugin.decode_plugin()],
    )(get_me)

    ep = testroute.get_endpoint(get_me)
    await testroute.setup()

    res = await lc(ep, headers={"Authorization": "adsfjaklsdjfklajsdfkjaklsdfj"})
    assert res.status_code == 401


async def test_endpoint_login_and_validate(
    testroute: Route, lc: LocalClient, jwt_auth_plugin: JWTAuthPlugin
):
    @testroute.get(
        auth_scheme=OAuth2PasswordFlow(token_url="token"),
        plugins=[jwt_auth_plugin.decode_plugin()],
    )
    async def get_me(
        token: Annotated[UserProfile, JWTAuthParam],
    ) -> Annotated[Text, status.OK]:
        assert token.user_id == "1" and token.user_name == "2"
        return "ok"

    @testroute.post(plugins=[jwt_auth_plugin.encode_plugin(expires_in_s=3600)])
    async def login_get_token(login_form: OAuthLoginForm) -> UserProfile:
        return UserProfile(user_id="1", user_name="2")

    await testroute.setup()

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


async def test_ep_is_scoped(testroute: Route):
    class Engine: ...

    def engine_factory() -> Engine:
        yield Engine()

    def func(engine: Annotated[Engine, use(engine_factory)]): ...

    testroute.get(func)
    ep = testroute.get_endpoint(func)
    await testroute.setup()

    assert ep.scoped


async def test_endpoint_with_list_query():
    called = False

    async def get_cart(names: list[int]) -> Empty:
        nonlocal called
        assert all(isinstance(n, int) for n in names)
        called = True

    lc = LocalClient()
    res = await lc.request(
        await lc.make_endpoint(get_cart),
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
        await lc.make_endpoint(get_cart),
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
        n: Annotated[int, Param(gt=0)], user_id: Annotated[str, Param(min_length=5)]
    ):
        nonlocal called
        called = True

    lc = LocalClient()

    ep = await lc.make_endpoint(get_user, path="/{user_id}")
    resp = await lc(ep, path_params={"user_id": "user"}, query_params={"n": -1})
    res = await resp.json()
    assert not called


async def test_ep_with_cookie():
    called: bool = False

    async def get_user(
        refresh_token: Annotated[
            str, Param("cookie", alias="x-refresh-token", min_length=1)
        ],
        user_id: Annotated[str, Param(min_length=5)],
    ):
        nonlocal called
        assert len(user_id) >= 5
        called = True
        return True

    lc = LocalClient(headers={"cookie": "x-refresh-token=asdf"})
    ep = await lc.make_endpoint(get_user, path="/{user_id}")
    assert ep.sig.header_params["refresh_token"].cookie_name == "x-refresh-token"
    resp = await lc(ep, path_params={"user_id": "user123"})
    res = await resp.json()
    assert res
    assert called


async def test_ep_with_cookie2():
    called: bool = False

    async def get_user(
        refresh_token: Annotated[str, Param("cookie", min_length=1)],
        user_id: Annotated[str, Param(min_length=5)],
    ):
        nonlocal called
        called = True
        return True

    lc = LocalClient(headers={"cookie": "refresh-token=asdf"})

    ep = await lc.make_endpoint(get_user, path="/{user_id}")
    resp = await lc(ep, path_params={"user_id": "user123"})
    res = await resp.json()
    assert res
    assert called


async def tests_calling_ep_query_without_default():
    lc = LocalClient()

    async def get_user(user_id: int): ...

    resp = await lc(await lc.make_endpoint(get_user))
    assert resp.status_code == 422


async def test_ep_with_multiple_value_header():
    lc = LocalClient()

    async def read_items(x_token: Annotated[list[str] | None, Param("header")] = None):
        return {"X-Token values": x_token}

    ep = await lc.make_endpoint(read_items)
    resp = await lc.request(
        ep,
        method="GET",
        path="",
        multi_headers=[("x-token", "value1"), ("x-token", "value2")],
    )
    assert resp.status_code == 200


from msgspec import convert


async def test_convert(): ...


async def test_ep_requiring_upload_file_with_decoder(rusers: Route, lc: LocalClient):

    async def get(
        req: Request,
        myfile: Annotated[UploadFile, Form(max_files=0, decoder=lambda x: x)],
    ) -> Annotated[str, status.OK]:
        assert isinstance(myfile, UploadFile)
        return ""

    await lc.make_endpoint(get)
