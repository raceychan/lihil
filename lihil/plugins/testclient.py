from time import perf_counter
from typing import Any, AsyncIterator, Literal, MutableMapping, Optional, Union
from urllib.parse import urlencode

from msgspec.json import decode as json_decode
from msgspec.json import encode as json_encode

from lihil.endpoint import Endpoint
from lihil.interface import HTTP_METHODS, ASGIApp, Base, Payload
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

    async def __aexit__(self, exc_type: type[Exception], exc: Exception, tb: Any):
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
    _stream_complete: bool = False

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

    async def stream(self) -> AsyncIterator[bytes]:
        """
        Return an async iterator for streaming response chunks.
        This is useful for server-sent events or other streaming responses.
        """
        # First yield any chunks we've already received
        for chunk in self.body_chunks:
            yield chunk

        # Mark that we've consumed all chunks
        self.body_chunks = []
        self._stream_complete = True

    async def stream_text(self) -> AsyncIterator[str]:
        """Return an async iterator for streaming response chunks as text."""
        encoding = self._get_content_encoding() or "utf-8"
        async for chunk in self.stream():
            yield chunk.decode(encoding)

    async def stream_json(self) -> AsyncIterator[Any]:
        """Return an async iterator for streaming response chunks as JSON objects."""
        async for chunk in self.stream_text():
            # Skip empty chunks
            if not chunk.strip():
                continue

            # For JSON streaming, each line should be a valid JSON object
            for line in chunk.splitlines():
                if line.strip():
                    yield json_decode(line.encode())

    def _get_content_encoding(self) -> Optional[str]:
        """Extract encoding from Content-Type header."""
        content_type = self.headers.get("content-type", "")
        if "charset=" in content_type:
            return content_type.split("charset=")[1].split(";")[0].strip()
        return None

    @property
    def is_chunked(self) -> bool:
        """Check if the response is using chunked transfer encoding."""
        return self.headers.get("transfer-encoding", "").lower() == "chunked"

    @property
    def is_streaming(self) -> bool:
        """Check if the response is a streaming response."""
        return self.is_chunked


class LocalClient:
    """A client for testing ASGI applications."""

    def __init__(
        self,
        client_type: Literal["http"] = "http",
        headers: dict[str, str] | None = None,
    ):
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
        stream: bool = False,
    ) -> RequestResult:
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
            "asgi": {"spec_version": "2.4"},
        }

        # Collect response data
        response_status = None
        response_headers: list[tuple[bytes, bytes]] = []
        response_body_chunks: list[bytes] = []
        is_streaming = False

        # Define send and receive functions
        async def receive():
            return {
                "type": "http.request",
                "body": body_bytes,
                "more_body": False,
            }

        async def send(message: MutableMapping[str, Any]):
            nonlocal response_status, response_headers, is_streaming

            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = message.get("headers", [])

                # Check if this is a streaming response
                for name, value in response_headers:
                    if (
                        name.lower() == b"transfer-encoding"
                        and value.lower() == b"chunked"
                    ):
                        is_streaming = True

            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk:
                    response_body_chunks.append(chunk)

                # If streaming is requested but we're not collecting more chunks, return early
                if stream and not message.get("more_body", False):
                    return

        # Call the ASGI app
        await app(scope, receive, send)

        # Convert headers to dict format
        headers_dict: dict[str, str] = {}
        for name, value in response_headers:
            name_str = name.decode("latin1").lower()
            value_str = value.decode("latin1")
            headers_dict[name_str] = value_str

        # Create and return result
        return RequestResult(
            status_code=response_status or 500,
            headers=headers_dict,
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
        """
        # TODO: override ep dependencies
        1. make a new graph, merge ep.graph
        2. override in the new graph
        3. set ep.graph = new graph
        4. reset ep.graph to old graph
        """

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

    async def call_route(
        self,
        route: Route,
        method: HTTP_METHODS,
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> RequestResult:
        """
        # TODO: override route dependencies
        1. make a new graph, merge route.graph
        2. override in the new graph
        3. set route.graph = new graph
        4. reset route.graph to old graph
        """

        actual_path = route.path
        if path_params:
            for param_name, param_value in path_params.items():
                pattern = f"{{{param_name}}}"
                actual_path = actual_path.replace(pattern, str(param_value))

        route.setup()

        resp = await self.request(
            app=route,
            method=method,
            path=actual_path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            body=body,
        )
        return resp

    async def call_app(
        self,
        app: ASGIApp,
        method: str,
        path: str,
        path_params: dict[str, Any] | None = None,
        query_params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        body: Optional[Union[bytes, str, dict[str, Any], Payload]] = None,
    ) -> RequestResult:
        await self.send_app_lifespan(app)
        return await self.request(
            app=app,
            method=method,
            path=path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            body=body,
        )

    async def send_app_lifespan(self, app: ASGIApp) -> None:
        """
        Helper function to initialize a Lihil app by sending lifespan events.
        This ensures the app's call_stack is properly set up before testing routes.
        """
        scope = {"type": "lifespan"}
        receive_messages = [{"type": "lifespan.startup"}]
        receive_index = 0

        async def receive():
            nonlocal receive_index
            if receive_index < len(receive_messages):
                message = receive_messages[receive_index]
                receive_index += 1
                return message
            return {"type": "lifespan.shutdown"}

        sent_messages: list[dict[str, str]] = []

        async def send(message: dict[str, str]) -> None:
            sent_messages.append(message)

        await app(scope, receive, send)
