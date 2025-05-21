import re
from typing import Annotated, Any, AsyncGenerator, Generator, Literal, TypeVar

from msgspec import Struct as Struct

T = TypeVar("T")

LIHIL_RESPONSE_MARK = "__LIHIL_RESPONSE_MARK"
LIHIL_RETURN_PATTERN = re.compile(r"__LIHIL_RESPONSE_MARK_(.*?)__")


def resp_mark(name: str) -> str:
    if name.startswith(LIHIL_RESPONSE_MARK):
        return name
    return f"{LIHIL_RESPONSE_MARK}_{name.upper()}__"


def extract_resp_type(mark: Any) -> "ResponseMark | None":
    if not isinstance(mark, str):
        return None

    match = LIHIL_RETURN_PATTERN.search(mark)

    if match:
        res = match.group(1)
        return res.lower()  # type: ignore
    return None


# ================ Response ================

TEXT_RETURN_MARK = resp_mark("text")
HTML_RETURN_MARK = resp_mark("html")
STREAM_RETURN_MARK = resp_mark("stream")
JSON_RETURN_MARK = resp_mark("json")
EMPTY_RETURN_MARK = resp_mark("empty")


Text = Annotated[str | bytes, TEXT_RETURN_MARK, "text/plain"]
HTML = Annotated[str | bytes, HTML_RETURN_MARK, "text/html"]
Stream = Annotated[
    AsyncGenerator[T, None] | Generator[T, None, None],
    STREAM_RETURN_MARK,
    "text/event-stream",
]
Json = Annotated[T, JSON_RETURN_MARK, "application/json"]

ResponseMark = Literal["text", "html", "stream", "json", "empty", "jw_token"]
