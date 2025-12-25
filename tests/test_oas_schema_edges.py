import types
from types import SimpleNamespace

import pytest
from msgspec import Struct, UNSET

from lihil.oas import model as oasmodel
from lihil.oas import schema as oas_schema
from lihil.oas.schema import (
    ParamError,
    ParamSchemaGenerationError,
    ResponseError,
    ResponseGenerationError,
    SchemaGenerationError,
    body_schema,
    detail_base_to_content as real_detail_base_to_content,
    get_ep_security,
    get_err_resp_schemas,
    get_path_item_from_route,
    type_to_content as real_type_to_content,
    _single_field_schema,
)
from lihil.problems import DetailBase, InvalidAuthError, InvalidRequestErrors


def test_schema_error_formatting_variants():
    err = SchemaGenerationError("boom", type_hint=int, detail="broken")
    assert err.describe() == ("Schema", "int")
    assert err.format_context("ctx", "hint") == " (ctx [hint])"
    assert err.format_context("", "hint") == " [hint]"

    param_err = ParamSchemaGenerationError(
        "param", type_hint="X", detail="d", param_error=ParamError(name="pid", source="query")
    )
    assert param_err.describe() == ("Param query pid", "X")
    assert param_err.format_context("ctx", "hint") == " (pid: Query[hint])"

    resp_err = ResponseGenerationError(
        "resp",
        type_hint="T",
        detail="d",
        response_error=ResponseError(status="500", content_type=None),
    )
    assert resp_err.describe() == ("Response 500", "T")
    assert resp_err.format_context("", "T") == " -> Response[500, [T]]"


def test_single_field_schema_adds_reference_component():
    class Sub(Struct):
        val: int

    class Wrapper(Struct):
        sub: Sub

    param = SimpleNamespace(
        type_=Wrapper, alias="wrap", source="query", required=True, name="wrap"
    )
    schemas: dict[str, object] = {}

    param_schema = _single_field_schema(param, schemas)

    assert "Wrapper" in schemas
    assert isinstance(param_schema, oasmodel.OASParameter)
    assert param_schema.schema_ == {"$ref": "#/components/schemas/Wrapper"}


def test_body_schema_collects_schema_errors():
    bad_param = SimpleNamespace(
        type_=type(lambda: None),
        name="payload",
        alias="payload",
        source="body",
        required=True,
        content_type="application/json",
    )
    ep_deps = SimpleNamespace(body_param=("payload", bad_param))
    errors: list[SchemaGenerationError] = []

    body = body_schema(ep_deps, {}, "endpoint", errors)

    assert body is None
    assert len(errors) == 1
    err = errors[0]
    assert isinstance(err, ParamSchemaGenerationError)
    assert err.param_error.name == "payload"
    assert err.param_error.source == "body"


def test_ep_security_scopes_added_to_components():
    auth_scheme = SimpleNamespace(
        scheme_name="auth",
        model={"type": "http"},
        scopes={"auth": "demo-scope"},
    )
    ep = SimpleNamespace(props=SimpleNamespace(auth_scheme=auth_scheme))
    security_schemas: dict[str, object] = {}

    security = get_ep_security(ep, security_schemas)

    assert security_schemas["auth"] == {"type": "http"}
    assert security == [{"auth": ["demo-scope"]}]


def test_path_item_error_endpoint_name_backfill(monkeypatch):
    def fake_generate_op_from_ep(ep, schemas, security_schemas, problem_path):
        err = SchemaGenerationError("fail", type_hint="X", detail="d", endpoint_name=None)
        return None, [err]

    monkeypatch.setattr(oas_schema, "generate_op_from_ep", fake_generate_op_from_ep)

    endpoint = SimpleNamespace(props=SimpleNamespace(in_schema=True), name="hello", method="GET")
    route = SimpleNamespace(path="/hello", endpoints={"GET": endpoint})
    schemas: dict[str, object] = {}
    security_schemas: dict[str, object] = {}
    error_map: dict[str, dict[str, list[SchemaGenerationError]]] = {}

    get_path_item_from_route(route, schemas, security_schemas, "/problems", error_map)

    assert error_map["/hello"]["GET"][0].endpoint_name == "hello"


