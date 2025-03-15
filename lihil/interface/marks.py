from types import GenericAlias
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Generator,
    LiteralString,
    TypeAliasType,
    TypeGuard,
    get_args,
    get_origin,
)

from msgspec import Struct

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

type Query[T] = Annotated[T, QUERY_REQUEST_MARK]

type Header[T, K: LiteralString] = Annotated[T, K, HEADER_REQUEST_MARK]

type Body[T] = Annotated[T, BODY_REQUEST_MARK]

type Path[T] = Annotated[T, PATH_REQUEST_MARK]

type Use[T] = Annotated[T, USE_DEPENDENCY_MARK]

# ================ Response ================

TEXT_RETURN_MARK = resp_mark("text")
HTML_RETURN_MARK = resp_mark("html")
STREAM_RETURN_MARK = resp_mark("stream")
JSON_RETURN_MARK = resp_mark("json")
RESP_RETURN_MARK = resp_mark("resp")

# type TextType = str | bytes
type Text = Annotated[str | bytes, TEXT_RETURN_MARK, "text/plain"]
type HTML = Annotated[str | bytes, HTML_RETURN_MARK, "text/html"]
# TODO: T
type Stream[T] = Annotated[
    AsyncGenerator[T, None] | Generator[T, None, None],
    STREAM_RETURN_MARK,
    "text/event-stream",
]
type Json[T] = Annotated[T, JSON_RETURN_MARK, "application/json"]
type Resp[T, S: Status | int] = Annotated[T, S, RESP_RETURN_MARK]
