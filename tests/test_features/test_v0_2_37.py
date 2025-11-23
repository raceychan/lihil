""" """

from typing import Annotated

from ididi import Ignore
from jwt import PyJWT
from msgspec import Struct, convert

from lihil import LocalClient, Param, Text, use
from lihil.interface import T

"""
write an endpoint that requires a function dependency which requires JWTAuthParam
"""


class JWTDecoder:
    def __init__(self, jwt_secret: str, jwt_algos: list[str]):
        self.jwt_secret = jwt_secret
        self.jwt_algos = jwt_algos

        self._jwt = PyJWT()

    def decode(self, raw: bytes, payload_type: type[T]) -> T:
        token = raw.decode("utf-8").removeprefix("Bearer ")
        decoded = self._jwt.decode(
            token, key=self.jwt_secret, algorithms=self.jwt_algos
        )
        return convert(decoded, payload_type)


class TestSecrets:
    class JWTSettings:
        secret: str = "my secret"
        algorithms: list[str] = ["HS256"]

    jwt: JWTSettings = JWTSettings()


def get_jwt_decoder(secrets: TestSecrets) -> JWTDecoder:
    algos: list[str] = secrets.jwt.algorithms
    return JWTDecoder(secrets.jwt.secret, algos)


def secret_provider() -> TestSecrets:
    return TestSecrets()


class LoginResponse(Struct):
    user_id: str


async def get_user_id(
    auth_header: Annotated[bytes, Param("header", alias="Authorization")],
    decoder: Annotated[JWTDecoder, use(get_jwt_decoder, reuse=True)],
) -> Ignore[str]:
    decoded = decoder.decode(auth_header, LoginResponse)
    return decoded.user_id


async def get_age(age: int) -> Ignore[int]:
    return age


FAKE_USER_DB = {
    "user123": {"user_id": "user123", "name": "Alice"},
}


async def get_me(user_id: Annotated[str, use(get_user_id)], age: Annotated[int, use(get_age)]) -> Text:
    return FAKE_USER_DB[user_id]["name"]


async def test_jwt_auth_param():
    lc = LocalClient()
    ep = await lc.make_endpoint(get_me)

    resp = await lc.call_endpoint(
        ep,
        headers={
            "Authorization": "Bearer "
            + PyJWT().encode({"user_id": "user123"}, "my secret", algorithm="HS256")
        },
        query_params={"age": "30"},
    )
    assert await resp.text() == "Alice"
