from types import UnionType
from typing import Annotated, Any, get_args, get_origin

# TODO: move flatten_annotated to ididi.utils.typing_utils


def get_annotated_type(annt) -> Any:
    """
    annt = Annotated[str, ...]
    assert get_annotated_type
    """
    return annt.__args__[0]


def flatten_annotated[T](
    type: Annotated[type[T], Any] | UnionType,
) -> tuple[type[T], ...]:
    "Annotated[Annotated[T, Ann1, Ann2], Ann3] -> [T, Ann1, Ann2, Ann3]"
    atype, *metadata = get_args(type)
    flattened_metadata: list[Any] = [atype]

    for item in metadata:
        if get_origin(item) is Annotated:
            flattened_metadata.extend(flatten_annotated(item))
        else:
            flattened_metadata.append(item)
    return tuple(flattened_metadata)
