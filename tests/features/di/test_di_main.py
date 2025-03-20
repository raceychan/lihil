import pytest
from starlette.requests import Request

from lihil import Payload, Route, Text
from lihil.plugins.testclient import LocalClient
from lihil.utils.phasing import encode_text

route = Route("/{p}")


class Engine: ...


class UserService:
    def __init__(self, engine: Engine):
        self.engine = engine


def get_engine() -> Engine:
    return Engine()


async def test_call_endpoint():
    route.add_nodes(UserService, get_engine)

    @route.post
    async def create_todo(req: Request, q: int, p: str, engine: Engine) -> Text:
        assert isinstance(req, Request)
        assert isinstance(q, int)
        assert isinstance(p, str)
        assert isinstance(engine, Engine)
        return "ok"

    ep = route.get_endpoint(create_todo)
    assert ep.encoder is encode_text
    client = LocalClient()
    resp = await client.call_endpoint(
        ep=ep, path_params=dict(p="hello"), query_params=dict(q=5)
    )
    result = await resp.body()
    assert result == b"ok"


async def test_non_use_dep():
    @route.get
    async def get_todo(p: str, service: UserService): ...

    ep = route.get_endpoint(get_todo)
    deps = ep.deps.dependencies
    assert len(deps) == 1  # only service not engine


async def test_validtion_error():
    "when receive data type and expected data time are different, str and int for example"
    route = Route("/{p}")

    @route.post
    async def create_todo(p: str, q: int) -> Text:
        return "ok"

    ep = route.get_endpoint(create_todo)
    client = LocalClient()

    # Send string where int is expected
    resp = await client.call_endpoint(
        ep=ep, path_params=dict(p="hello"), query_params=dict(q='"s"')
    )

    assert resp.status_code == 422
    result = await resp.json()

    error = result["detail"][0]
    assert "InvalidDataType" == error["type"]
    assert "query" == error["location"]
    assert "q" == error["param"]

    # test invalid json
    resp = await client.call_endpoint(
        ep=ep, path_params=dict(p="hello"), query_params=dict(q="s")
    )

    assert resp.status_code == 422
    result = await resp.json()

    error = result["detail"][0]
    assert "InvalidJsonReceived" == error["type"]
    assert "query" == error["location"]
    assert "q" == error["param"]


async def test_decoder_error():
    "when receive data is not in vaild json format"
    route = Route("/test")

    @route.post
    async def create_todo(data: Todo) -> Text:
        return "ok"

    ep = route.get_endpoint(create_todo)
    client = LocalClient()

    # Send invalid JSON
    resp = await client.call_endpoint(ep, body=b"{invalid json")

    assert resp.status_code == 422
    result = await resp.json()


async def test_param_with_default():
    "when param has default values and is not show up in received"
    route = Route("/{p}")

    @route.get
    async def get_todo(p: str, q: int = 42) -> Text:
        return f"p={p}, q={q}"

    ep = route.get_endpoint(get_todo)
    client = LocalClient()

    # Don't send the parameter with default value
    resp = await client.call_endpoint(ep=ep, path_params=dict(p="hello"))

    assert resp.status_code == 200
    result = await resp.body()
    assert result == b"p=hello, q=42"


async def test_body_with_default():
    "when receive data is not in vaild json format"
    route = Route("/test")

    @route.post
    async def create_todo(data: Todo = Todo("aloha")) -> Text:
        return "ok"

    ep = route.get_endpoint(create_todo)
    client = LocalClient()

    # Send invalid JSON
    resp = await client.call_endpoint(ep)

    assert resp.status_code == 200


class Todo(Payload):
    message: str


async def test_received_empty_body():
    "body is required but body is received as empty bytes"
    route = Route("/test")

    @route.post
    async def create_todo(data: Todo) -> Text:
        return "ok"

    ep = route.get_endpoint(create_todo)
    client = LocalClient()

    # Send empty body
    resp = await client.call_endpoint(ep, body=b"")

    assert resp.status_code == 422
    result = await resp.json()

    error = result["detail"][0]
    assert "MissingRequestParam" in error["type"]
    assert error["location"] == "body"


async def test_parse_command():
    "a request that has body is treated as `command`"
    route = Route("/test")

    @route.post
    async def create_todo(data: Todo) -> Text:
        return f"received: {data.message}"

    ep = route.get_endpoint(create_todo)
    client = LocalClient()

    # Send a command as JSON body
    resp = await client.call_endpoint(ep, body={"message": "hello world"})

    result = await resp.body()
    assert resp.status_code == 200
    assert result == b"received: hello world"


async def test_path_keys_not_consumed():
    "example {user_id}/{order_id} but only user_id is used in f signature"
    route = Route("/{user_id}/{order_id}")

    @route.get
    async def get_user(user_id: str) -> Text:
        return f"user: {user_id}"

    ep = route.get_endpoint(get_user)
    client = LocalClient()

    # Call with both path parameters, but function only uses one
    resp = await client.call_endpoint(
        ep=ep, path_params=dict(user_id="user123", order_id="order456")
    )

    # The endpoint should work, but there should be a warning logged about unused path keys
    # We can't easily test the warning, but we can verify the endpoint works
    assert resp.status_code == 200
    result = await resp.body()
    assert result == b"user: user123"
