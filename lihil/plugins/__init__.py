"""
Plugins that contains non-core functionalities for lihil,
mostly simple wrappers to third-party dependencies.
if not, likely to be a standalone lib
"""

from typing import Any, Awaitable, Callable, Protocol

from ididi import Graph

from lihil.signature import EndpointSignature

IFunc = Callable[..., Awaitable[Any]]


class IAsyncPlugin(Protocol):
    async def __call__(
        self,
        graph: Graph,
        func: IFunc,
        sig: EndpointSignature[Any],
        /,
    ) -> IFunc: ...


class ISyncPlugin(Protocol):
    def __call__(
        self,
        graph: Graph,
        func: IFunc,
        sig: EndpointSignature[Any],
        /,
    ) -> IFunc: ...


IPlugin = IAsyncPlugin | ISyncPlugin
