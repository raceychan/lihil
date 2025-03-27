from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Generator,
    LiteralString,
    TypeAliasType,
    TypeGuard,
    Union,
    get_args,
)
from typing import get_origin as ty_get_origin

from msgspec import Struct as Struct

from lihil.constant.status import Status
from lihil.utils.typing import deannotate

LIHIL_RESPONSE_MARK = "__LIHIL_RESPONSE_MARK"
LIHIL_PARAM_MARK = "__LIHIL_PARAM_MARK"


def get_origin_pro[T](
    type_: type[T] | UnionType | GenericAlias | TypeAliasType,
    metas: list[Any] | None = None,
) -> tuple[type, list[Any]] | tuple[type, None]:
    """
    type MyTypeAlias = Annotated[Query[int], CustomEncoder]
    type NewAnnotated = Annotated[MyTypeAlias, "aloha"]


    get_param_origin(Body[SamplePayload | None]) -> (SamplePayload | None, [BODY_REQUEST_MARK])
    get_param_origin(MyTypeAlias) -> (int, [QUERY_REQUEST_MARK, CustomEncoder])
    get_param_origin(NewAnnotated) -> (int, [QUERY_REQUEST_MARK, CustomEncoder])
    """

    if isinstance(type_, TypeAliasType):
        return get_origin_pro(type_.__value__, None)
    elif current_origin := ty_get_origin(type_):
        if current_origin is Annotated:
            annt_type, local_metas = deannotate(type_)
            if local_metas:
                if metas is None:
                    metas = []
                metas.extend(local_metas)
            return get_origin_pro(annt_type, metas)
        elif isinstance(current_origin, TypeAliasType):
            dealiased = type_.__value__
            if (als_args := get_args(dealiased)) and (ty_args := get_args(type_)):
                ty_type, *local_args = ty_args + als_args[len(ty_args) :]
                if ty_get_origin(dealiased) is Annotated:
                    if metas:
                        new_metas = metas + local_args
                    else:
                        new_metas = local_args

                    return get_origin_pro(ty_type, new_metas)
            return get_origin_pro(dealiased, metas)
        elif current_origin is UnionType:
            union_args = get_args(type_)
            utypes: list[type] = []
            umetas: list[Any] = []
            for uarg in union_args:
                utype, umeta = get_origin_pro(uarg, metas)
                utypes.append(utype)
                if umeta:
                    for i in umeta:
                        if i in umetas:
                            continue
                        umetas.append(i)

            if not umetas:
                return get_origin_pro(Union[*utypes], metas)

            if not metas:
                metas = umetas
            else:
                for i in umetas:
                    if i in metas:
                        continue
                    metas.append(i)
            return get_origin_pro(Union[*utypes], metas)
        else:
            return (type_, metas)
    else:
        return (type_, metas)


def lhl_get_origin(annt: Any) -> Any:
    "a extended get origin that handles TypeAliasType"
    if is_marked_param(annt):
        return ty_get_origin(annt)
    elif isinstance(annt, TypeAliasType):
        while isinstance(annt, TypeAliasType):
            annt = annt.__value__
        return annt
    return ty_get_origin(annt)


def resp_mark(name: str):
    return f"{LIHIL_RESPONSE_MARK}_{name.upper()}__"


def param_mark(name: str):
    return f"{LIHIL_PARAM_MARK}_{name.upper()}__"


def is_lihil_marked(m: Any, mark_prefix: str) -> bool:
    if isinstance(m, str):
        return m.startswith(mark_prefix)
    elif ty_get_origin(m) is Annotated:
        meta_args = get_args(m)
        return any(is_lihil_marked(m, mark_prefix) for m in meta_args)
    elif isinstance(m, (TypeAliasType, GenericAlias)):
        value = getattr(m, "__value__", None)
        return is_lihil_marked(value, mark_prefix) if value else False
    else:
        return False


def is_resp_mark(m: Any) -> TypeGuard[TypeAliasType]:
    """
    marks that usually show up in endpoint return annotation
    """
    return is_lihil_marked(m, LIHIL_RESPONSE_MARK)


def is_param_mark(m: Any) -> bool:
    """
    marks that usually show up in endpoint signature and sub-deps
    """
    return is_lihil_marked(m, LIHIL_PARAM_MARK)


def is_marked_param(m: Any) -> bool:
    return is_param_mark(m) or is_resp_mark(m)


# ================ Request ================

QUERY_REQUEST_MARK = param_mark("query")
HEADER_REQUEST_MARK = param_mark("header")
BODY_REQUEST_MARK = param_mark("body")
FORM_REQUEST_MARK = param_mark("form")
PATH_REQUEST_MARK = param_mark("path")
USE_DEPENDENCY_MARK = param_mark("use")

type Query[T] = Annotated[T, QUERY_REQUEST_MARK]
type Header[T, K: LiteralString] = Annotated[T, K, HEADER_REQUEST_MARK]
type Body[T] = Annotated[T, BODY_REQUEST_MARK]
type Form[T] = Annotated[T, FORM_REQUEST_MARK]
type Path[T] = Annotated[T, PATH_REQUEST_MARK]
type Use[T] = Annotated[T, USE_DEPENDENCY_MARK]

# ================ Response ================

TEXT_RETURN_MARK = resp_mark("text")
HTML_RETURN_MARK = resp_mark("html")
STREAM_RETURN_MARK = resp_mark("stream")
JSON_RETURN_MARK = resp_mark("json")
RESP_RETURN_MARK = resp_mark("resp")
EMPTY_RETURN_MARK = resp_mark("empty")

type Text = Annotated[str | bytes, TEXT_RETURN_MARK, "text/plain"]
type HTML = Annotated[str | bytes, HTML_RETURN_MARK, "text/html"]
type Stream[T] = Annotated[
    AsyncGenerator[T, None] | Generator[T, None, None],
    STREAM_RETURN_MARK,
    "text/event-stream",
]
type Json[T] = Annotated[T, JSON_RETURN_MARK, "application/json"]
type Resp[T, S: Status | int] = Annotated[T, S, RESP_RETURN_MARK]
