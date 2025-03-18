from types import GenericAlias, UnionType
from typing import Annotated, Any, TypeAliasType, cast, get_args, get_origin


def flatten_annotated[T](
    annt: Annotated[type[T], Any] | UnionType | TypeAliasType | GenericAlias,
) -> tuple[type[T], ...]:
    "Annotated[Annotated[T, Ann1, Ann2], Ann3] -> [T, Ann1, Ann2, Ann3]"
    type_args = get_args(annt)
    size = len(type_args)
    if size == 0:
        return cast(tuple[type, ...], (annt,))
    elif size == 1:
        return (type_args[0],)
    else:
        atype, *metadata = type_args
        flattened_metadata: list[Any] = [atype]

        for item in metadata:
            if get_origin(item) is Annotated:
                flattened_metadata.extend(flatten_annotated(item))
            else:
                flattened_metadata.append(item)
        return tuple(flattened_metadata)
