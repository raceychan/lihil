import re
from types import GenericAlias
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Generator,
    Literal,
    TypeGuard,
    TypeVar,
    get_args,
)
from typing import get_origin as ty_get_origin

from msgspec import Struct as Struct
from typing_extensions import TypeAliasType

from lihil.constant.status import Status

T = TypeVar("T")

LIHIL_RESPONSE_MARK = "__LIHIL_RESPONSE_MARK"
LIHIL_PARAM_MARK = "__LIHIL_PARAM_MARK"
LIHIL_PARAM_PATTERN = re.compile(r"__LIHIL_PARAM_MARK_(.*?)__")
LIHIL_RETURN_PATTERN = re.compile(r"__LIHIL_RESPONSE_MARK_(.*?)__")


def resp_mark(name: str) -> str:
    if name.startswith(LIHIL_RESPONSE_MARK):
        return name
    return f"{LIHIL_RESPONSE_MARK}_{name.upper()}__"


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


def extract_resp_type(mark: Any) -> "ResponseMark | None":
    if not isinstance(mark, str):
        return None

    match = LIHIL_RETURN_PATTERN.search(mark)

    if match:
        res = match.group(1)
        return res.lower()  # type: ignore
    return None


def is_resp_mark(m: Any) -> TypeGuard[TypeAliasType]:
    """
    marks that usually show up in endpoint return annotation
    """
    return is_lihil_marked(m, LIHIL_RESPONSE_MARK)


# ================ Request ================


# type AppState[T] = Annotated[T, "lihil_app_state"]


# ================ Response ================

TEXT_RETURN_MARK = resp_mark("text")
HTML_RETURN_MARK = resp_mark("html")
STREAM_RETURN_MARK = resp_mark("stream")
JSON_RETURN_MARK = resp_mark("json")
EMPTY_RETURN_MARK = resp_mark("empty")
JW_TOKEN_RETURN_MARK = resp_mark("jw_token")


Text = Annotated[str | bytes, TEXT_RETURN_MARK, "text/plain"]
HTML = Annotated[str | bytes, HTML_RETURN_MARK, "text/html"]
Stream = Annotated[
    AsyncGenerator[T, None] | Generator[T, None, None],
    STREAM_RETURN_MARK,
    "text/event-stream",
]
Json = Annotated[T, JSON_RETURN_MARK, "application/json"]


class Resp:
    """
    async def create_user() -> Annotated[Json[str], Resp(200)]
    """

    def __init__(self, code: Status):
        self.code = code


ResponseMark = Literal["text", "html", "stream", "json", "empty", "jw_token"]
