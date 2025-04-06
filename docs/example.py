from lihil import Lihil, Payload, Route, field
from lihil.plugins.auth.jwt import JWToken, JWTPayload

# from lihil.plugins.auth import OAuth2PasswordPlugin, OAuthLoginForm
from lihil.plugins.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm

users = Route("users")


class UserPayload(JWTPayload):
    __jwt_claims__ = {"exp_in": 300}

    user_id: str = field(name="sub")


class User(Payload):
    name: str
    email: str


@users.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))
async def get_user(token: JWToken[UserPayload]) -> User:
    assert token.user_id == "user123"
    return User(name="user", email="user@email.com")


token = Route("token")


@token.post
async def create_token(credentials: OAuthLoginForm) -> JWToken[UserPayload]:
    assert credentials.username == "admin" and credentials.password == "admin"
    return UserPayload(user_id="user123")


lhl = Lihil[None](routes=[users, token])

# =============================

# from typing import Annotated

# from fastapi import Depends, FastAPI
# from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# lhl = FastAPI()


# # @lhl.post("/token")
# # async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]): ...


# @lhl.get("/me")
# async def read_users_me(
#     token: Annotated[str, Depends(OAuth2PasswordBearer(tokenUrl="token"))],
# ):
#     return token
