# import asyncio
# import contextlib
# import http
# import re
# import signal
# import socket
# import sys
# import threading
# from asyncio import Queue
# from asyncio.events import TimerHandle
# from collections import deque
# from collections.abc import Generator
# from types import FrameType
# from typing import Any, Literal, Protocol, cast
# from urllib.parse import unquote as url_esapce

# from httptools import HttpRequestParser  # type: ignore
# from httptools import parse_url  # type: ignore
# from httptools import HttpParserError, HttpParserUpgrade
# from loguru import logger
# from uvloop import EventLoopPolicy

# from lihil.config import ServerConfig
# from lihil.constant.resp import ServiceUnavailableResp
# from lihil.interface.asgi import ASGIApp, HTTPScope, LihilInterface, Message

# HANDLED_SIGNALS = (
#     signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
#     signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
# )

# STATE_TRANSITION_ERROR = "Got invalid state transition on lifespan protocol."

# HEADER_RE = re.compile(b'[\x00-\x1f\x7f()<>@,;:[]={} \t\\"]')
# HEADER_VALUE_RE = re.compile(b"[\x00-\x08\x0a-\x1f\x7f]")


# def _get_status_line(status_code: int):
#     try:
#         phrase = http.HTTPStatus(status_code).phrase.encode()
#     except ValueError:
#         phrase = b""

#     parts: list[bytes] = [
#         b"HTTP/1.1 ",
#         str(status_code).encode(),
#         b" ",
#         phrase,
#         b"\r\n",
#     ]

#     return b"".join(parts)


# # Pre-compute status lines at module load time
# STATUS_LINE: dict[int, bytes] = {
#     status_code: _get_status_line(status_code) for status_code in range(100, 600)
# }


# class Parser(Protocol):
#     def get_http_version(self) -> str: ...

#     def should_keep_alive(self) -> bool: ...

#     def should_upgrade(self) -> bool: ...

#     def feed_data(self, data: bytes): ...

#     def get_method(self) -> bytes: ...

#     def set_dangerous_leniencies(self, lenient_data_after_close: bool): ...


# class ClientDisconnected(OSError): ...


# class LifespanOn:
#     def __init__(self, app, version) -> None:
#         self.app = app
#         self.version = version
#         self.startup_event = asyncio.Event()
#         self.shutdown_event = asyncio.Event()
#         self.receive_queue: Queue[Message] = asyncio.Queue()
#         self.error_occured = False
#         self.startup_failed = False
#         self.shutdown_failed = False
#         self.should_exit = False
#         self.state: dict[str, Any] = {}

#     async def startup(self) -> None:
#         logger.info("Waiting for application startup.")

#         loop = asyncio.get_event_loop()
#         main_lifespan_task = loop.create_task(self.main())  # noqa: F841
#         # Keep a hard reference to prevent garbage collection
#         # See https://github.com/encode/uvicorn/pull/972
#         startup_event: Message = {"type": "lifespan.startup"}
#         await self.receive_queue.put(startup_event)
#         await self.startup_event.wait()

#         if self.startup_failed:
#             logger.error("Application startup failed. Exiting.")
#             self.should_exit = True
#         else:
#             logger.info("Application startup complete.")

#     async def shutdown(self) -> None:
#         if self.error_occured:
#             return
#         logger.info("Waiting for application shutdown.")
#         shutdown_event: Message = {"type": "lifespan.shutdown"}
#         await self.receive_queue.put(shutdown_event)
#         await self.shutdown_event.wait()

#         if self.shutdown_failed:
#             logger.error("Application shutdown failed. Exiting.")
#             self.should_exit = True
#         else:
#             logger.info("Application shutdown complete.")

#     async def main(self) -> None:
#         try:
#             scope: Message = {
#                 "type": "lifespan",
#                 "asgi": {"version": self.version, "spec_version": "2.0"},
#                 "state": self.state,
#             }
#             await self.app(scope, self.receive, self.send)
#         except BaseException as exc:
#             self.asgi = None
#             self.error_occured = True
#             if self.startup_failed or self.shutdown_failed:
#                 return

#             msg = "Exception in 'lifespan' protocol\n"
#             logger.error(msg, exc_info=exc)
#         finally:
#             self.startup_event.set()
#             self.shutdown_event.set()

#     async def send(self, message: Message) -> None:
#         assert message["type"] in (
#             "lifespan.startup.complete",
#             "lifespan.startup.failed",
#             "lifespan.shutdown.complete",
#             "lifespan.shutdown.failed",
#         )

