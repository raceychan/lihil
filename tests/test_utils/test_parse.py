import pytest

from lihil.utils.string import to_kebab_case, trim_path


def test_acronym():
    assert to_kebab_case("HTTPException") == "http-exception"
    assert to_kebab_case("UserAPI") == "user-api"
    assert to_kebab_case("OAuth2PasswordBearer") == "o-auth2-password-bearer"


def test_parse_empty():
    assert to_kebab_case("") == ""


def test_trim_trailling_path():
    with pytest.raises(ValueError):
        trim_path("/tests/")


# def test_parse_header_key():
#     assert parse_header_key("XToken", []) == "x-token"
#     assert parse_header_key("x_request_id") == "x-request-id"

#     assert parse_header_key("trace_id", ["x-trace-id"]) == "x-trace-id"

#     with pytest.raises(NotSupportedError):
#         parse_header_key("trace_id", [15])
