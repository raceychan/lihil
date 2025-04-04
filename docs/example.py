from lihil import Annotated, Form, Lihil, Route, Text
from lihil.auth.oauth import OAuth2PasswordPlugin

users = Route("users")


@users.get
async def get_user(
    name: str, token: Annotated[str, OAuth2PasswordPlugin(token_url="token")]
): ...


get_user_ep = users.get_endpoint(get_user)

lhl = Lihil[None](routes=[users])

# # =============================

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
