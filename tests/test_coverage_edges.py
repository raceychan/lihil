from dataclasses import dataclass
from typing import Annotated

import pytest
from ididi import Graph, NodeMeta

from lihil import HTTPException, Lihil, MISSING, Param, Route, status
from lihil.config import DEFAULT_CONFIG
from lihil.errors import NotSupportedError
from lihil.interface.props import IOASContent, IOASResponse
from lihil.signature.parser import EndpointParser, formdecoder_factory
from lihil.signature.params import FormMeta, FormParam, PathParam
from lihil.signature.returns import parse_returns
from lihil.vendors import FormData


def test_oas_response_props_are_importable():
    content: IOASContent = {"schema": {"type": "string"}, "example": "ok"}
    response: IOASResponse = {
        "description": "ok",
        "content": {"application/json": content},
    }

    assert response["content"]["application/json"]["example"] == "ok"


def test_asgi_sub_reuses_existing_child_route():
    route = Route("/api")

    users = route.sub("users")

    assert route.sub("users") is users


def test_lihil_config_setter_accepts_config():
    app = Lihil()

    app.config = DEFAULT_CONFIG

    assert app.config is DEFAULT_CONFIG


def test_route_include_subroutes_warns_and_merges():
    parent = Route("/api")
    child = Route("/users")

    with pytest.warns(DeprecationWarning):
        parent.include_subroutes(child)

    assert parent.subroutes[0].path == "/api/users"


def test_endpoint_skips_duplicate_plugins_and_setup_twice_raises():
    calls = []

    def plugin(ep_info):
        calls.append(ep_info)
        return ep_info.func

    route = Route("/plugin", plugins=[plugin, plugin])

    @route.get
    async def handler():
        return {"ok": True}

    route.setup()
    endpoint = route.get_endpoint("GET")

    assert len(calls) == 1
    with pytest.raises(Exception, match="setup"):
        endpoint.setup(endpoint.sig, route.graph)


async def test_static_endpoint_reraises_without_solver():
    route = Route("/boom")

    @route.get
    async def boom():
        raise ValueError("boom")

    route.setup()
    endpoint = route.get_endpoint("GET")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/boom",
        "headers": [],
        "query_string": b"",
        "path_params": {},
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    with pytest.raises(ValueError, match="boom"):
        await endpoint.make_static_call(scope, receive, send)


def test_http_exception_accepts_int_status():
    assert HTTPException(status=499).status == 499


def test_path_and_form_param_missing_or_default_edges():
    path_param = PathParam(
        type_=str,
        annotation=str,
        name="item_id",
        alias="item_id",
        decoder=str,
    )

    value, error = path_param.extract({})
    assert value is MISSING
    assert error

    form_param = FormParam(
        type_=str,
        annotation=str,
        name="name",
        alias="name",
        decoder=lambda form: form["name"],
        default="anon",
        meta=FormMeta(),
    )

    value, error = form_param.extract(FormData())
    assert value == "anon"
    assert error is MISSING


def test_formdecoder_factory_accepts_sequence_of_structured_types():
    @dataclass
    class Item:
        name: str

    with pytest.raises(TypeError, match="Unsupported type"):
        formdecoder_factory(list[Item])


def test_parse_param_node_meta_ignore_and_missing_factory():
    parser = EndpointParser(Graph(), "/items")

    parsed = parser.parse_param("name", Annotated[str, NodeMeta(ignore=True)])
    assert parsed[0].name == "name"

    with pytest.raises(RuntimeError, match="node without factory"):
        parser.parse_param("name", Annotated[str, NodeMeta()])


def test_parse_returns_rejects_partial_status_union():
    with pytest.raises(NotSupportedError, match="union size"):
        parse_returns(Annotated[str, status.OK] | int)


def test_signature_collects_missing_header_error():
    from lihil.vendors import Headers, QueryParams

    route = Route("/headers")

    @route.get
    async def handler(token: Annotated[str, Param("header")]):
        return token

    route.setup()
    endpoint = route.get_endpoint("GET")
    conn = type(
        "Conn",
        (),
        {
            "headers": Headers({}),
            "path_params": {},
            "query_params": QueryParams(""),
        },
    )()

    parsed = endpoint._injector._validate_conn(conn)

    assert parsed.errors
