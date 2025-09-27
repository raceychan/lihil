import re
from typing import Callable

import pytest

from lihil import SSE, EventStream, Lihil, Route
from lihil.interface import Record
from lihil.interface.struct import encode_sse
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
    """
    Validate if a given string is a valid SSE message using regex.
    """
    # Must end with a blank line (double newline)
    if not message.endswith("\n\n"):
        return False

    # Strip only the final blank line (otherwise split will give extra empty string)
    lines = message.rstrip("\n").splitlines()

    for line in lines:
        if not SSE_LINE_PATTERN.match(line):
            return False

    return True


# ------


# @pytest.fixture
# def lc() -> LocalClient:
#     return LocalClient()


class Person(Record):
    name: str
    age: int


def test_sse():
    sse1 = SSE(data=Person(name="Alice", age=30), event="start", id="1", retry=5000)

    sse_str = encode_sse(sse1).decode()
    assert is_valid_sse(sse_str)

    sse2 = SSE(data=Person(name="Bob", age=25))
    sse_str2 = encode_sse(sse2).decode()
    assert is_valid_sse(sse_str2)


def test_sse_multiline_data():
    """Data containing new lines should be split into multiple data: lines."""
    payload = "line1\nline2\nline3"
    sse = SSE(data=payload, event="multi", id="42")
    sse_str = encode_sse(sse).decode()

    assert is_valid_sse(sse_str)
    assert sse_str.endswith("\n\n")
    # Ensure each line of payload becomes its own data: line
    assert "data: line1\ndata: line2\ndata: line3" in sse_str


def test_sse_encodes_json_payload():
    """Non-string payloads are JSON-encoded as a single data: line."""
    sse = SSE(data=Person(name="Carol", age=27))
    sse_str = encode_sse(sse).decode()

    assert is_valid_sse(sse_str)
    # msgspec.json encodes compact JSON without spaces
    assert 'data: {"name":"Carol","age":27}' in sse_str


def test_sse_invalid_retry_non_integer():
    """retry must be an integer; non-integers are invalid."""
    invalid = "retry: abc\n\n"
    assert not is_valid_sse(invalid)


def test_sse_invalid_missing_final_blank_line():
    """A valid SSE message must end with a blank line (\n\n)."""
    # Construct a nearly-correct message but missing the final blank line
    almost = "event: test\ndata: hello\n"  # only one trailing newline
    assert not is_valid_sse(almost)


def test_sse_invalid_unknown_field():
    """Lines must start with data/event/id/retry or be comments; others invalid."""
    invalid = "badfield: 123\n\n"
    assert not is_valid_sse(invalid)


async def test_endpoint_with_sse(test_client: Callable[[Lihil], TestClient]):

    async def sse_endpoint() -> EventStream:
        yield SSE(data={"message": "Hello, SSE!"}, event="start")

        for i in range(3):
            yield SSE(data={"count": i}, event="update", id=str(i))
        yield SSE(data={"message": "Goodbye!"}, event="close", id="final")

    sse_route = Route("/sse")
    sse_route.get(sse_endpoint)
    lhl = Lihil(sse_route)
    lhl._setup()

    client = test_client(lhl)

    response = client.get("/sse")
    assert response.status_code == 200

    # Read the streamed response line by line
    lines: list[str] = []
    for line in response.iter_lines():
        if line:  # skip empty lines
            lines.append(line)

    # Join lines back into a single message for validation
    message = "\n".join(lines) + "\n\n"  # add final blank line
    assert is_valid_sse(message)

    # Check that expected events are present
    assert "event: start" in message
    assert 'data: {"message":"Hello, SSE!"}' in message
    for i in range(3):
        assert f"event: update" in message
        assert f"id: {i}" in message
        assert f'data: {{"count":{i}}}' in message
    assert "event: close" in message
    assert 'data: {"message":"Goodbye!"}' in message