#         if message["type"] == "lifespan.startup.complete":
#             assert not self.startup_event.is_set(), STATE_TRANSITION_ERROR
#             assert not self.shutdown_event.is_set(), STATE_TRANSITION_ERROR
#             self.startup_event.set()

#         elif message["type"] == "lifespan.startup.failed":
#             assert not self.startup_event.is_set(), STATE_TRANSITION_ERROR
#             assert not self.shutdown_event.is_set(), STATE_TRANSITION_ERROR
#             self.startup_event.set()
#             self.startup_failed = True
#             if message.get("message"):
#                 logger.error(message["message"])

#         elif message["type"] == "lifespan.shutdown.complete":
#             assert self.startup_event.is_set(), STATE_TRANSITION_ERROR
#             assert not self.shutdown_event.is_set(), STATE_TRANSITION_ERROR
#             self.shutdown_event.set()

#         elif message["type"] == "lifespan.shutdown.failed":
#             assert self.startup_event.is_set(), STATE_TRANSITION_ERROR
#             assert not self.shutdown_event.is_set(), STATE_TRANSITION_ERROR
#             self.shutdown_event.set()
#             self.shutdown_failed = True
#             if message.get("message"):
#                 logger.error(message["message"])

#     async def receive(self) -> Message:
#         return await self.receive_queue.get()


# CLOSE_HEADER = (b"connection", b"close")

# HIGH_WATER_LIMIT = 65536


# class FlowControl:
#     def __init__(self, transport: asyncio.Transport) -> None:
#         self._transport = transport
#         self.read_paused: bool = False
#         self.write_paused: bool = False
#         self._is_writable_event: asyncio.Event = asyncio.Event()
#         self._is_writable_event.set()

#     async def drain(self) -> None:
#         await self._is_writable_event.wait()

#     def pause_reading(self) -> None:
#         if not self.read_paused:
#             self.read_paused = True
#             self._transport.pause_reading()

#     def resume_reading(self) -> None:
#         if self.read_paused:
#             self.read_paused = False
#             self._transport.resume_reading()

#     def pause_writing(self) -> None:
#         if not self.write_paused:
#             self.write_paused = True
#             self._is_writable_event.clear()

#     def resume_writing(self) -> None:
#         if self.write_paused:
#             self.write_paused = False
#             self._is_writable_event.set()


# class ServerState:
#     """
#     Shared servers state that is available between all protocol instances.
#     """

#     def __init__(self) -> None:
#         self.total_requests = 0
#         self.connections = set()
#         self.tasks = set()
#         self.default_headers = []


# UNKNOWN_ADDRESS: tuple[str, int] = ("unkown", 0)


# def _get_remote_addr(transport) -> tuple[str, int] | None:
#     socket_info = transport.get_extra_info("socket")

#     res: tuple[str, int]
#     if socket_info is not None:
#         try:
#             info = socket_info.getpeername()
#             if isinstance(info, tuple):
#                 res = (str(info[0]), int(info[1]))
#                 return res
#             return None
#         except OSError:
#             return None

#     info = transport.get_extra_info("peername")
#     if info is not None and isinstance(info, (list, tuple)) and len(info) == 2:
#         res = (str(info[0]), int(info[1]))
#         return res
#     return None


# def _get_local_addr(transport) -> tuple[str, int] | None:
#     socket_info = transport.get_extra_info("socket")
#     res = None
#     if socket_info is not None:
#         info = socket_info.getsockname()
#         if isinstance(info, tuple):
#             res = (str(info[0]), int(info[1]))
#     info = transport.get_extra_info("sockname")
#     if info is not None and isinstance(info, (list, tuple)) and len(info) == 2:
#         res = (str(info[0]), int(info[1]))
#     return res


# def is_ssl(transport: asyncio.Transport) -> bool:
#     return bool(transport.get_extra_info("sslcontext"))


# # TODO: server timeout, circuit breaker
# class Channel:
#     def __init__(
#         self,
#         scope: HTTPScope,
#         transport: asyncio.Transport,
#         flow: FlowControl,
#         default_headers: list[tuple[bytes, bytes]],
#         message_event: asyncio.Event,
#         expect_100_continue,
#         keep_alive,
#         on_response,
#     ):
#         self.scope = scope
#         self.transport = transport
#         self.flow = flow

#         self.default_headers = default_headers
#         self.message_event = message_event
#         self.on_response = on_response

