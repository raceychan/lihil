from types import GenericAlias, MappingProxyType, UnionType
from typing import Any, Protocol, TypeAliasType, cast

from ididi import Resolver

from lihil.errors import NotSupportedError
from lihil.interface import MISSING, Base, Maybe
from lihil.interface.marks import extract_mark_type
from lihil.utils.typing import get_origin_pro
from lihil.vendor_types import Request


class PluginParam[T](Base):
    type_: type[T]
    name: str
    default: Maybe[Any] = MISSING
    required: bool = False
    loader: "PluginLoader[T] | None" = None

    def __post_init__(self):
        self.required = self.default is MISSING


class PluginLoader[T](Protocol):
    async def __call__(self, request: Request, resolver: Resolver) -> T: ...


class PluginProvider[T](Protocol):
    async def load(self, request: Request, resolver: Resolver) -> T: ...

    def parse(
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
        metas: list[Any] | None,
    ) -> PluginParam[T]:
        return PluginParam(
            type_=cast(type[T], type_), name=name, default=default, loader=self.load
        )


def __plugin_registry():
    plugin_providers: dict[str, PluginProvider[Any]] = {}

    def register_plugin_provider(
        mark: TypeAliasType | GenericAlias, provider: PluginProvider[Any]
    ) -> None:
        nonlocal plugin_providers

        _, metas = get_origin_pro(mark)

        if not metas:
            raise NotSupportedError("Invalid mark type")

        for meta in metas:
            if mark_type := extract_mark_type(meta):
                break
        else:
            raise NotSupportedError("Invalid mark type")

        plugin_providers[mark_type] = provider

    def remove_plugin_provider(mark: TypeAliasType | GenericAlias) -> None:
        nonlocal plugin_providers
        _, metas = get_origin_pro(mark)

        if not metas:
            raise NotSupportedError("Invalid mark type")
        for meta in metas:
            if mark_type := extract_mark_type(meta):
                break
        else:
            raise NotSupportedError("Invalid mark type")

        plugin_providers.pop(mark_type)

    return (
        MappingProxyType(plugin_providers),
        register_plugin_provider,
        remove_plugin_provider,
    )


PLUGIN_REGISTRY, register_plugin_provider, remove_plugin_provider = __plugin_registry()
