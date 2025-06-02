from collections.abc import Mapping
from dataclasses import is_dataclass
from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    ForwardRef,
    Literal,
    Sequence,
    TypeVar,
    Union,
    cast,
    get_args,
)
from typing import get_origin as ty_get_origin
from typing import overload

from msgspec import UNSET, Struct, UnsetType
from pydantic import BaseModel
from typing_extensions import TypeAliasType, TypeGuard, is_typeddict

T = TypeVar("T")


@overload
def lenient_issubclass(t: Any, cls_or_clses: type[T]) -> TypeGuard[type[T]]: ...


@overload
def lenient_issubclass(t: Any, cls_or_clses: tuple[type, ...]) -> TypeGuard[type]: ...


def lenient_issubclass(
    t: Any, cls_or_clses: Union[type[T], tuple[type, ...]]
) -> TypeGuard[type[T]]:
    try:
        return isinstance(t, type) and issubclass(t, cls_or_clses)
    except TypeError:
        if origin := ty_get_origin(t):
            return lenient_issubclass(origin, cls_or_clses)
        return False


def union_types(subs: Sequence[type[Any]]) -> type | UnionType | GenericAlias | None:
    """
    convert a sequence of types to a union of types
    union_types([str, int, bytes]) -> Union[str, int, bytes]
    """
    if not subs:
        return None
    elif len(subs) == 1:
        return next(iter(subs))
    return Union[tuple(subs)]  # type: ignore


def is_py_singleton(t: Any) -> Literal[None, True, False]:
    return t in {True, False, None, ...}


def is_union_type(
    t: type | UnionType | GenericAlias | TypeAliasType,
) -> TypeGuard[UnionType]:
    return ty_get_origin(t) in (Union, UnionType)


def is_nontextual_sequence(
    type_: Any, strict: bool = False
) -> TypeGuard[list[Any] | tuple[Any] | bytearray]:
    type_origin = ty_get_origin(type_) or type_

    if type_origin is Union:
        return any(is_nontextual_sequence(arg, strict) for arg in get_args(type_))

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


def is_structured_type(
    param_type: type[Any] | UnionType | GenericAlias, homogeneous_union: bool = False
) -> bool:
    if is_union_type(param_type):
        q_union_args = get_args(param_type)
        union_filter = all if homogeneous_union else any
        return union_filter(is_structured_type(q) for q in q_union_args)

    qorigin = ty_get_origin(param_type) or param_type

    if not isinstance(qorigin, type):
        return False

    return (
        issubclass(qorigin, (Mapping, Struct, BaseModel))
        or is_typeddict(qorigin)
        or is_dataclass(qorigin)
    )


def is_generic_type(type_: Any) -> bool:
    return isinstance(type_, TypeVar) or any(
        is_generic_type(arg) for arg in get_args(type_)
    )


def replace_typevars(
    tyvars: Sequence[type | TypeVar], nonvars: Sequence[type]
) -> tuple[type, ...]:
    typevar_map: dict[TypeVar, None | type] = {
        item: None for item in tyvars if isinstance(item, TypeVar)
    }

    var_size, nonvar_size = len(typevar_map), len(nonvars)
    if var_size > nonvar_size:
        raise ValueError(f"Expected {var_size} types in t2, got {nonvar_size}")

    idx = 0
    for var in tyvars:
        if isinstance(var, TypeVar) and typevar_map.get(var) is None:
            typevar_map[var] = nonvars[idx]
            idx += 1

    result = tuple(
        typevar_map[var] if isinstance(var, TypeVar) else var for var in tyvars
    )
    return result


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


def deannotate(
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
    return (atype, flattened_metadata)


def get_origin_pro(
    type_: type[T] | UnionType | GenericAlias | TypeAliasType | TypeVar | ForwardRef,
    metas: list[Any] | None = None,
    type_args: tuple[type, ...] | None = None,
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

    if isinstance(type_, ForwardRef):
        raise TypeError(f"{type_} is not supported before python 3.12")

    if (current_origin := ty_get_origin(type_)) is None:
        return (cast(type, type_), cast(None, metas))

    if type_args is None:  # perserve the top most type arguments only
        type_args = recursive_get_args(type_)

    if current_origin is Annotated:
        annt_type, local_metas = deannotate(type_)
        if local_metas and metas:
            local_metas += metas
        return get_origin_pro(annt_type, local_metas, type_args)

    if isinstance(current_origin, TypeAliasType):
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
    if current_origin is UnionType:
        union_args = get_args(type_)
        utypes: list[type | UnionType | GenericAlias] = []
        new_metas: list[Any] = []
        for uarg in union_args:
            utype, umeta = get_origin_pro(uarg, None, type_args)
            utypes.append(utype)
            if umeta:
                new_metas.extend(umeta)
        if not new_metas:
            return get_origin_pro(Union[tuple(utypes)], metas, type_args)  # type: ignore

        if metas is None:
            metas = new_metas
        else:
            metas.extend(new_metas)
        return get_origin_pro(Union[tuple(utypes)], metas, type_args)  # type: ignore

    return (cast(type, type_), cast(None, metas))


def all_subclasses(cls: type[T], ignore: set[type[Any]] | None = None) -> set[type[T]]:
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


def should_use_pydantic(t: type[T] | UnsetType = UNSET) -> TypeGuard[type[BaseModel]]:
    if t is UNSET:
        return False

    type_origin, _ = get_origin_pro(t)

    if type_args := get_args(type_origin):
        return any(should_use_pydantic(arg) for arg in type_args)

    type_origin = cast(type, type_origin)

    return lenient_issubclass(type_origin, BaseModel)
