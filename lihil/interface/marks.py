from types import GenericAlias
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Generator,
    TypeVar,
    get_args,
    get_origin,
)

from msgspec import Struct
from typing_extensions import LiteralString, TypeAliasType, TypeGuard

from lihil.constant.status import Status

LIHIL_RESPONSE_MARK = "__LIHIL_RESPONSE_MARK"
LIHIL_PARAM_MARK = "__LIHIL_PARAM_MARK"


def resp_mark(name: str):
    return f"{LIHIL_RESPONSE_MARK}_{name.upper()}__"


def param_mark(name: str):
    return f"{LIHIL_PARAM_MARK}_{name.upper()}__"


def is_lihil_mark(m: Any, mark_prefix: str) -> bool:
    if isinstance(m, str):
        return m.startswith(mark_prefix)
    elif get_origin(m) is Annotated:
        meta_args = get_args(m)
        return any(is_lihil_mark(m, mark_prefix) for m in meta_args)
    elif isinstance(m, (TypeAliasType, GenericAlias)):
        value = getattr(m, "__value__", None)
        return is_lihil_mark(value, mark_prefix) if value else False
    else:
        return False


def is_resp_mark(m: Any) -> TypeGuard[TypeAliasType]:
    """
    marks that usually show up in endpoint return annotation
    """
    return is_lihil_mark(m, LIHIL_RESPONSE_MARK)


def is_param_mark(m: Any) -> bool:
    """
    marks that usually show up in endpoint signature and sub-deps
    """
    return is_lihil_mark(m, LIHIL_PARAM_MARK)


class Payload(Struct):
    """
    a structural type for request payloads
    we can have HeaderPayload, BodyPayload, etc.
    """


# ================ Request ================

QUERY_REQUEST_MARK = param_mark("query")
HEADER_REQUEST_MARK = param_mark("header")
BODY_REQUEST_MARK = param_mark("body")
PATH_REQUEST_MARK = param_mark("path")
USE_DEPENDENCY_MARK = param_mark("use")

T = TypeVar("T")
K = TypeVar("K", bound=LiteralString)

S = TypeVar("S", bound=Status | int)

Query = Annotated[T, QUERY_REQUEST_MARK]

Header = Annotated[T, K, HEADER_REQUEST_MARK]

Body = Annotated[T, BODY_REQUEST_MARK]

Path = Annotated[T, PATH_REQUEST_MARK]

Use = Annotated[T, USE_DEPENDENCY_MARK]

# ================ Response ================

TEXT_RETURN_MARK = resp_mark("text")
HTML_RETURN_MARK = resp_mark("html")
STREAM_RETURN_MARK = resp_mark("stream")
JSON_RETURN_MARK = resp_mark("json")
RESP_RETURN_MARK = resp_mark("resp")

# type TextType = str | bytes
Text = Annotated[str | bytes, TEXT_RETURN_MARK, "text/plain"]
HTML = Annotated[str | bytes, HTML_RETURN_MARK, "text/html"]
# TODO: T
Stream = Annotated[
    AsyncGenerator[T, None] | Generator[T, None, None],
    STREAM_RETURN_MARK,
    "text/event-stream",
]
Json = Annotated[T, JSON_RETURN_MARK, "application/json"]
Resp = Annotated[T, S, RESP_RETURN_MARK]
