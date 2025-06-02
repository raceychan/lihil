from inspect import iscoroutinefunction
from time import perf_counter
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Literal,
    MutableMapping,
    Optional,
    Union,
)
from urllib.parse import urlencode
from uuid import uuid4

from msgspec.json import decode as json_decode
from msgspec.json import encode as json_encode
from pydantic import BaseModel, TypeAdapter
from typing_extensions import Unpack

from lihil.errors import LihilError
from lihil.interface import HTTP_METHODS, ASGIApp, Base, Payload, R
from lihil.routing import Endpoint, IEndpointProps, Route


class Timer:
    __slots__ = ("_precision", "_start", "_end", "_cost")

    def __init__(self, precision: int = 6):
        self._precision = precision
        self._start, self._end, self._cost = 0, 0, 0

    def __repr__(self):
        return f"Timer(cost={self.cost}s, precison: {self._precision})"

    def __aenter__(self):
        self._start = perf_counter()
        return self

    def __aexit__(self, exc_type: type[Exception], exc: Exception, tb: Any):
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
        *,
        client_type: Literal["http"] = "http",
        headers: dict[str, str] | None = None,
    ):
        self.client_type = client_type
        self.base_headers: dict[str, str] = {
            "user-agent": "lihil-test-client",
        }
        if headers:
            self.base_headers.update(headers)

    def update_headers(self, headers: dict[str, str]):
        self.base_headers.update(headers)

    async def submit_form(
        self,
        app: ASGIApp,
        form_data: dict[str, Any],
        method: HTTP_METHODS | None = None,
        path: str | None = None,
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> RequestResult:

        boundary = f"----WebKitFormBoundary{uuid4().hex}"
        content_type = f"multipart/form-data; boundary={boundary}"
        # Prepare headers
        if headers is None:
            headers = {}
        headers["Content-Type"] = content_type

        # Build multipart form data
        body_parts: list[str | bytes] = []

        for field_name, field_value in form_data.items():
            # Start boundary
            body_parts.append(f"--{boundary}\r\n")

            if isinstance(field_value, str):
                # Simple text field
                body_parts.append(
                    f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'
                )
                body_parts.append(f"{field_value}\r\n")

            elif isinstance(field_value, bytes):
                # Raw bytes field
                body_parts.append(
                    f'Content-Disposition: form-data; name="{field_name}"\r\n\r\n'
                )
                body_parts.append(field_value)
                body_parts.append(b"\r\n")

            elif isinstance(field_value, tuple):
                # File upload: (filename, file_bytes, content_type)
                filename, file_bytes, file_content_type = field_value + (None,) * (
                    3 - len(field_value)
                )

                body_parts.append(
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
                )

                if file_content_type:
                    body_parts.append(f"Content-Type: {file_content_type}\r\n\r\n")
                else:
                    body_parts.append("\r\n")

                body_parts.append(file_bytes)
                body_parts.append(b"\r\n")

        # End boundary
        body_parts.append(f"--{boundary}--\r\n")

        # Combine all parts into single body
        body = b""
        for part in body_parts:
            if isinstance(part, str):
                body += part.encode("utf-8")
            else:
                body += part

        return await self.__call__(
            app=app,
            method=method,
            path=path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            body=body,
        )

    def _encode_header(self, headers: dict[str, str]) -> list[tuple[bytes, bytes]]:
        return [
            (k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in headers.items()
        ]

    def _encode_body(self, body: Any) -> bytes:
        if body is not None:
            if isinstance(body, bytes):
                body_bytes = body
            elif isinstance(body, BaseModel):
                body_bytes = TypeAdapter(type(body)).dump_json(body)
            else:
                body_bytes = json_encode(body)
        else:
            body_bytes = b""

        return body_bytes

    async def request(
        self,
        app: ASGIApp,
        method: str,
        path: str,
        path_params: dict[str, Any] | None = None,
        query_string: bytes | None = None,
        query_params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        multi_headers: list[tuple[str, str]] | None = None,
        body: Union[bytes, str, dict[str, Any], Payload] | None = None,
        stream: bool = False,
    ) -> RequestResult:
        # Prepare query string
        query_string = query_string if query_string is not None else b""

        if query_params:
            query_string = query_string + urlencode(query_params).encode("utf-8")

        # Prepare headers
        request_headers = self.base_headers.copy()
        if headers:
            request_headers.update(headers)

        if path_params:
            path_template = path
            for param_name, param_value in path_params.items():
                pattern = f"{{{param_name}}}"
                path_template = path_template.replace(pattern, str(param_value))

            path = path_template

        # Convert headers to ASGI format
        asgi_headers = self._encode_header(request_headers)
        if multi_headers:
            for name, value in multi_headers:
                asgi_headers.append((name.encode("utf-8"), value.encode("utf-8")))

        # Prepare body
        body_bytes = self._encode_body(body)

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
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> RequestResult:
        """
        TODO: override ep dependencies
        1. make a new graph, merge ep.graph
        2. override in the new graph
        3. set ep.graph = new graph
        4. reset ep.graph to old graph
        """

        if not ep.is_setup:
            await ep.route.setup()

        resp = await self.request(
            app=ep,
            method=ep.method,
            path=ep.path,
            path_params=path_params,
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

        await route.setup()

        resp = await self.request(
            app=route,
            method=method,
            path=route.path,
            path_params=path_params,
            query_params=query_params,
            headers=headers,
            body=body,
        )
        return resp

    async def call_app(
        self,
        app: ASGIApp,
        method: HTTP_METHODS,
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
            prefix, type_, result = message["type"].split(".")
            if result == "failed":
                raise LihilError(message["message"])
            sent_messages.append(message)

        await app(scope, receive, send)

    async def __call__(
        self,
        app: ASGIApp | Callable[..., None],
        method: HTTP_METHODS | None = None,
        path: str | None = None,
        path_params: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> RequestResult:
        if isinstance(app, Endpoint):
            return await self.call_endpoint(
                app,
                path_params=path_params,
                query_params=query_params,
                body=body,
                headers=headers,
            )
        elif isinstance(app, Route):
            assert method, "method is required to call route"
            return await self.call_route(
                app,
                method=method,
                path_params=path_params,
                query_params=query_params,
                body=body,
                headers=headers,
            )

        elif callable(app) and iscoroutinefunction(app.__call__):
            assert method, "method is required to call app"
            assert path, "path is required to call app"
            return await self.call_app(
                app,
                method=method,
                path=path,
                path_params=path_params,
                query_params=query_params,
                body=body,
                headers=headers,
            )
        else:
            raise TypeError(f"Not supported type {app}")

    async def make_endpoint(
        self,
        f: Callable[..., R],
        method: HTTP_METHODS = "GET",
        path: str = "",
        **props: Unpack[IEndpointProps],
    ) -> Endpoint[R]:
        route = Route(path)
        route.add_endpoint(method, func=f, **props)
        await route.setup()
        return route.get_endpoint(method)
