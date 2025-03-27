from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    Sequence,
    TypeAliasType,
    Union,
    cast,
    get_args,
    get_origin,
)


def is_py_singleton(t: Any) -> Literal[None, True, False]:
    return t in {True, False, None, ...}


def flatten_annotated[T](
    annt: Annotated[type[T], "Annotated"] | UnionType | GenericAlias,
) -> tuple[type[T], list[Any]] | tuple[type[T], None]:
    type_args = get_args(annt)
    size = len(type_args)

    if size == 0:
        return (cast(type, annt), None)
    elif size == 1:
        return (type_args[0], None)
    else:
        atype, *metadata = type_args
        flattened_metadata: list[Any] = []

        for item in metadata:
            if get_origin(item) is Annotated:
                _, metas = flatten_annotated(item)
                if metas:
                    flattened_metadata.extend(metas)
            else:
                flattened_metadata.append(item)
        return (atype, flattened_metadata)


def is_union_type(t: type | UnionType | GenericAlias | TypeAliasType):
    return get_origin(t) in (Union, UnionType)


def is_nontextual_sequence(type_: Any):
    while isinstance(type_, TypeAliasType):
        type_ = type_.__value__

    type_origin = get_origin(type_) or type_

    if not isinstance(type_origin, type):
        return False

    if type_origin in (str, bytes):
        return False

    return issubclass(type_origin, Sequence)


def is_text_type(t: type | UnionType) -> bool:
    if is_union_type(t):
        union_args = get_args(t)
        return any(u in (str, bytes) for u in union_args)

    return t in (str, bytes)