#         # Connection state
#         self.disconnected = False
#         self.keep_alive = keep_alive
#         self.waiting_for_100_continue = expect_100_continue

#         # Request state
#         self.body: bytes = b""
#         self.more_body = True

#         # Response state
#         self.response_started = False
#         self.response_complete = False
#         self.chunked_encoding = False
#         self.expected_content_length = 0

#     # ASGI exception wrapper
#     async def run_asgi(self, app: ASGIApp) -> None:
#         await app(self.scope, self.receive, self.send)
#         if not self.response_started and not self.disconnected:
#             await ServiceUnavailableResp(self.send)
#         elif not self.response_complete and not self.disconnected:
#             self.transport.close()
#         self.on_response = lambda: None

#     # ASGI interface
#     async def send(self, message: Message) -> None:
#         message_type = message["type"]

#         if self.flow.write_paused and not self.disconnected:
#             await self.flow.drain()

#         if self.disconnected:
#             return

#         if not self.response_started:
#             # Sending response status line and headers
#             if message_type != "http.response.start":
#                 msg = "Expected ASGI message 'http.response.start', but got '%s'."
#                 raise RuntimeError(msg % message_type)

#             self.response_started = True
#             self.waiting_for_100_continue = False

#             status_code = message["status"]
#             headers = self.default_headers + list(message.get("headers", []))

#             if CLOSE_HEADER in self.scope["headers"] and CLOSE_HEADER not in headers:
#                 headers = headers + [CLOSE_HEADER]

#             # Write response status line and headers
#             content = [STATUS_LINE[status_code]]

#             for name, value in headers:
#                 if HEADER_RE.search(name):
#                     raise RuntimeError("Invalid HTTP header name.")
#                 if HEADER_VALUE_RE.search(value):
#                     raise RuntimeError("Invalid HTTP header value.")

#                 name = name.lower()
#                 if name == b"content-length" and self.chunked_encoding == 0:
#                     self.expected_content_length = int(value.decode())
#                     self.chunked_encoding = 0
#                 elif name == b"transfer-encoding" and value.lower() == b"chunked":
#                     self.expected_content_length = 0
#                     self.chunked_encoding = 1
#                 elif name == b"connection" and value.lower() == b"close":
#                     self.keep_alive = 0

#                 content.extend([name, b": ", value, b"\r\n"])

#             if (
#                 self.chunked_encoding is None
#                 and self.scope["method"] != "HEAD"
#                 and status_code not in (204, 304)
#             ):
#                 # Neither content-length nor transfer-encoding specified
#                 self.chunked_encoding = True
#                 content.append(b"transfer-encoding: chunked\r\n")

#             content.append(b"\r\n")
#             self.transport.write(b"".join(content))
#         elif not self.response_complete:
#             # Sending response body
#             if message_type != "http.response.body":
#                 msg = "Expected ASGI message 'http.response.body', but got '%s'."
#                 raise RuntimeError(msg % message_type)

#             body = cast(bytes, message.get("body", b""))
#             more_body = message.get("more_body", False)

#             # Write response body
#             if self.scope["method"] == "HEAD":
#                 self.expected_content_length = 0
#             elif self.chunked_encoding:
#                 if body:
#                     content = [b"%x\r\n" % len(body), body, b"\r\n"]
#                 else:
#                     content = []
#                 if not more_body:
#                     content.append(b"0\r\n\r\n")
#                 self.transport.write(b"".join(content))
#             else:
#                 num_bytes = len(body)
#                 if num_bytes > self.expected_content_length:
#                     raise RuntimeError("Response content longer than Content-Length")
#                 else:
#                     self.expected_content_length -= num_bytes
#                 self.transport.write(body)

#             # Handle response completion
#             if not more_body:
#                 if self.expected_content_length != 0:
#                     raise RuntimeError("Response content shorter than Content-Length")
#                 self.response_complete = True
#                 self.message_event.set()
#                 if not self.keep_alive:
#                     self.transport.close()
#                 self.on_response()
#         else:
#             # Response already sent
#             msg = "Unexpected ASGI message '%s' sent, after response already completed."
#             raise RuntimeError(msg % message_type)

#     async def receive(self) -> Message:
#         if self.waiting_for_100_continue and not self.transport.is_closing():
#             self.transport.write(b"HTTP/1.1 100 Continue\r\n\r\n")
#             self.waiting_for_100_continue = False

#         if not self.disconnected and not self.response_complete:
#             self.flow.resume_reading()
#             await self.message_event.wait()
#             self.message_event.clear()

