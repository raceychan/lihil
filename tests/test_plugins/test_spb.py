import pytest
from msgspec import ValidationError, convert

from lihil import Lihil, Route
from lihil.plugins.auth.supabase import (
    auth_types,
    signin_route_factory,
    signup_route_factory,
)


def test_validate_typeddict():

    data = {"provider": "google", "token": "asdfadsf"}

    result = convert(data, auth_types.SignInWithIdTokenCredentials)
    assert isinstance(result, dict)

    fail_data = {"provider": "google", "token": 3.5}

    with pytest.raises(ValidationError):
        convert(fail_data, auth_types.SignInWithIdTokenCredentials)


def test_create_signup():
    route = signup_route_factory("token", sign_up_with="email")
    assert isinstance(route, Route)


def test_create_signin():
    route = signin_route_factory("token")
    assert isinstance(route, Route)


async def test_setup_signin_route():
    route = signin_route_factory("login")

    await route.setup()
