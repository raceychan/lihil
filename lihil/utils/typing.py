from collections.abc import Mapping
from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    Literal,
    Sequence,
    TypeAliasType,
    TypeVar,
    Union,
    cast,
    get_args,
)
from typing import get_origin as ty_get_origin


def union_types(subs: Sequence[type[Any]]) -> type | UnionType | GenericAlias | None:
    """
    convert a sequence of types to a union of types
    union_types([str, int, bytes]) -> Union[str, int, bytes]
    """
    if not subs:
        return None
    elif len(subs) == 1:
        return next(iter(subs))
    return Union[*subs]  # type: ignore


def is_py_singleton(t: Any) -> Literal[None, True, False]:
    return t in {True, False, None, ...}


def is_union_type(
    t: type | UnionType | GenericAlias | TypeAliasType,
):
    return ty_get_origin(t) in (Union, UnionType)


def is_nontextual_sequence(type_: Any, strict: bool = False):
    type_origin = ty_get_origin(type_) or type_

    if not isinstance(type_origin, type):
        return False

    if type_origin in (str, bytes):
        return False

    if issubclass(type_origin, Sequence):
        return True

    return not strict and issubclass(type_origin, (set, frozenset))


def is_text_type(t: type | UnionType | GenericAlias) -> bool:
    if is_union_type(t):
        union_args = get_args(t)
        return any(u in (str, bytes) for u in union_args)

    return t in (str, bytes)


def is_mapping_type(qtype: type | UnionType | GenericAlias) -> bool:
    if is_union_type(qtype):
        q_union_args = get_args(qtype)
        return any(is_mapping_type(q) for q in q_union_args)

    qorigin = ty_get_origin(qtype) or qtype
    return qorigin is dict or isinstance(qorigin, type) and issubclass(qorigin, Mapping)


def is_generic_type(type_: Any) -> bool:
    return isinstance(type_, TypeVar) or any(
        is_generic_type(arg) for arg in get_args(type_)
    )


def replace_typevars(
    tyvars: tuple[type | TypeVar, ...], nonvars: tuple[type, ...]
) -> tuple[type, ...]:
    typevar_map: dict[TypeVar, None | type] = {
        item: None for item in tyvars if isinstance(item, TypeVar)
    }

    if len(typevar_map) > len(nonvars):
        raise ValueError(f"Expected {len(typevar_map)} types in t2, got {len(nonvars)}")

    idx = 0
    for k in typevar_map:
        typevar_map[k] = nonvars[idx]
        idx += 1

    # Replace TypeVars in t1
    result: list[type] = []

    for item in tyvars:
        if isinstance(item, TypeVar):
            mapped = typevar_map[item]
            assert mapped
            result.append(mapped)
        else:
            result.append(item)

    return tuple(result)


def repair_type_generic_alias(
    type_: TypeAliasType | GenericAlias, type_args: tuple[Any, ...]
) -> GenericAlias:
    """
    type StrDict[V] = dict[str, V]

    assert repair_type_generic_alias(StrDict[int]) == dict[str, int]
    assert repair_type_generic_alias(StrDict[float]) == dict[str, float]
    """

    generic = type_.__value__
    origin = ty_get_origin(generic)
    generic_args = generic.__args__
    res = replace_typevars(generic_args, type_args)
    return GenericAlias(origin, res)


def recursive_get_args(type_: Any) -> tuple[Any, ...]:
    if not get_args(type_):
        return ()
    type_args = get_args(type_)
    for idx, arg in enumerate(type_args):
        if sub_args := get_args(arg):
            type_args = type_args[:idx] + sub_args + type_args[idx + 1 :]
    return type_args


