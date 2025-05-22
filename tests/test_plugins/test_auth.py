import sys
from typing import Annotated
from unittest import mock

import pytest
from msgspec import field

from lihil import Route, Text
from lihil.errors import NotSupportedError
from lihil.local_client import LocalClient
from lihil.plugins.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm
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
    await token.setup()

    lc = LocalClient()
    res = await lc.submit_form(
        form_ep, form_data={"username": "user", "password": "pass"}
    )

    assert res.status_code == 200
    assert await res.text() == "ok"

    # lhl = Lihil(routes=[users, token])


def test_random_obj_to_jwt(): ...


def test_jwt_missing():
    with mock.patch.dict("sys.modules", {"jwt": None}):
        if "lihil.plugins.auth.jwt" in sys.modules:
            del sys.modules["lihil.plugins.auth.jwt"]

        with pytest.raises(ImportError):
            from lihil.plugins.auth.jwt import jwt_decoder_factory
