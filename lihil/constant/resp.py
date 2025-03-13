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


def generate_static_resp(content: bytes, content_type: str, charset: str) -> bytes:
    """
    generate a http response from content
    that can directly be returned by `transport.write`

    pretty much a simpler version of starlette.Response
    """

    status_line = b"HTTP/1.1 200 OK\r\n"

    # Using f-strings to directly construct the headers
    headers = (
        f"content-length: {len(content)}\r\n"
        f"content-type: {content_type}; {charset=}\r\n"
    ).encode("latin-1") + b"\r\n"

    # Combine the status line, headers, and content to form the full response
    return status_line + headers + content