def deannotate[T](
    annt: Annotated[type[T], "Annotated"] | UnionType | GenericAlias,
) -> tuple[type[T], list[Any]] | tuple[type[T], None]:
    type_args = get_args(annt)
    size = len(type_args)

    if size < 2:
        return (cast(type[T], annt), None)

    atype, *metadata = type_args
    flattened_metadata: list[Any] = []

    for item in metadata:
        if ty_get_origin(item) is Annotated:
            _, metas = deannotate(item)
            if metas:
                flattened_metadata.extend(metas)
        else:
            flattened_metadata.append(item)
    # if isinstance(ty_get_origin(atype), TypeAliasType):
    #     new_type, new_metas = deannotate(atype.__value__)
    #     new_type: type[T]
    #     if new_metas:
    #         merged: list[Any] = new_metas + flattened_metadata
    #     else:
    #         merged = flattened_metadata
    #     return (new_type, merged)
    return (atype, flattened_metadata)


# TODO: carry type_args, StriDict[int] -> tyargs = ()
def get_origin_pro[T](
    type_: type[T] | UnionType | GenericAlias | TypeAliasType | TypeVar,
    metas: list[Any] | None = None,
    type_args: tuple[type] | None = None,
) -> tuple[type | UnionType | GenericAlias, list[Any] | None]:
    """
    type MyTypeAlias = Annotated[Query[int], CustomEncoder]
    type NewAnnotated = Annotated[MyTypeAlias, "aloha"]

    get_param_origin(Body[SamplePayload | None]) -> (SamplePayload | None, [BODY_REQUEST_MARK])
    get_param_origin(MyTypeAlias) -> (int, [QUERY_REQUEST_MARK, CustomEncoder])
    get_param_origin(NewAnnotated) -> (int, [QUERY_REQUEST_MARK, CustomEncoder])
    """

    if isinstance(type_, TypeAliasType):
        return get_origin_pro(type_.__value__, metas, type_args)

    if (current_origin := ty_get_origin(type_)) is None:
        return (cast(type, type_), cast(None, metas))

    if type_args is None:  # perserve the top most type arguments only
        type_args = recursive_get_args(type_)

    if current_origin is Annotated:
        annt_type, local_metas = deannotate(type_)
        if local_metas and metas:
            local_metas += metas
        return get_origin_pro(annt_type, local_metas, type_args)
    elif isinstance(current_origin, TypeAliasType):
        dealiased = cast(TypeAliasType, type_).__value__
        dtype, demetas = get_origin_pro(dealiased, metas, type_args)

        if is_generic_type(dtype):  # type: ignore
            if demetas:
                nontyvar = [
                    arg for arg in get_args(type_) if not isinstance(arg, TypeVar)
                ]
                dtype = nontyvar.pop(0) if nontyvar else dtype
                # dtype should be the first nontyvar, rest replace the tyvars in dmetas
                while nontyvar:
                    for idx, meta in enumerate(demetas):
                        if isinstance(meta, TypeVar):
                            demetas[idx] = nontyvar.pop(0)

                return get_origin_pro(dtype, demetas, type_args)
            else:
                dtype = repair_type_generic_alias(type_, type_args)
                return dtype, None
        else:
            return get_origin_pro(dealiased, metas, type_args)
    elif current_origin is UnionType:
        union_args = get_args(type_)
        utypes: list[type | UnionType | GenericAlias] = []
        new_metas: list[Any] = []
        for uarg in union_args:
            utype, umeta = get_origin_pro(uarg, None, type_args)
            utypes.append(utype)
            if umeta:
                new_metas.extend(umeta)
        if not new_metas:
            return get_origin_pro(Union[*utypes], metas, type_args)  # type: ignore

        if metas is None:
            metas = new_metas
        else:
            metas.extend(new_metas)
        return get_origin_pro(Union[*utypes], metas, type_args)  # type: ignore
    else:
        return (cast(type, type_), cast(None, metas))


def all_subclasses[T](
    cls: type[T], ignore: set[type[Any]] | None = None
) -> set[type[T]]:
    """
    Get all subclasses of a class recursively, avoiding repetition.

    Args:
        cls: The class to get subclasses for
        __seen__: Internal set to track already processed classes

    Returns:
        A set of all subclasses
    """
    if ignore is None:
        ignore = set()

    result: set[type[T]] = set()
    for subclass in cls.__subclasses__():
        if subclass not in ignore:
            ignore.add(subclass)
            result.add(subclass)
            result.update(all_subclasses(subclass, ignore))
    return result
