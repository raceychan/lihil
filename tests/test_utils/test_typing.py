from typing import Annotated, Union

import pytest

from lihil.interface import Body, CustomEncoder, Query, Resp
from lihil.interface.marks import BODY_REQUEST_MARK, QUERY_REQUEST_MARK
from lihil.utils.typing import (
    deannotate,
    get_origin_pro,
    is_nontextual_sequence,
    is_text_type,
    is_union_type,
)


def test_deannotate():
    assert deannotate(int) == (int, None)
    assert deannotate(Annotated[str, 1, 2, 3]) == (str, [1, 2, 3])


def test_is_union_type():
    assert is_union_type(int | str)
    assert is_union_type(Union[int, str])
    assert not is_union_type(int)
    assert not is_union_type(dict[str, str])


def test_is_non_textual_sequence():
    assert is_nontextual_sequence(list[int])
    assert is_nontextual_sequence(tuple[str])

    assert not is_nontextual_sequence(str)
    assert not is_nontextual_sequence(bytes)
    assert not is_nontextual_sequence(5)


def test_is_text_type():
    assert is_text_type(str)
    assert is_text_type(bytes)
    assert is_text_type(str | bytes)
    assert is_text_type(bytes | dict[str, str])

    assert not is_text_type(dict[str, str])
    assert not is_text_type(int)
    assert not is_text_type(list[int])


type MyTypeAlias = Annotated[Query[int], CustomEncoder]
type NewAnnotated = Annotated[MyTypeAlias, "aloha"]

type MyType[T] = Annotated[T, "mymark"]


type StrDict[T] = dict[str, T]


def test_get_origin_pro_base_types():
    """
    we would need much more test case for this function
    to make it well tested.
    """
    assert get_origin_pro(int) == (int, None)
    assert get_origin_pro(str | bytes) == (str | bytes, None)


def test_get_origin_pro_generic_container():
    assert get_origin_pro(tuple[int]) == (tuple[int], None)
    assert get_origin_pro(tuple[int, ...]) == (tuple[int, ...], None)
    assert get_origin_pro(list[int]) == (list[int], None)
    assert get_origin_pro(dict[str, int]) == (dict[str, int], None)


def test_get_origin_pro_annotated():
    assert get_origin_pro(Annotated[list[int], "ok"]) == (list[int], ["ok"])


def test_get_origin_pro_type_alias():
    assert get_origin_pro(MyType[str]) == (str, ["mymark"])
    assert get_origin_pro(MyType[str | int]) == (Union[str | int], ["mymark"])
    assert get_origin_pro(Body[str | None]) == (Union[str, None], [BODY_REQUEST_MARK])
    assert get_origin_pro(MyTypeAlias) == (int, [QUERY_REQUEST_MARK, CustomEncoder])
    assert get_origin_pro(NewAnnotated) == (
        int,
        [QUERY_REQUEST_MARK, CustomEncoder, "aloha"],
    )
    assert get_origin_pro(Resp[str, 200] | Resp[int, 201]) == (
        Union[str, int],
        [200, "__LIHIL_RESPONSE_MARK_RESP__", 201, "__LIHIL_RESPONSE_MARK_RESP__"],
    )


type Base[T] = Annotated[T, 1]
type NewBase[T] = Annotated[Base[T], 2]
type AnotherBase[T, K] = Annotated[NewBase[T], K, 3]


def test_get_origin_nested():
    base = get_origin_pro(Base[str])
    assert base[0] == str and base[1] == [1]

    nbase = get_origin_pro(NewBase[str])
    assert nbase[0] == str and nbase[1] == [1, 2]

    res = get_origin_pro(AnotherBase[bytes | float, str] | list[int])
    assert res[0] == Union[bytes, float, list[int]]
    assert res[1] == [1, 2, str, 3]


# def test_get_origin_pro_type_alias_generic():
#     # ============= TypeAlias + TypeVar + Genric ============
#     assert get_origin_pro(StrDict[int]) == (dict[str, int], None)


type MARK_ONE = Annotated[str, "ONE"]
type MARK_TWO = Annotated[MARK_ONE, "TWO"]
type MARK_THREE = Annotated[MARK_TWO, "THREE"]


def test_get_origin_pro_unpack_annotated_in_order():
    res = get_origin_pro(Annotated[str, 1, Annotated[str, 2, Annotated[str, 3]]])
    assert res == (str, [1, 2, 3])


def test_get_origin_pro_unpack_textalias_in_order():
    res = get_origin_pro(MARK_THREE)
    assert res == (str, ["ONE", "TWO", "THREE"])


type Pair[K, V] = tuple[K, V]


def test_get_origin_pro_with_generic_alias():

    ptype, _ = get_origin_pro(dict[str, str])
    assert ptype == dict[str, str]

    ptype, _ = get_origin_pro(Pair[float, int])
    assert ptype == tuple[float, int]


type StrDict[V] = dict[str, V]


def test_generic_alias():
    ptype, _ = get_origin_pro(StrDict[int])
    assert ptype == dict[str, int]
    assert get_origin_pro(StrDict[float])[0] == dict[str, float]


def test_get_origin_pro_with_unset():
    from lihil.interface import UNSET, Unset, UnsetType

    ptype, metas = get_origin_pro(Unset[str])

    assert ptype.__args__ == (UnsetType, str)