#         if self.disconnected or self.response_complete:
#             return {"type": "http.disconnect"}

#         message: Message = {
#             "type": "http.request",
#             "body": self.body,
#             "more_body": self.more_body,
#         }
#         self.body = b""
#         return message


# class HttpProtocol:
#     channel: Channel

#     def __init__(
#         self,
#         app: ASGIApp,
#         root_path: str,
#         timeout_keep_alive: int,
#         server_state: ServerState,
#         _loop: asyncio.AbstractEventLoop | None = None,
#     ):

#         self.app = app
#         # self.static_cache = app.static_cache
#         # self.cache_hit = False
#         self.loop = _loop or asyncio.get_event_loop()

#         self.parser: Parser = HttpRequestParser(self)
#         self.parser.set_dangerous_leniencies(lenient_data_after_close=True)

#         self.root_path = root_path

#         # Timeouts
#         self.timeout_keep_alive_task: TimerHandle | None = None
#         self.timeout_keep_alive = timeout_keep_alive

#         # Global state
#         self.server_state = server_state
#         self.connections = server_state.connections
#         self.tasks = server_state.tasks

#         # Per-connection state
#         self.transport: asyncio.Transport
#         self.flow: FlowControl
#         self.server: tuple[str, int]
#         self.client: tuple[str, int]
#         self.scheme: Literal["http", "https"]
#         self.pipeline: deque[tuple[Channel, ASGIApp]] = deque()

#         # Per-request state
#         self.scope: HTTPScope
#         self.headers: list[tuple[bytes, bytes]]
#         self.expect_100_continue = False

#         self.channel = None

#     # ============ Protocol interface ============

#     def connection_made(self, transport: asyncio.Transport) -> None:
#         self.connections.add(self)
#         self.transport = transport
#         self.flow = FlowControl(transport)
#         self.server = _get_local_addr(transport)  # type: ignore
#         self.client = _get_remote_addr(transport)  # type: ignore
#         self.scheme = "https" if is_ssl(transport) else "http"

#     def connection_lost(self, exc: Exception | None) -> None:
#         self.connections.discard(self)

#         if self.channel and not self.channel.response_complete:
#             self.channel.disconnected = True
#         if self.channel is not None:
#             self.channel.message_event.set()
#         if self.flow is not None:
#             self.flow.resume_writing()
#         if exc is None:
#             self.transport.close()
#             self._unset_keepalive_task()

#         self.parser = None  # type: ignore

#     def pause_writing(self) -> None:
#         self.flow.pause_writing()

#     def resume_writing(self) -> None:
#         self.flow.resume_writing()

#     def eof_received(self) -> None:
#         pass

#     # ============ Protocol interface ============

#     def _unset_keepalive_task(self):
#         if self.timeout_keep_alive_task is None:
#             return

#         self.timeout_keep_alive_task.cancel()
#         self.timeout_keep_alive_task = None

#     def _get_upgrade(self) -> bytes | None:
#         connection = []
#         upgrade = None
#         for name, value in self.headers:
#             if name == b"connection":
#                 connection = [token.lower().strip() for token in value.split(b",")]
#             if name == b"upgrade":
#                 upgrade = value.lower()
#         if b"upgrade" in connection:
#             return upgrade
#         return None

#     def data_received(self, data: bytes) -> None:
#         self._unset_keepalive_task()

#         try:
#             self.parser.feed_data(data)
#         except HttpParserError as exc:
#             logger.error(exc)
#             msg = "Invalid HTTP request received."
#             self.send_400_response(msg)
#             return
#         except HttpParserUpgrade:
#             ...

#     def on_message_begin(self):
#         # only create a buffer here
#         self.url = b""
#         self.expect_100_continue = False
#         self.headers = []
#         self.scope = {
#             "type": "http",
#             "asgi": {"version": "3.0", "spec_version": "2.3"},
#             "http_version": "1.1",
#             "server": self.server,
#             "client": self.client,
#             "scheme": self.scheme,  # type: ignore[typeddict-item]
#             "root_path": self.root_path,
#             "headers": self.headers,
#         }

#     # Parser callbacks
#     def on_url(self, url: bytes):
#         # put url in the buffer
#         self.url += url

#     def on_header(self, name: bytes, value: bytes):
#         name = name.lower()
#         if name == b"expect" and value.lower() == b"100-continue":
#             self.expect_100_continue = True
#         self.headers.append((name, value))

