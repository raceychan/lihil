from typing import (
    Any,
    AsyncContextManager,
    AsyncGenerator,
    Iterator,
    Mapping,
    Protocol,
    Unpack,
)

from starlette.datastructures import URL as URL
from starlette.datastructures import Address as Address
from starlette.datastructures import FormData as FormData
from starlette.datastructures import Headers as Headers
from starlette.datastructures import QueryParams as QueryParams
from starlette.datastructures import UploadFile as UploadFile
from starlette.requests import Request as Request
from starlette.requests import cookie_parser as cookie_parser
from starlette.responses import Response as Response
from starlette.types import Lifespan as Lifespan
from starlette.types import Receive as IReceive
from starlette.types import Scope as IScope
from starlette.websockets import WebSocket as WebSocket

try:
    from starlette.testclient import TestClient as TestClient
except (ImportError, RuntimeError):
    pass


from ididi import use as ididi_use
from ididi.interfaces import INodeConfig, INodeFactory


def use[**P, T](func: INodeFactory[P, T], **iconfig: Unpack[INodeConfig]):
    if iconfig.get("reuse") is None:
        iconfig["reuse"] = False
    return ididi_use(func, **iconfig)
