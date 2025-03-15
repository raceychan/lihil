import pytest
from starlette.requests import Request

from lihil import Route, Text, Use
from lihil.plugins.testing import LocalClient
from lihil.utils.phasing import encode_text

route = Route("/{p}")


class Engine: ...


class UserService:
    def __init__(self, engine: Engine):
        self.engine = engine


def get_engine() -> Engine:
    return Engine()


route.add_nodes(UserService, get_engine)


@route.post
async def create_todo(req: Request, q: int, p: str, engine: Engine) -> Text:
    assert isinstance(req, Request)
    assert isinstance(q, int)
    assert isinstance(p, str)
    assert isinstance(engine, Engine)
    return "ok"


@route.get
async def get_todo(p: str, service: UserService): ...


async def test_call_endpoint():
    ep = route.get_endpoint(create_todo)
    assert ep.encoder is encode_text
    client = LocalClient()
    resp = await client.call_endpoint(
        ep=ep, path_params=dict(p="hello"), query_params=dict(q=5)
    )
    result = await resp.body()
    assert result == b"ok"


async def test_non_use_dep():
    ep = route.get_endpoint(get_todo)
    deps = ep.deps.dependencies
    assert len(deps) == 1  # only service not engine