#     def on_headers_complete(self):
#         try:
#             http_version = self.parser.get_http_version()
#             method = self.parser.get_method()
#             self.scope["method"] = method.decode("ascii")
#             if http_version != "1.1":
#                 self.scope["http_version"] = http_version

#             if self.parser.should_upgrade():
#                 return

#             parsed_url = parse_url(self.url)
#             raw_path = parsed_url.path
#             path = raw_path.decode("ascii")
#             if "%" in path:
#                 path = url_esapce(path)

#             # if static_content := self.static_cache.get(path):
#             #     self.cache_hit = True
#             #     self.transport.write(static_content)
#             #     # self.transport.close()
#             #     return

#             full_path = self.root_path + path
#             full_raw_path = self.root_path.encode("ascii") + raw_path
#             self.scope["path"] = full_path
#             self.scope["raw_path"] = full_raw_path
#             self.scope["query_string"] = parsed_url.query or b""

#             current_cycle = self.channel
#             self.channel = Channel(
#                 scope=self.scope,
#                 transport=self.transport,
#                 flow=self.flow,
#                 default_headers=self.server_state.default_headers,
#                 message_event=asyncio.Event(),
#                 expect_100_continue=self.expect_100_continue,
#                 keep_alive=http_version != "1.0",
#                 on_response=self.on_response_complete,
#             )

#             if current_cycle is None or current_cycle.response_complete:
#                 # Standard case - start processing the request.
#                 task = self.loop.create_task(self.channel.run_asgi(self.app))
#                 task.add_done_callback(self.tasks.discard)
#                 self.tasks.add(task)
#             else:
#                 # Pipelined HTTP requests need to be queued up.
#                 self.flow.pause_reading()
#                 self.pipeline.appendleft((self.channel, self.app))
#         except Exception as exc:
#             logger.error(exc)

#     def on_body(self, body):
#         try:
#             if self.channel.response_complete:
#                 return
#             self.channel.body += body
#             if len(self.channel.body) > HIGH_WATER_LIMIT:
#                 self.flow.pause_reading()
#             self.channel.message_event.set()
#         except Exception as exc:
#             logger.error(exc)

#     def on_message_complete(self):
#         # if self.cache_hit:
#         #     self.cache_hit = False
#         #     return
#         try:
#             if self.channel.response_complete:
#                 return

#             self.channel.more_body = False
#             self.channel.message_event.set()
#         except Exception as exc:
#             logger.error(exc)

#     def on_response_complete(self):
#         # Callback for pipelined HTTP requests to be started.
#         self.server_state.total_requests += 1

#         if self.transport.is_closing():
#             return

#         self._unset_keepalive_task()

#         # Unpause data reads if needed.
#         self.flow.resume_reading()

#         # Unblock any pipelined events. If there are none, arm the
#         # Keep-Alive timeout instead.
#         if self.pipeline:
#             channel, app = self.pipeline.pop()
#             task = self.loop.create_task(channel.run_asgi(app))
#             task.add_done_callback(self.tasks.discard)
#             self.tasks.add(task)
#         else:
#             self.timeout_keep_alive_task = self.loop.call_later(
#                 self.timeout_keep_alive, self.timeout_keep_alive_handler
#             )

#     def send_400_response(self, msg: str):
#         content: list[bytes] = [STATUS_LINE[400]]

#         for name, value in self.server_state.default_headers:
#             content.extend([name, b": ", value, b"\r\n"])

#         content.extend(
#             [
#                 b"content-type: text/plain; charset=utf-8\r\n",
#                 b"content-length: " + str(len(msg)).encode("ascii") + b"\r\n",
#                 b"connection: close\r\n",
#                 b"\r\n",
#                 msg.encode("ascii"),
#             ]
#         )
#         self.transport.write(b"".join(content))
#         self.transport.close()

#     def shutdown(self) -> None:
#         """
#         Called by the server to commence a graceful shutdown.
#         """
#         if self.channel is None or self.channel.response_complete:
#             self.transport.close()
#         else:
#             self.channel.keep_alive = 0

#     def timeout_keep_alive_handler(self) -> None:
#         """
#         Called on a keep-alive connection if no new data is received after a short
#         delay.
#         """
#         if not self.transport.is_closing():
#             self.transport.close()


# class Server:
#     def __init__(self, app: ASGIApp, config: ServerConfig) -> None:
#         self.app = app
#         self.config: ServerConfig = config
#         self.lifespan = LifespanOn(app, config.asgi_version)
#         self.server_state: ServerState = ServerState()

