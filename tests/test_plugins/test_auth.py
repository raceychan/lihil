import sys
from typing import Annotated
from unittest import mock

import pytest
from msgspec import field

from lihil import Route, Text
from lihil.auth.jwt import JWTPayload
from lihil.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm
from lihil.errors import NotSupportedError
from lihil.plugins.testclient import LocalClient
from lihil.problems import InvalidAuthError


async def test_login():
    users = Route("users")
    token = Route("token")

    async def get_user(
        name: str, token: Annotated[str, OAuth2PasswordFlow(token_url="token")]
    ):
        return token

    async def create_token(credentials: OAuthLoginForm) -> Text:
        return "ok"

    users.get(get_user)
    token.post(create_token)

    form_ep = token.get_endpoint("POST")
    form_ep.setup()

    lc = LocalClient()
    res = await lc.submit_form(
        form_ep, form_data={"username": "user", "password": "pass"}
    )

    assert res.status_code == 200
    assert await res.text() == "ok"

    # lhl = Lihil(routes=[users, token])


def test_random_obj_to_jwt(): ...


def test_payload_with_aud_and_iss():
    class UserProfile(JWTPayload):
        __jwt_claims__ = {"aud": "client", "iss": "test", "expires_in": 5}

    profile = UserProfile()
    assert profile.exp


def test_payload_without_exp():
    class UserProfile(JWTPayload):
        __jwt_claims__ = {"aud": "client", "iss": "test"}

    with pytest.raises(NotSupportedError):
        UserProfile()


def test_jwt_missing():
    with mock.patch.dict("sys.modules", {"jwt": None}):
        if "lihil.auth.jwt" in sys.modules:
            del sys.modules["lihil.auth.jwt"]

        with pytest.raises(ImportError):
            from lihil.auth.jwt import jwt_decoder_factory


def test_invalid_payload_type():
    from lihil.auth.jwt import jwt_encoder_factory

    with pytest.raises(NotSupportedError):
        jwt_encoder_factory(
            secret="secret", algorithms=["HS256"], payload_type=list[int]
        )

    with pytest.raises(NotSupportedError):
        jwt_encoder_factory(
            secret="secret", algorithms=["HS256"], payload_type=JWTPayload
        )


def test_decode_jwtoken_fail():
    from lihil.auth.jwt import jwt_decoder_factory

    class UserProfile(JWTPayload):
        __jwt_claims__ = {"aud": "client", "iss": "test", "expires_in": 5}

        user_id: str = field(name="sub")

    decoder = jwt_decoder_factory(
        secret="secret", algorithms=["HS256"], payload_type=UserProfile
    )

    with pytest.raises(InvalidAuthError):
        decoder("Bearer")
