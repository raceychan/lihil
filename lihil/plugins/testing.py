from time import perf_counter
from typing import Any, Literal, Optional, Union
from urllib.parse import urlencode

from msgspec.json import decode as json_decode
from msgspec.json import encode as json_encode

from lihil.endpoint import Endpoint
from lihil.interface import ASGIApp, Base, Payload
from lihil.routing import Route


class Timer:
    __slots__ = ("_precision", "_start", "_end", "_cost")

    def __init__(self, precision: int = 6):
        self._precision = precision
        self._start, self._end, self._cost = 0, 0, 0

    def __repr__(self):
        return f"Timer(cost={self.cost}s, precison: {self._precision})"

    async def __aenter__(self):
        self._start = perf_counter()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        end = perf_counter()
        self._cost = round(end - self._start, self._precision)
        self._end = end

    @property
    def cost(self) -> float:
        return self._cost


class RequestResult(Base):
    """Represents the result of a request made to an ASGI application."""

    status_code: int
    headers: dict[str, str]
    body_chunks: list[bytes] = []
    _body: Optional[bytes] = None

    def __post_init__(self):
        self.headers = dict(self.headers)

    async def body(self) -> bytes:
        """Return the complete response body."""
        if self._body is None:
            self._body = b"".join(self.body_chunks)
            self.body_chunks = []
        return self._body

    async def text(self) -> str:
        """Return the response body as text."""
        body = await self.body()
        encoding = self._get_content_encoding() or "utf-8"
        return body.decode(encoding)

    async def json(self) -> Any:
        """Return the response body as parsed JSON."""
        result = await self.body()
        return json_decode(result)

    def _get_content_encoding(self) -> Optional[str]:
        """Extract encoding from Content-Type header."""
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            return content_type.split("charset=")[1].split(";")[0].strip()
        return None


class LocalClient:
    """A client for testing ASGI applications."""

    def __init__(
        self,
        client_type: Literal["http"] = "http",
        headers: dict[str, str] | None = None,
    ):
        """
        Initialize a test client for an ASGI application.

        Args:
            app: The ASGI application to test
            client_type: The type of client (currently only "http" is supported)
        """
        self.client_type = client_type
        self.base_headers: dict[str, str] = {
            "user-agent": "lihil-test-client",
        }
        if headers:
            self.base_headers.update(headers)

    async def request(
        self,
        app: ASGIApp,
        method: str,
        path: str,
        path_params: dict[str, Any] | None = None,
        query_params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        body: Optional[Union[bytes, str, dict[str, Any], Payload]] = None,
    ) -> RequestResult:
        """
        Make a request to the ASGI application.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: URL path
            query: Query parameters
            headers: HTTP headers
            body: Request body

        Returns:
            RequestResult object containing the response
        """
        # Prepare query string
        query_string = b""
        if query_params:
            query_string = urlencode(query_params).encode("utf-8")

        # Prepare headers
        request_headers = self.base_headers.copy()
        if headers:
            request_headers.update(headers)

        # Convert headers to ASGI format
        asgi_headers = [
            (k.lower().encode("utf-8"), v.encode("utf-8"))
            for k, v in request_headers.items()
        ]

        # Prepare body
        if body is not None:
            if isinstance(body, bytes):
                body_bytes = body
            else:
                body_bytes = json_encode(body)
        else:
            body_bytes = b""

        # Prepare ASGI scope
        scope = {
            "type": self.client_type,
            "method": method.upper(),
            "path": path,
            "path_params": path_params,
            "query_string": query_string,
            "headers": asgi_headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }

        # Collect response data
        response_status = None
        response_headers = []
        response_body_chunks: list[bytes] = []

        # Define send and receive functions
        async def receive():
            return {
                "type": "http.request",
                "body": body_bytes,
                "more_body": False,
            }

        async def send(message: dict[str, Any]):
            nonlocal response_status, response_headers

            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = message.get("headers", [])

            elif message["type"] == "http.response.body":
                response_body_chunks.append(message.get("body", b""))

        # Call the ASGI app
        await app(scope, receive, send)

        # Create and return result
        return RequestResult(
            status_code=response_status or 500,
            headers=response_headers,  # type: ignore
            body_chunks=response_body_chunks,
        )

    async def call_endpoint(
        self,
        ep: Endpoint[Any],
        path_params: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> RequestResult:

        encoded_path = (
            {k: str(v) for k, v in path_params.items()} if path_params else {}
        )

        resp = await self.request(
            app=ep,
            method=ep.method,
            path=ep.path,
            path_params=encoded_path,
            query_params=query_params,
            headers=headers,
            body=body,
        )
        return resp

    async def call_route(self, route: Route): ...

    # async def get(
    #     self,
    #     path: str,
    #     query: Optional[dict[str, Any]] = None,
    #     headers: Optional[dict[str, str]] = None,
    # ) -> RequestResult:
    #     """Make a GET request."""
    #     return await self.request("GET", path, query, headers)

    # async def post(
    #     self,
    #     path: str,
    #     body: Any = None,
    #     query: Optional[dict[str, Any]] = None,
    #     headers: Optional[dict[str, str]] = None,
    # ) -> RequestResult:
    #     """Make a POST request."""
    #     return await self.request("POST", path, query, headers, body)

    # async def put(
    #     self,
    #     path: str,
    #     body: Any = None,
    #     query: Optional[dict[str, Any]] = None,
    #     headers: Optional[dict[str, str]] = None,
    # ) -> RequestResult:
    #     """Make a PUT request."""
    #     return await self.request("PUT", path, query, headers, body)

    # async def delete(
    #     self,
    #     path: str,
    #     query: Optional[dict[str, Any]] = None,
    #     headers: Optional[dict[str, str]] = None,
    # ) -> RequestResult:
    #     """Make a DELETE request."""
    #     return await self.request("DELETE", path, query, headers)
