import asyncio
import inspect
from types import MappingProxyType
from typing import Annotated, Any

import pytest
from msgspec import Struct
from msgspec.json import encode as json_encode
from typing_extensions import NotRequired

from lihil import Ignore, Param, use
from lihil.errors import InvalidParamError, NotSupportedError
from lihil.interface import MISSING
from lihil.signature.tool_parser import _resolve_schema, tool

try:  # pragma: no cover - optional dependency
    from pydantic import BaseModel
except ImportError:  # pragma: no cover - optional dependency
    BaseModel = None


class UserService: ...


async def sample_tool(
    user_id: Annotated[str, Param(description="The ID of the user")],
    user_data: dict[str, Any],
    service: Annotated[UserService, use(UserService)],
    notify: bool = False,
    email: Annotated[
        str | None, Param(alias="email_address", description="User email")
    ] = None,
) -> dict[str, Any]:
    """Create a new user in the system."""


def test_tool_parser_collects_metadata():
    t = tool(sample_tool)
    signature = t.signature

    assert t.name == "sample_tool"
    assert t.description == "Create a new user in the system."
    assert signature.return_type == dict[str, Any]

    # service parameter is injected dependency
    assert "service" not in signature.parameters

    user_id = signature.parameters["user_id"]
    assert user_id.alias == "user_id"
    assert user_id.required is True
    assert user_id.schema["description"] == "The ID of the user"
    assert user_id.schema["type"] == "string"

    notify = signature.parameters["notify"]
    assert notify.required is False
    assert notify.schema["default"] is False

    email = signature.parameters["email"]
    assert email.alias == "email_address"
    assert email.required is False
    email_options = email.schema.get("anyOf", [])
    assert any(option.get("type") == "string" for option in email_options)
    assert email.schema.get("default") is None

    tool_payload = t.schema
    properties = tool_payload["parameters"]["properties"]
    assert set(properties) == {"user_id", "user_data", "notify", "email_address"}
    assert tool_payload["parameters"]["required"] == ["user_id", "user_data"]


def test_tool_parser_rejects_duplicate_aliases():
    AnnotatedAlias = Annotated[int, Param(alias="shared")]

    async def duplicate_alias(arg1: AnnotatedAlias, arg2: AnnotatedAlias): ...

    with pytest.raises(InvalidParamError):
        tool(duplicate_alias)


def test_tool_parser_disallows_varargs():
    def invalid(*args: int): ...

    with pytest.raises(NotSupportedError):
        tool(invalid)


async def complex_tool(
    keywords: Annotated[
        list[str], Param(description="Search terms", examples=[["ai", "ml"]])
    ],
    metadata: Annotated[
        dict[str, str],
        Param(
            description="Additional metadata",
            examples=[{"source": "web"}],
            extra_json_schema={"additionalProperties": {"type": "string"}},
        ),
    ],
    *,
    limit: Annotated[int, Param(ge=1, le=100, examples=[5])] = 10,
) -> list[dict[str, Any]]:
    """Complex search helper."""
    raise NotImplementedError


def test_tool_parser_handles_complex_examples():
    t = tool(complex_tool)
    signature = t.signature

    keywords = signature.parameters["keywords"]
    assert keywords.schema["type"] == "array"
    assert keywords.schema["items"]["type"] == "string"
    assert keywords.schema["description"] == "Search terms"
    assert keywords.schema["examples"] == [["ai", "ml"]]

    metadata = signature.parameters["metadata"]
    assert metadata.schema["type"] == "object"
    assert metadata.schema["description"] == "Additional metadata"
    assert metadata.schema["examples"] == [{"source": "web"}]
    assert metadata.schema["additionalProperties"] == {"type": "string"}

    limit = signature.parameters["limit"]
    assert limit.required is False
    assert limit.schema["default"] == 10
    assert limit.schema["minimum"] == 1
    assert limit.schema["maximum"] == 100
    assert limit.schema["examples"] == [5]

    payload = t.schema
    props = payload["parameters"]["properties"]
    assert props["keywords"]["examples"] == [["ai", "ml"]]
    assert props["metadata"]["additionalProperties"] == {"type": "string"}
    assert payload["parameters"]["required"] == ["keywords", "metadata"]


class Payload(Struct):
    value: int


class RequestStruct(Struct):
    name: str
    count: int


