from types import UnionType
from typing import Any, Sequence, Union


def all_subclasses[T](
    cls: type[T], __seen__: set[type[Any]] | None = None
) -> set[type[T]]:
    """
    Get all subclasses of a class recursively, avoiding repetition.

    Args:
        cls: The class to get subclasses for
        __seen__: Internal set to track already processed classes

    Returns:
        A set of all subclasses
    """
    if __seen__ is None:
        __seen__ = set()

    result: set[type[T]] = set()
    for subclass in cls.__subclasses__():
        if subclass not in __seen__:
            __seen__.add(subclass)
            result.add(subclass)
            result.update(all_subclasses(subclass, __seen__))
    return result


def union_types(subs: Sequence[type[Any]]) -> type | UnionType | None:
    if not subs:
        return None
    elif len(subs) == 1:
        return next(iter(subs))
    return Union[*(subs)]  # type: ignore
