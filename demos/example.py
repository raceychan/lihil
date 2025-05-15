from typing import Literal, Annotated

from lihil import Lihil, Payload, Route, field, Header
from msgspec import Meta
from lihil.auth.jwt import JWTAuth, JWTPayload
from lihil.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm


me = Route("me")
token = Route("token")


class UserProfile(JWTPayload):
    __jwt_claims__ = {"expires_in": 300}

    user_id: str = field(name="sub")
    role: Literal["admin", "user"] = "user"


class User(Payload):
    name: str
    email: str


token_based = OAuth2PasswordFlow(token_url="token")


@me.get(auth_scheme=token_based)
async def get_user(token: JWTAuth[UserProfile]) -> User:
    assert token.user_id == "user123"
    return User(name="user", email="user@email.com")


@me.sub("test").get(auth_scheme=token_based)
async def get_another_user(token: JWTAuth[UserProfile]) -> User:
    assert token.user_id == "user123"
    return User(name="user", email="user@email.com")


class UserPayload(Payload):
    user_name: Annotated[str, Meta(min_length=1)]

all_users =Route("/users")

@all_users.sub("{user_id}").post
async def create_user(
    user_id: str,                                           # from URL path
    auth_token: Header[str, Literal["x-auth-token"]],       # from request headers
    user_data: UserPayload                                  # from request body
):
    # All parameters are automatically parsed and validated
    ...


@token.post
async def create_token(credentials: OAuthLoginForm) -> JWTAuth[UserProfile]:
    assert credentials.username == "admin" and credentials.password == "admin"
    return UserProfile(user_id="user123")


lhl = Lihil[None](routes=[me, token])


if __name__ == "__main__":
    lhl.run(__file__)
