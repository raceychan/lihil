from typing import Literal

from lihil import Lihil, Payload, Route, field
from lihil.auth.jwt import JWTAuth, JWTPayload
from lihil.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm
from lihil.config import AppConfig, SecurityConfig

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


@token.post
async def create_token(credentials: OAuthLoginForm) -> JWTAuth[UserProfile]:
    assert credentials.username == "admin" and credentials.password == "admin"
    return UserProfile(user_id="user123")


lhl = Lihil[None](routes=[me, token])

# =============================

# from typing import Annotated

# from fastapi import Depends, FastAPI
# from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# lhl = FastAPI()


# @lhl.post("/token")
# async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]): ...


# @lhl.get("/me")
# async def read_users_me(
#     token: Annotated[str, Depends(OAuth2PasswordBearer(tokenUrl="token"))],
# ):
#     return token


if __name__ == "__main__":
    lhl.run(__file__)
