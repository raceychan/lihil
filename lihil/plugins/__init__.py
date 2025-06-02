"""
Plugins that contains non-core functionalities for lihil,
mostly simple wrappers to third-party dependencies.
if not, likely to be a standalone lib
"""

from typing import Any, Protocol, Generic

from ididi import Graph

from lihil.interface import IAsyncFunc, P, R
from lihil.signature import EndpointSignature


class IAsyncPlugin(Protocol, Generic[P, R]):
    async def __call__(
        self,
        graph: Graph,
        func: IAsyncFunc[P, R],
        sig: EndpointSignature[Any],
        /,
    ) -> IAsyncFunc[P, R]: ...


class ISyncPlugin(Protocol, Generic[P, R]):
    def __call__(
        self,
        graph: Graph,
        func: IAsyncFunc[P, R],
        sig: EndpointSignature[Any],
        /,
    ) -> IAsyncFunc[P, R]: ...


IPlugin = IAsyncPlugin[..., Any] | ISyncPlugin[..., Any]
