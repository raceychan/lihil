from typing import Annotated, Generic, TypeAlias, TypeVar, Union

import pytest

from lihil import Param
from lihil.interface import CustomEncoder
from lihil.utils.typing import (
    deannotate,
    get_origin_pro,
    is_nontextual_sequence,
    is_text_type,
    is_union_type,
    lenient_issubclass,
    should_use_pydantic,
)

T = TypeVar("T")
K = TypeVar("K")


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


MyTypeAlias = Annotated[int, CustomEncoder]
NewAnnotated = Annotated[MyTypeAlias, "aloha"]

MyType = Annotated[T, "mymark"]


StrDict = dict[str, T]


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
    assert get_origin_pro(Annotated[str | None, Param("body")])[0] == (Union[str, None])
    # assert get_origin_pro(MyTypeAlias) == (int, [QUERY_REQUEST_MARK, CustomEncoder])
    # assert get_origin_pro(NewAnnotated) == (
    #     int,
    #     [QUERY_REQUEST_MARK, CustomEncoder, "aloha"],
    # )
    # assert get_origin_pro(Resp[str, 200] | Resp[int, 201]) == (
    #     Union[str, int],
    #     [200, "__LIHIL_RESPONSE_MARK_RESP__", 201, "__LIHIL_RESPONSE_MARK_RESP__"],
    # )


Base = Annotated[T, 1]
NewBase = Annotated[Base[T], 2]


def test_get_origin_nested():
    base = get_origin_pro(Base[str])
    assert base[0] == str and base[1] == [1]

    nbase = get_origin_pro(NewBase[str])
    assert nbase[0] == str and nbase[1] == [1, 2]


# def test_get_origin_pro_type_alias_generic():
#     # ============= TypeAlias + TypeVar + Genric ============
#     assert get_origin_pro(StrDict[int]) == (dict[str, int], None)


MARK_ONE = Annotated[str, "ONE"]
MARK_TWO = Annotated[MARK_ONE, "TWO"]
MARK_THREE = Annotated[MARK_TWO, "THREE"]


def test_get_origin_pro_unpack_annotated_in_order():
    res = get_origin_pro(Annotated[str, 1, Annotated[str, 2, Annotated[str, 3]]])
    assert res == (str, [1, 2, 3])


def test_get_origin_pro_unpack_textalias_in_order():
    res = get_origin_pro(MARK_THREE)
    assert res == (str, ["ONE", "TWO", "THREE"])


V = TypeVar("V")
Pair = tuple[K, V]


def test_get_origin_pro_with_generic_alias():

    ptype, _ = get_origin_pro(dict[str, str])
    assert ptype == dict[str, str]

    ptype, _ = get_origin_pro(Pair[float, int])
    assert ptype == tuple[float, int]


StrDict = dict[str, V]


def test_generic_alias():
    ptype, _ = get_origin_pro(StrDict[int])
    assert ptype == dict[str, int]
    assert get_origin_pro(StrDict[float])[0] == dict[str, float]


def test_get_origin_pro_with_unset():
    from lihil.interface import UNSET, Unset, UnsetType

    ptype, metas = get_origin_pro(Unset[str])

    assert ptype.__args__ == (UnsetType, str)


def test_get_auth_header():

    ptype, metas = get_origin_pro(
        Annotated[str, Param("header", alias="Authorization")]
    )
    assert ptype is str
    assert metas
    assert metas[0].alias == "Authorization"


class T1(Generic[K, V]): ...


TAlias: TypeAlias = T1[K, V]


def test_get_generic_types():

    ptype, metas = get_origin_pro(TAlias[str, int])
    assert ptype == T1[str, int]
    assert not metas


def test_lenient_issubclass():
    assert lenient_issubclass(str, str)
    assert lenient_issubclass(str, (str, object))
    assert not lenient_issubclass(5, str)


@pytest.mark.debug
def test_should_use_pydantic():
    assert not should_use_pydantic(str)
    assert not should_use_pydantic(int)
    assert not should_use_pydantic(list[int])

    from msgspec import Struct
    from pydantic import BaseModel

    class PydanticType(BaseModel):
        name: str

    class MsgspecType(Struct):
        name: str

    assert should_use_pydantic(PydanticType)
    assert should_use_pydantic(list[PydanticType])
    assert should_use_pydantic(dict[str, PydanticType])

    assert not should_use_pydantic(MsgspecType)
