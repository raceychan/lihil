from types import GenericAlias, MappingProxyType
from typing import Any, Protocol, TypeAliasType

from ididi import Resolver

from lihil.errors import InvalidMarkTypeError
from lihil.interface import MISSING, Maybe, ParamBase, RegularTypes
from lihil.interface.marks import extract_mark_type
from lihil.utils.typing import get_origin_pro
from lihil.vendors import Request


class PluginParam(ParamBase[Any], kw_only=True):
    processor: Maybe["ParamProcessor"] = MISSING
    plugin: Maybe["PluginBase"] = MISSING


    def __repr__(self) -> str:
        name_repr = (
            self.name if self.alias == self.name else f"{self.name!r}, {self.alias!r}"
        )
        return f"{self.__class__.__name__}<Plugin> ({name_repr}: {self.type_repr})"


class ParamProcessor(Protocol):
    async def __call__(
        self, params: dict[str, Any], request: Request, resolver: Resolver
    ) -> None: ...


class PluginBase:
    async def process(
        self, params: dict[str, Any], request: Request, resolver: Resolver
    ) -> None:
        raise NotImplementedError(
            f"Plugin {self.__class__} did not implement `load` method"
        )

    def parse(
        self,
        name: str,
        type_: RegularTypes,
        annotation: Any,
        default: Any,
    ) -> PluginParam:
        return PluginParam(
            type_=type_,
            annotation=annotation,
            plugin=self,
            name=name,
            default=default,
            processor=self.process,
        )


def __plugin_registry():
    plugin_providers: dict[str, PluginBase] = {}

    def register_plugin_provider(
        mark: TypeAliasType | GenericAlias | str, provider: PluginBase
    ) -> PluginBase:
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
