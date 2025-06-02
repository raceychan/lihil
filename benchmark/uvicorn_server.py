from uvicorn._types import ASGIReceiveCallable, ASGISendCallable, Scope

# from .share import endpoint


async def app(
    scope: Scope,
    receive: ASGIReceiveCallable,
    send: ASGISendCallable,
):
    """
    ASGI application that handles user data.
    """
    if scope["type"] != "http":
        return

    # Receive the HTTP body
    body: bytes = b""

    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body", False):
            break

    # res = endpoint(body)
    res = "hello, world".encode()
    content_lengh = str(len(res)).encode()

    # Send response headers
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": (
                (b"content-type", b"application/json"),
                (b"content-length", content_lengh),
            ),
        }
    )

    # Send response body
    await send(
        {
            "type": "http.response.body",
            "body": res,
        }
    )
