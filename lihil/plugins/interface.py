from typing import Generic, Protocol

from ididi import Graph

from lihil.interface import IAsyncFunc, P, R
from lihil.signature import EndpointSignature


class IEndpointInfo(Protocol, Generic[P, R]):
    @property
    def graph(self) -> Graph: ...
    @property
    def func(self) -> IAsyncFunc[P, R]: ...
    @property
    def sig(self) -> EndpointSignature[R]: ...


class IPlugin(Protocol):
    def __call__(self, endpoint_info: IEndpointInfo[P, R], /) -> IAsyncFunc[P, R]: ...
