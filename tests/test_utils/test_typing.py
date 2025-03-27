from typing import Annotated, Union

from lihil.utils.typing import (
    flatten_annotated,
    is_nontextual_sequence,
    is_text_type,
    is_union_type,
)


def test_flatten_annotated():
    assert flatten_annotated(int) == (int, None)
    assert flatten_annotated(Annotated[str, 1, 2, 3]) == (str, [1, 2, 3])


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
