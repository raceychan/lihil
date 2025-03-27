from typing import Annotated, Union

from lihil.interface.marks import get_origin_pro
from lihil.utils.typing import (
    deannotate,
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


type MyTV = list[int]


def test_is_non_textual_sequence():
    assert is_nontextual_sequence(list[int])
    assert is_nontextual_sequence(MyTV)

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


from lihil.interface import Body, CustomEncoder, Query, Resp
from lihil.interface.marks import BODY_REQUEST_MARK, QUERY_REQUEST_MARK, RESP_RETURN_MARK

type MyTypeAlias = Annotated[Query[int], CustomEncoder]
type NewAnnotated = Annotated[MyTypeAlias, "aloha"]

type MyType[T] = Annotated[T, "mymark"]


def test_get_origin_pro():
    assert get_origin_pro(int) == (int, None)
    assert get_origin_pro(list[int]) == (list[int], None)
    assert get_origin_pro(Annotated[list[int], "ok"]) == (list[int], ["ok"])
    assert get_origin_pro(MyType[str]) == (str, ["mymark"])

    assert get_origin_pro(Body[str | None]) == (Union[str, None], [BODY_REQUEST_MARK])
    assert get_origin_pro(MyTypeAlias) == (int, [CustomEncoder, QUERY_REQUEST_MARK])
    assert get_origin_pro(NewAnnotated) == (int, [CustomEncoder, QUERY_REQUEST_MARK])

    utype, umeta = get_origin_pro(Resp[str, 200] | Resp[int, 201])
    assert umeta
    assert utype == Union[str, int]
    assert 200 in umeta
    assert 201 in umeta
    assert RESP_RETURN_MARK in umeta
