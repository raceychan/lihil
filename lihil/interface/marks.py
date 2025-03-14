from types import GenericAlias
from typing import Annotated, Any, LiteralString, TypeAliasType, get_args, get_origin, TypeGuard

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
type Query[T] = Annotated[T, QUERY_REQUEST_MARK]

HEADER_REQUEST_MARK = param_mark("header")
type Header[T, K: LiteralString] = Annotated[T, K, HEADER_REQUEST_MARK]

BODY_REQUEST_MARK = param_mark("body")
type Body[T] = Annotated[T, BODY_REQUEST_MARK]

PATH_REQUEST_MARK = param_mark("path")
type Path[T] = Annotated[T, PATH_REQUEST_MARK]

USE_DEPENDENCY_MARK = param_mark("use")
type Use[T] = Annotated[T, USE_DEPENDENCY_MARK]

# ================ Response ================

TEXT_RETURN_MARK = resp_mark("text")
type Text = Annotated[str | bytes, TEXT_RETURN_MARK, "text/plain"]

HTML_RETURN_MARK = resp_mark("html")
type HTML = Annotated[str | bytes, HTML_RETURN_MARK, "text/html"]


STREAM_RETURN_MARK = resp_mark("stream")
type Stream = Annotated[bytes, STREAM_RETURN_MARK, "text/event-stream"]

JSON_RETURN_MARK = resp_mark("json")
type Json[_] = Annotated[Any, JSON_RETURN_MARK, "application/json"]

RESP_RETURN_MARK = resp_mark("resp")
type Resp[T, S: Status | int] = Annotated[T, S, RESP_RETURN_MARK]
