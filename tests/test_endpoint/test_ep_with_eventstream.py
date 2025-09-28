import re
from typing import Callable

import pytest

from lihil import SSE, EventStream, Lihil, Route
from lihil.vendors import TestClient

# Matches a single SSE line
SSE_LINE_PATTERN = re.compile(
    r"""^(?:
        (?:data|event|id):[ \t]?.*   # data/event/id lines
      | retry:[ \t]*\d+              # retry must be integer
      | :.*                          # comment line
      | $                            # blank line
    )$""",
    re.VERBOSE,
)


def is_valid_sse(message: str) -> bool:
    """Validate if a given string is a valid SSE message."""
    if not message.endswith("\n\n"):
        return False
    lines = message.rstrip("\n").splitlines()
    return all(SSE_LINE_PATTERN.match(line) for line in lines)


async def test_endpoint_returns_sse_struct_eventstream(
    test_client: Callable[[Lihil], TestClient],
):
    async def sse_struct_endpoint() -> EventStream:
        yield SSE(data={"message": "Hello, SSE!"}, event="start")
        for i in range(2):
            yield SSE(data={"count": i}, event="update", id=str(i))
        yield SSE(data={"message": "Goodbye!"}, event="close", id="final")

    route = Route("/sse-struct")
    route.get(sse_struct_endpoint)
    app = Lihil(route)
    app._setup()

    client = test_client(app)
    response = client.get("/sse-struct")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    lines: list[str] = []
    for line in response.iter_lines():
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode()
        lines.append(line)

    message = "\n".join(lines) + "\n\n"
    assert is_valid_sse(message)
    assert "event: start" in message
    assert 'data: {"message":"Hello, SSE!"}' in message
    for i in range(2):
        assert "event: update" in message
        assert f"id: {i}" in message
        assert f'data: {{"count":{i}}}' in message
    assert "event: close" in message
    assert 'data: {"message":"Goodbye!"}' in message


    # TypedDict (SSEDict) support is removed; only SSE struct endpoints are tested.