def test_generate_oas_includes_security_schemes(monkeypatch):
    def fake_get_path_item(route, schemas, security_schemas, problem_path, error_map):
        security_schemas["auth"] = {"type": "http"}
        return oasmodel.OASPathItem()

    monkeypatch.setattr(oas_schema, "get_path_item_from_route", fake_get_path_item)

    from lihil.routing import Route

    class DummyConfig:
        PROBLEM_PATH = "/problems"
        TITLE = "Demo"
        VERSION = "1.0.0"

    route = Route("/secured")

    api = oas_schema.generate_oas([route], DummyConfig(), "v1")

    assert api.components.securitySchemes is not UNSET
    assert "auth" in api.components.securitySchemes


def test_format_context_returns_empty_when_no_descriptor_or_hint():
    err = SchemaGenerationError("boom", type_hint="", detail="d")
    assert err.format_context("", "") == ""


def test_get_err_resp_schemas_handles_problem_detail_failure(monkeypatch):
    def raise_schema(*_args, **_kwargs):
        raise SchemaGenerationError("fail", type_hint="T", detail="d")

    monkeypatch.setattr(oas_schema, "type_to_content", raise_schema)

    ep = SimpleNamespace(name="ep", props=SimpleNamespace(problems=(), auth_scheme=None))

    with pytest.raises(ResponseGenerationError) as excinfo:
        get_err_resp_schemas(ep, {}, "/problems")

    assert excinfo.value.response_error.status == "problem"

    monkeypatch.setattr(oas_schema, "type_to_content", real_type_to_content)


def test_get_err_resp_schemas_auth_branch(monkeypatch):
    auth_scheme = SimpleNamespace(scheme_name="auth", model={"type": "http"}, scopes=None)
    ep = SimpleNamespace(
        name="ep",
        props=SimpleNamespace(problems=(), auth_scheme=auth_scheme),
        sig=SimpleNamespace(return_params={}),
    )
    monkeypatch.setattr(oas_schema, "detail_base_to_content", lambda *args, **kwargs: {})

    resps = get_err_resp_schemas(ep, {}, "/problems")

    assert "401" in resps or "403" in resps  # InvalidAuthError sets __status__ = 401

    monkeypatch.setattr(oas_schema, "detail_base_to_content", real_detail_base_to_content)


def test_get_err_resp_schemas_single_error_generation_failure(monkeypatch):
    def raise_detail(*_args, **_kwargs):
        raise SchemaGenerationError("boom", type_hint="T", detail="d")

    monkeypatch.setattr(oas_schema, "detail_base_to_content", raise_detail)

    ep = SimpleNamespace(
        name="ep",
        props=SimpleNamespace(problems=(), auth_scheme=None),
    )

    with pytest.raises(ResponseGenerationError):
        get_err_resp_schemas(ep, {}, "/problems")

    monkeypatch.setattr(oas_schema, "detail_base_to_content", real_detail_base_to_content)


def test_get_err_resp_schemas_multi_error_generation_failure(monkeypatch):
    class Err1(DetailBase[str]):
        __status__ = 400

    class Err2(DetailBase[str]):
        __status__ = 400

    def raise_detail(err_type, *args, **kwargs):
        if err_type is Err2:
            raise SchemaGenerationError("boom", type_hint="T", detail="d")
        return {}

    monkeypatch.setattr(oas_schema, "detail_base_to_content", raise_detail)

    ep = SimpleNamespace(
        name="ep",
        props=SimpleNamespace(problems=[Err1, Err2], auth_scheme=None),
    )

    with pytest.raises(ResponseGenerationError):
        get_err_resp_schemas(ep, {}, "/problems")

    monkeypatch.setattr(oas_schema, "detail_base_to_content", real_detail_base_to_content)
