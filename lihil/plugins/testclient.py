from time import perf_counter
from typing import Any, Literal, MutableMapping, Optional, Union
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

        async def send(message: MutableMapping[str, Any]):
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

    async def call_route(
        self,
        route: Route,
        method: HTTP_METHODS,
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> RequestResult:
        # Ensure the route has the endpoint for the requested method
        if method not in route.endpoints:
            raise ValueError(f"Route does not support {method} method")

        # Get the actual path with path parameters substituted
        actual_path = route.path
        if path_params:
            # Replace path parameters in the URL
            for param_name, param_value in path_params.items():
                pattern = f"{{{param_name}}}"
                actual_path = actual_path.replace(pattern, str(param_value))

        # Make the request
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
        await self._initialize_app_lifespan(app)
        return await self.request(
            app=app,
            method=method,
            path=path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            body=body,
        )

    async def _initialize_app_lifespan(self, app: ASGIApp) -> None:
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
