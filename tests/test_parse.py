from lihil.utils.parse import to_kebab_case


def test_acronym():
    assert to_kebab_case("HTTPException") == "http-exception"
    assert to_kebab_case("UserAPI") == "user-api"
    assert to_kebab_case("OAuth2PasswordBearer") == "o-auth2-password-bearer"
