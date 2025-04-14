from typing import Any

from starlette.responses import PlainTextResponse

from lihil.constant.status import METHOD_NOT_ALLOWED, NOT_FOUND, STATUS_CODE
from lihil.interface.asgi import IReceive, IScope, ISend

NOT_FOUND_RESP = PlainTextResponse("Not Found", status_code=STATUS_CODE[NOT_FOUND])
METHOD_NOT_ALLOWED_RESP = PlainTextResponse(
    "Method Not Allowed", status_code=STATUS_CODE[METHOD_NOT_ALLOWED]
)


INTERNAL_ERROR_HEADER = {
    "type": "http.response.start",
    "status": 500,
    "headers": [
        (b"content-type", b"text/plain; charset=utf-8"),
        (b"content-length", b"21"),
        (b"connection", b"close"),
    ],
}
INTERNAL_ERROR_BODY = {
    "type": "http.response.body",
    "body": b"Internal Server Error",
    "more_body": False,
}


async def InternalErrorResp(_: IScope, __: IReceive, send: ISend) -> None:
    await send(INTERNAL_ERROR_HEADER)
    await send(INTERNAL_ERROR_BODY)


SERVICE_UNAVAILABLE_HEADER = {
    "type": "http.response.start",
    "status": 503,
    "headers": [
        (b"content-type", b"text/plain; charset=utf-8"),
        (b"content-length", b"19"),
        (b"connection", b"close"),
    ],
}
SERVICE_UNAVAILABLE_BODY = {
    "type": "http.response.body",
    "body": b"Service Unavailable",
    "more_body": False,
}


async def ServiceUnavailableResp(send: ISend) -> None:
    await send(SERVICE_UNAVAILABLE_HEADER)
    await send(SERVICE_UNAVAILABLE_BODY)


def lhlserver_static_resp(
    content: bytes, content_type: str = "text/plain", charset: str = "utf-8"
) -> bytes:
    """
    a static route that requires our own server to run
    """

    status_line = b"HTTP/1.1 200 OK\r\n"

    # Using f-strings to directly construct the headers
    headers = (
        f"content-length: {len(content)}\r\n"
        f"content-type: {content_type}; {charset=}\r\n"
    ).encode("latin-1") + b"\r\n"

    # Combine the status line, headers, and content to form the full response
    return status_line + headers + content


def uvicorn_static_resp(
    content: bytes, status: int, content_type: str, charset: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    "a static route that works with uvicorn"

    content_length = str(len(content))
    content_type = f"{content_type}; charset={charset}"
    headers: list[tuple[bytes, bytes]] = [
        (b"content-length", content_length.encode("latin-1")),
        (b"content-type", content_type.encode("latin-1")),
    ]
    start_msg = {"type": "http.response.start", "status": status, "headers": headers}
    body_msg = {"type": "http.response.body", "body": content}
    return start_msg, body_msg
