from typing import Annotated, Any

import pytest
from msgspec import Struct

from lihil import Ignore, Param, use
from lihil.errors import InvalidParamError, NotSupportedError
from lihil.signature.tool import ToolParser, _resolve_schema

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
    parser = ToolParser()

    signature = parser.parse(sample_tool)

    assert signature.name == "sample_tool"
    assert signature.description == "Create a new user in the system."
    assert signature.return_type.startswith("dict")

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

    tool_payload = signature.schema
    # fn_block = tool_payload["function"]
    properties = tool_payload["parameters"]["properties"]
    assert set(properties) == {"user_id", "user_data", "notify", "email_address"}
    assert tool_payload["parameters"]["required"] == ["user_id", "user_data"]


def test_tool_parser_rejects_duplicate_aliases():
    parser = ToolParser()

    AnnotatedAlias = Annotated[int, Param(alias="shared")]

    async def duplicate_alias(arg1: AnnotatedAlias, arg2: AnnotatedAlias): ...

    with pytest.raises(InvalidParamError):
        parser.parse(duplicate_alias)


def test_tool_parser_disallows_varargs():
    parser = ToolParser()

    def invalid(*args: int): ...

    with pytest.raises(NotSupportedError):
        parser.parse(invalid)


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
    parser = ToolParser()

    signature = parser.parse(complex_tool)

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

    payload = signature.schema
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
    model: RequestStruct = RequestStruct(name="demo", count=1),
    tags: list[str] = ["default"],
    ratio: float = 0.0,
    options: tuple[int, int] = (1, 2),
    config: dict[str, int] = {"mode": 1},
    secret: Ignore[str] = "hidden",
):
    pass


def typed_tool() -> int:
    return 1


def test_tool_parser_any_defaults_and_returns():
    parser = ToolParser()

    signature = parser.parse(fallback_tool)

    assert signature.return_type == "None"

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
    assert model_schema["properties"]["name"]["type"] == "string"
    assert model_schema["properties"]["count"]["type"] == "integer"
    assert "default" not in model_schema

    tags_schema = signature.parameters["tags"].schema
    assert tags_schema["default"] == ["default"]

    options_schema = signature.parameters["options"].schema
    assert options_schema["default"] == (1, 2)

    config_schema = signature.parameters["config"].schema
    assert config_schema["default"] == {"mode": 1}

    ratio_schema = signature.parameters["ratio"].schema
    assert ratio_schema["default"] == 0.0

    assert "secret" not in signature.parameters


    typed_signature = parser.parse(typed_tool)
    assert typed_signature.return_type == "int"

    generic_signature = parser.parse(generic_return_tool)
    assert generic_signature.return_type == repr(Annotated[int, "meta"])


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
