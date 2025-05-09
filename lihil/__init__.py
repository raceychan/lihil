from typing import Annotated as Annotated

from ididi import AsyncScope as AsyncScope
from ididi import DependentNode as DependentNode
from ididi import Graph as Graph
from ididi import Ignore as Ignore
from ididi import Resolver as Resolver
from msgspec import Meta as Meta
from msgspec import Struct as Struct
from msgspec import field as field

from .constant import status as status

from .interface import Cookie as Cookie
from .interface import HTML as HTML
from .interface import MISSING as MISSING
from .interface import Body as Body
from .interface import Empty as Empty
from .interface import Form as Form
from .interface import Header as Header
from .interface import Json as Json
from .interface import Path as Path
from .interface import Payload as Payload
from .interface import Query as Query
from .interface import Resp as Resp
from .interface import Stream as Stream
from .interface import Text as Text
from .interface import Use as Use
from .lihil import Lihil as Lihil
from .plugins.bus import BusTerminal as BusTerminal
from .plugins.bus import EventBus as EventBus
from .plugins.testclient import LocalClient as LocalClient
from .problems import HTTPException as HTTPException
from .routing import Route as Route
from .websocket import WebSocketRoute as WebSocketRoute
from .vendors import Request as Request
from .vendors import Response as Response
from .vendors import UploadFile as UploadFile
from .vendors import WebSocket as WebSocket
from .vendors import use as use

# from .server.runner import run as run

VERSION = "0.2.4"
__version__ = VERSION
