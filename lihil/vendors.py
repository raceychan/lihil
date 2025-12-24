from typing import ParamSpec, TypeVar

from starlette.datastructures import URL as URL
from starlette.datastructures import Address as Address
from starlette.datastructures import FormData as FormData
from starlette.datastructures import Headers as Headers
from starlette.datastructures import QueryParams as QueryParams
from starlette.datastructures import UploadFile as UploadFile
from starlette.formparsers import MultiPartException as MultiPartException
from starlette.requests import HTTPConnection as HTTPConnection
from starlette.requests import Request as Request
from starlette.requests import cookie_parser as cookie_parser
from starlette.responses import Response as Response
from starlette.responses import StreamingResponse as StreamingResponse
from starlette.routing import compile_path as compile_path
from starlette.types import Lifespan as Lifespan
from starlette.websockets import WebSocket as WebSocket
from starlette.websockets import WebSocketDisconnect as WebSocketDisconnect
from starlette.websockets import WebSocketState as WebSocketState

P = ParamSpec("P")
T = TypeVar("T")

try:
    from starlette.testclient import TestClient as TestClient
except (ImportError, RuntimeError):
    pass


from ididi import use as use
