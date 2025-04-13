from inspect import isasyncgen, isgenerator
from typing import Any, Callable, Unpack

from ididi import Graph
from ididi.graph import Resolver
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

from lihil.config import AppConfig, SyncDeps
from lihil.endpoint import EndpointSignature, ParseResult
from lihil.endpoint.returns import agen_encode_wrapper, syncgen_encode_wrapper
from lihil.errors import InvalidParamTypeError
from lihil.interface import HTTP_METHODS, IReceive, IScope, ISend
from lihil.plugins.bus import BusTerminal, EventBus
from lihil.problems import InvalidRequestErrors, get_solver
from lihil.props import EndpointProps
from lihil.props import IEndpointProps as IEndpointProps
from lihil.utils.threading import async_wrapper

"""
This should be closer to Route
we might move some logic into signature then put it in routing.py
make `Endpoint` a very think wrapper around endpoint function

signature/
    params.py
    returns.py
    signature.py
"""
