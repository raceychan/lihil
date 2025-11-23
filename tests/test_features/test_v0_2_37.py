""" """

from typing import Annotated

from ididi import Ignore
from jwt import PyJWT
from msgspec import Struct, convert

from lihil import LocalClient, Param, use
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


async def get_age(age: int, path_int: Annotated[int, Param("path")]) -> Ignore[int]:
    return age + path_int


FAKE_USER_DB = {
    "user123": {"user_id": "user123", "name": "Alice"},
}


class User(Struct):
    name: str
    age: int


async def get_me(
    user_id: Annotated[str, use(get_user_id)], age: Annotated[int, use(get_age)]
) -> User:
    return User(name=FAKE_USER_DB[user_id]["name"], age=age)


async def test_jwt_auth_param():
    lc = LocalClient()
    ep = await lc.make_endpoint(get_me, path="/me/{path_int}")

    resp = await lc.call_endpoint(
        ep,
        headers={
            "Authorization": "Bearer "
            + PyJWT().encode({"user_id": "user123"}, "my secret", algorithm="HS256")
        },
        query_params={"age": "30"},
        path_params={"path_int": "5"},
    )
    assert await resp.json() == {"name": "Alice", "age": 35}
