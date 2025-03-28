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
)
from typing import get_origin as ty_get_origin


def is_py_singleton(t: Any) -> Literal[None, True, False]:
    return t in {True, False, None, ...}


def deannotate[T](
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
            if ty_get_origin(item) is Annotated:
                _, metas = deannotate(item)
                if metas:
                    flattened_metadata.extend(metas)
            else:
                flattened_metadata.append(item)
        return (atype, flattened_metadata)


def is_union_type(t: type | UnionType | GenericAlias | TypeAliasType):
    return ty_get_origin(t) in (Union, UnionType)


def is_nontextual_sequence(type_: Any):
    while isinstance(type_, TypeAliasType):
        type_ = type_.__value__

    type_origin = ty_get_origin(type_) or type_

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


def get_origin_pro[T](
    type_: type[T] | UnionType | GenericAlias | TypeAliasType,
    metas: list[Any] | None = None,
) -> tuple[type, list[Any]] | tuple[type, None]:
    """
    type MyTypeAlias = Annotated[Query[int], CustomEncoder]
    type NewAnnotated = Annotated[MyTypeAlias, "aloha"]

    get_param_origin(Body[SamplePayload | None]) -> (SamplePayload | None, [BODY_REQUEST_MARK])
    get_param_origin(MyTypeAlias) -> (int, [QUERY_REQUEST_MARK, CustomEncoder])
    get_param_origin(NewAnnotated) -> (int, [QUERY_REQUEST_MARK, CustomEncoder])
    """

    if isinstance(type_, TypeAliasType):
        return get_origin_pro(type_.__value__, None)
    elif current_origin := ty_get_origin(type_):
        if current_origin is Annotated:
            annt_type, local_metas = deannotate(type_)
            if local_metas:
                if metas is None:
                    metas = local_metas
            return get_origin_pro(annt_type, metas)
        elif isinstance(current_origin, TypeAliasType):
            dealiased = type_.__value__
            if (als_args := get_args(dealiased)) and (ty_args := get_args(type_)):
                ty_type, *local_args = ty_args + als_args[len(ty_args) :]
                if ty_get_origin(dealiased) is Annotated:
                    if metas:
                        new_metas = metas + local_args
                    else:
                        new_metas = local_args
                    return get_origin_pro(ty_type, new_metas)
            return get_origin_pro(dealiased, metas)
        elif current_origin is UnionType:
            union_args = get_args(type_)
            utypes: list[type] = []

            new_metas: list[Any] = []
            for uarg in union_args:
                utype, umeta = get_origin_pro(uarg, None)
                utypes.append(utype)
                if umeta:
                    new_metas.extend(umeta)

            if not new_metas:
                return get_origin_pro(Union[*utypes], metas)


            if metas is None:
                metas = new_metas
            else:
                metas.extend(new_metas)
            return get_origin_pro(Union[*utypes], metas)
        else:
            return (type_, metas)
    else:
        return (type_, metas)
