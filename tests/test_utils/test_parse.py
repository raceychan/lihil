from typing import Union

import pytest

from lihil.utils.parse import to_kebab_case
from lihil.utils.phasing import build_union_decoder, to_bytes, to_str


def test_acronym():
    assert to_kebab_case("HTTPException") == "http-exception"
    assert to_kebab_case("UserAPI") == "user-api"
    assert to_kebab_case("OAuth2PasswordBearer") == "o-auth2-password-bearer"


def test_to_str_decode_bytes():
    assert to_str(b"abc") == "abc"


def test_to_bytes_decode_str():
    assert to_bytes("abc") == b"abc"


def test_byte_str_union():
    with pytest.raises(TypeError):
        build_union_decoder((bytes, str), target_type=str)


def test_build_union_decoder_with_complex_types():
    """Test union decoder with more complex types"""
    # Create a union decoder for Union[list, dict, str]
    union_decoder = build_union_decoder((list[int], dict[str, int], str), str)

    # Test decoding a valid list
    assert union_decoder("[1, 2, 3]") == [1, 2, 3]

    # Test decoding a valid dict
    assert union_decoder('{"a": 1, "b": 2}') == {"a": 1, "b": 2}

    # Test decoding a string that's not valid JSON
    assert union_decoder("not json") == "not json"


def test_build_union_decoder_nested_unions():
    """Test union decoder with nested union types"""
    # Define a nested union type
    NestedUnion = Union[int, Union[dict, list]]

    # Create a union decoder
    union_decoder = build_union_decoder((int, dict, list, str), str)

    # Test decoding different types
    assert union_decoder("42") == 42
    assert union_decoder('{"a": 1}') == {"a": 1}
    assert union_decoder("[1, 2, 3]") == [1, 2, 3]
    assert union_decoder("not json") == "not json"


def test_build_union_decoder_priority():
    """Test that the decoder tries complex types before falling back to str/bytes"""
    # Create a union decoder
    union_decoder = build_union_decoder((dict, str), str)

    # A valid JSON string that could be either a dict or kept as string
    json_str = '{"key": "value"}'

    # It should be decoded as a dict first
    assert union_decoder(json_str) == {"key": "value"}
    assert not isinstance(union_decoder(json_str), str)

    # A string that looks like JSON but isn't valid should be kept as string
    invalid_json = '{"key": value}'  # missing quotes around value
    assert union_decoder(invalid_json) == invalid_json
    assert isinstance(union_decoder(invalid_json), str)