#         self.started: bool = False
#         self.should_exit: bool = False
#         self.force_exit: bool = False
#         self._captured_signals: list[int] = []

#     def run(self, sockets: list[socket.socket] | None = None) -> None:
#         asyncio.set_event_loop_policy(EventLoopPolicy())
#         return asyncio.run(self.serve(sockets=sockets))

#     async def serve(self, sockets: list[socket.socket] | None = None) -> None:
#         with self.capture_signals():
#             await self._serve(sockets)

#     def create_protocol(
#         self,
#         _loop: asyncio.AbstractEventLoop | None = None,
#     ) -> asyncio.Protocol:
#         return HttpProtocol(  # type: ignore[call-arg]
#             app=self.app,
#             root_path=self.config.root_path,
#             timeout_keep_alive=self.config.timeout_keep_alive,
#             server_state=self.server_state,
#             _loop=_loop,
#         )

#     async def _serve(self, sockets: list[socket.socket] | None = None) -> None:
#         await self.startup(sockets=sockets)
#         if self.should_exit:
#             return
#         await self.main_loop()
#         await self.shutdown(sockets=sockets)

#     async def startup(self, sockets: list[socket.socket] | None = None) -> None:
#         await self.lifespan.startup()
#         logger.success(f"running {self.app} at {self.config.host}:{self.config.port}")
#         if self.lifespan.should_exit:
#             self.should_exit = True
#             return

#         loop = asyncio.get_running_loop()
#         try:
#             server = await loop.create_server(
#                 self.create_protocol,
#                 host=self.config.host,
#                 port=self.config.port,
#                 backlog=self.config.backlog,
#             )
#         except OSError as exc:
#             logger.error(exc)
#             await self.lifespan.shutdown()
#             sys.exit(1)

#         assert server.sockets is not None
#         self.servers = [server]
#         self.started = True

#     async def main_loop(self) -> None:
#         while not self.should_exit:
#             await asyncio.sleep(0.1)

#     async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
#         logger.info("Shutting down")

#         # Stop accepting new connections.
#         for server in self.servers:
#             server.close()
#         for sock in sockets or []:
#             sock.close()

#         # Request shutdown on all existing connections.
#         for connection in list(self.server_state.connections):
#             connection.shutdown()

#         await asyncio.sleep(0.1)

#         # When 3.10 is not supported anymore, use `async with asyncio.timeout(...):`.
#         try:
#             await asyncio.wait_for(
#                 self._wait_tasks_to_complete(),
#                 timeout=None,
#             )
#         except asyncio.TimeoutError:
#             logger.error(
#                 "Cancel %s running task(s), timeout graceful shutdown exceeded",
#                 len(self.server_state.tasks),
#             )
#             for t in self.server_state.tasks:
#                 t.cancel(msg="Task cancelled, timeout graceful shutdown exceeded")

#         # Send the lifespan shutdown event, and wait for application shutdown.
#         if not self.force_exit:
#             await self.lifespan.shutdown()

#     async def _wait_tasks_to_complete(self) -> None:
#         # Wait for existing connections to finish sending responses.
#         if self.server_state.connections and not self.force_exit:
#             msg = "Waiting for connections to close. (CTRL+C to force quit)"
#             logger.info(msg)
#             while self.server_state.connections and not self.force_exit:
#                 await asyncio.sleep(0.1)

#         # Wait for existing tasks to complete.
#         if self.server_state.tasks and not self.force_exit:
#             msg = "Waiting for background tasks to complete. (CTRL+C to force quit)"
#             logger.info(msg)
#             while self.server_state.tasks and not self.force_exit:
#                 await asyncio.sleep(0.1)

#         for server in self.servers:
#             await server.wait_closed()

#     @contextlib.contextmanager
#     def capture_signals(self) -> Generator[None, None, None]:
#         if threading.current_thread() is not threading.main_thread():
#             yield
#             return

#         original_handlers = {
#             sig: signal.signal(sig, self.handle_exit) for sig in HANDLED_SIGNALS
#         }
#         try:
#             yield
#         finally:
#             for sig, handler in original_handlers.items():
#                 signal.signal(sig, handler)

#         for captured_signal in reversed(self._captured_signals):
#             signal.raise_signal(captured_signal)

#     def handle_exit(self, sig: int, frame: FrameType | None) -> None:
#         self._captured_signals.append(sig)
#         if self.should_exit and sig == signal.SIGINT:
#             self.force_exit = True
#         else:
#             self.should_exit = True
