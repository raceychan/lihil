from lihil import Annotated, Lihil, Route
from lihil.plugins.auth import OAuth2PasswordPlugin, OAuthLoginForm

users = Route("users")


@users.get
async def get_user(
    name: str, token: Annotated[str, OAuth2PasswordPlugin(token_url="token")]
): ...


token = Route("token")


@token.post
async def create_token(credentials: OAuthLoginForm): ...


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
