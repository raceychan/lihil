from types import UnionType
from typing import Annotated, Any, cast, get_args, get_origin, TypeAliasType


def flatten_annotated[T](
    annt: Annotated[type[T], Any] | UnionType | TypeAliasType,
) -> tuple[type[T], ...]:
    "Annotated[Annotated[T, Ann1, Ann2], Ann3] -> [T, Ann1, Ann2, Ann3]"
    type_args = get_args(annt)
    if len(type_args) > 1:
        atype, *metadata = type_args
        flattened_metadata: list[Any] = [atype]

        for item in metadata:
            if get_origin(item) is Annotated:
                flattened_metadata.extend(flatten_annotated(item))
            else:
                flattened_metadata.append(item)
        return tuple(flattened_metadata)
    else:
        return cast(tuple[type, ...], (annt,))