def fallback_tool(
    data: Any,
    payload: Payload,
    payload_opt: Payload | None = None,
    model: RequestStruct | None = None,
    tags: list[str] = ("default",),
    ratio: float = 0.0,
    options: tuple[int, int] = (1, 2),
    config: dict[str, int] = MappingProxyType({"mode": 1}),
    secret: Ignore[str] = "hidden",
):
    pass


def typed_tool() -> int:
    return 1


def test_tool_parser_any_defaults_and_returns():
    t = tool(fallback_tool)
    signature = t.signature

    assert signature.return_type is MISSING

    data_schema = signature.parameters["data"].schema
    assert data_schema == {"type": "string"}

    payload_schema = signature.parameters["payload"].schema
    assert payload_schema["type"] == "object"
    assert payload_schema["properties"]["value"]["type"] == "integer"

    payload_opt_schema = signature.parameters["payload_opt"].schema
    assert payload_opt_schema["anyOf"][0]["type"] == "null"
    assert payload_opt_schema["anyOf"][1]["properties"]["value"]["type"] == "integer"
    assert payload_opt_schema["default"] is None

    model_schema = signature.parameters["model"].schema
    assert model_schema["anyOf"][0]["type"] == "null"
    assert model_schema["anyOf"][1]["properties"]["name"]["type"] == "string"
    assert model_schema["anyOf"][1]["properties"]["count"]["type"] == "integer"
    assert model_schema["default"] is None

    tags_schema = signature.parameters["tags"].schema
    assert tags_schema["default"] == ("default",)

    options_schema = signature.parameters["options"].schema
    assert options_schema["default"] == (1, 2)

    config_schema = signature.parameters["config"].schema
    assert "default" not in config_schema
    assert signature.parameters["config"].default["mode"] == 1

    ratio_schema = signature.parameters["ratio"].schema
    assert ratio_schema["default"] == 0.0

    assert "secret" not in signature.parameters

    typed_tool_obj = tool(typed_tool)
    assert typed_tool_obj.signature.return_type is int

    generic_tool_obj = tool(generic_return_tool)
    assert generic_tool_obj.signature.return_type == Annotated[int, "meta"]


def test_resolve_schema_inlines_refs_with_lists():
    schema = {"anyOf": [{"$ref": "#/components/schemas/Payload"}]}
    defs = {
        "Payload": {
            "type": "object",
            "properties": {
                "value": {"type": "integer"},
                "items": {"type": "array", "items": {"$ref": "#/components/schemas/N"}},
            },
            "required": ["value", "items"],
        },
        "N": {"type": "integer"},
    }

    resolved = _resolve_schema(schema, defs)

    assert resolved["anyOf"][0]["properties"]["items"]["items"]["type"] == "integer"


def generic_return_tool() -> Annotated[int, "meta"]:
    return 1


async def async_tool(user_id: Annotated[str, Param(description="user id")]) -> str:
    return f"{user_id}-ok"


def test_tool_call_handles_async_callable():
    t = tool(async_tool)

    assert t.name == "async_tool"
    assert inspect.iscoroutinefunction(t.func)

    result = t("demo")
    assert inspect.iscoroutine(result)
    assert asyncio.run(result) == "demo-ok"


async def virtual_dict_tool(
    user_id: Annotated[str, Param(alias="uid")],
    limit: int = 5,
    note: Annotated[str | None, Param(alias="note_text")] = None,
) -> None: ...


def test_tool_signature_virtual_dict_metadata():
    t = tool(virtual_dict_tool)

    virtual = t.signature.virtual_dict
    assert issubclass(virtual, dict)
    assert virtual.__name__ == f"{virtual_dict_tool.__name__}_params"
    assert virtual.__module__ == virtual_dict_tool.__module__
    assert virtual.__required_keys__ == frozenset({"uid"})
    assert virtual.__optional_keys__ == frozenset({"limit", "note_text"})
    assert virtual.__annotations__["uid"] is str
    assert virtual.__annotations__["limit"] == NotRequired[int]
    assert virtual.__annotations__["note_text"] == NotRequired[str | None]


async def decode_params_tool(
    user_id: Annotated[str, Param(alias="uid")],
    limit: int = 3,
    notify: Annotated[bool, Param(alias="send_notification")] = True,
) -> None: ...


def test_tool_decode_params_applies_defaults_and_aliases():
    t = tool(decode_params_tool)

    payload = json_encode({"uid": "abc"})
    decoded = t.decode_params(payload)

    assert decoded["uid"] == "abc"
    assert decoded["send_notification"] is True
    assert decoded["limit"] == 3
