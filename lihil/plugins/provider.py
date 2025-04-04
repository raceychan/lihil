from types import GenericAlias, MappingProxyType, UnionType
from typing import Any, ClassVar, Protocol, TypeAliasType, cast

from ididi import Resolver

from lihil.errors import InvalidMarkTypeError
from lihil.interface import Maybe, RequestParamBase
from lihil.interface.marks import extract_mark_type
from lihil.utils.typing import get_origin_pro
from lihil.vendor_types import Request


class PluginParam[T](RequestParamBase[T]):
    loader: "PluginLoader[T] | None" = None


class PluginLoader[T](Protocol):
    async def __call__(self, request: Request, resolver: Resolver) -> T: ...


# Perhaps it is eaasier to just check for subclass of this
class PluginMixin[T]:
    __mark_type__: ClassVar[str]

    async def load(self, request: Request, resolver: Resolver) -> T: ...

    def parse(
        self,
        name: str,
        type_: type[T] | UnionType,
        annotation: Any,
        default: Maybe[T],
    ) -> PluginParam[T]:
        return PluginParam(
            type_=cast(type[T], type_),
            annotation=annotation,
            name=name,
            default=default,
            loader=self.load,
        )


def __plugin_registry():
    plugin_providers: dict[str, PluginMixin[Any]] = {}

    # TODO:
    def register_plugin_provider(
        mark: TypeAliasType | GenericAlias | str, provider: PluginMixin[Any]
    ) -> PluginMixin[Any]:
        nonlocal plugin_providers

        if isinstance(mark, str):
            mark_type = mark
        else:
            _, metas = get_origin_pro(mark)

            if not metas:
                raise InvalidMarkTypeError(mark)

            for meta in metas:
                if mark_type := extract_mark_type(meta):
                    break
            else:
                raise InvalidMarkTypeError(mark)

        if mark_type in plugin_providers:
            raise Exception(f"Duplicate mark {mark}, remove it first")

        plugin_providers[mark_type] = provider
        return provider

    def remove_plugin_provider(mark: TypeAliasType | GenericAlias | str) -> None:
        nonlocal plugin_providers

        if isinstance(mark, str):
            mark_type = mark
        else:
            _, metas = get_origin_pro(mark)

            if not metas:
                raise InvalidMarkTypeError(mark)
            for meta in metas:
                if mark_type := extract_mark_type(meta):
                    break
            else:
                raise InvalidMarkTypeError(mark)

        plugin_providers.pop(mark_type)

    return (
        MappingProxyType(plugin_providers),
        register_plugin_provider,
        remove_plugin_provider,
    )


PLUGIN_REGISTRY, register_plugin_provider, remove_plugin_provider = __plugin_registry()
