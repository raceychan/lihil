import uuid
from typing import Annotated

import pytest
from ididi import AsyncScope, Graph, Ignore, use
from starlette.requests import Request

from lihil import (
    Form,
    Json,
    Payload,
    Query,
    Resp,
    Route,
    Stream,
    Text,
    UploadFile,
    Use,
    status,
)
from lihil.errors import NotSupportedError, StatusConflictError
from lihil.plugins.testclient import LocalClient
from lihil.utils.threading import async_wrapper


class User(Payload, kw_only=True):
    id: int
    name: str
    email: str


# class Engine: ...


@pytest.fixture
async def rusers() -> Route:
    return Route("users/{user_id}")


@pytest.fixture
async def lc() -> LocalClient:
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
    assert "q" in ep.deps.query_params
    assert "func_dep" in ep.deps.dependencies
    assert "user_id" in ep.deps.path_params

    ep_ret = ep.deps.return_params[201]
    assert ep_ret.type_ is User


def test_status_conflict(rusers: Route):

    async def get_user(
        user_id: str,
    ) -> Annotated[Resp[str, status.NO_CONTENT], "hello"]:
        return "hello"

    rusers.get(get_user)
    with pytest.raises(StatusConflictError):
        rusers.get_endpoint(get_user).setup()


def test_annotated_generic(rusers: Route):

    async def update_user(user_id: str) -> Annotated[dict[str, str], "aloha"]: ...

    rusers.put(update_user)
    ep = rusers.get_endpoint(update_user)
    ep.setup()
    repr(ep)
    assert ep.deps.return_params[200].type_ == dict[str, str]


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

    ep = rusers.get_endpoint(update_user)
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

    async def get() -> Resp[None, 204]:
        return "asdf"

    rusers.get(get)
    ep = rusers.get_endpoint("GET")

    res = await lc.call_endpoint(ep)

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
    assert ep.deps.query_params
    assert not ep.deps.path_params


async def test_ep_with_random_annoated_query(rusers: Route, lc: LocalClient):

    async def get(aloha: Annotated[int, "aloha"]) -> Resp[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    ep.setup()
    assert ep.deps.query_params
    assert "aloha" in ep.deps.query_params
    assert ep.deps.query_params["aloha"].type_ is int


async def test_ep_with_random_annoated_path1(rusers: Route, lc: LocalClient):

    async def get(user_id: Annotated[int, "aloha"]) -> Resp[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    ep.setup()
    assert ep.deps.path_params
    assert "user_id" in ep.deps.path_params
    assert ep.deps.path_params["user_id"].type_ is int


async def test_ep_with_random_annoated_path2(rusers: Route, lc: LocalClient):
    class UserInfo(Payload):
        name: str
        phones: list[str]

    async def get(user: Annotated[UserInfo, "aloha"]) -> Resp[Text, status.OK]:
        return "ok"

    rusers.get(get)

    ep = rusers.get_endpoint("GET")
    ep.setup()
    assert ep.deps.body_param
    assert ep.deps.body_param[1].type_ is UserInfo


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
