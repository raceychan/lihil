from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    Sequence,
    TypeAliasType,
    Union,
    cast,
    get_args,
    get_origin,
)


def flatten_annotated[T](
    annt: Annotated[type[T], Any] | UnionType | TypeAliasType | GenericAlias,
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
    if not isinstance(type_, type):
        return False

    if type_ in (str, bytes):
        return False

    return issubclass(type_, Sequence)


# def isasyncfunc():
#    return iscoroutinefunction
