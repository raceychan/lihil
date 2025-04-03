# from lihil import Form, Lihil, Route, Text
# from lihil.auth.oauth import OAuthLoginForm
#
# token = Route("/token")
#
#
# @token.post
# async def create_token(login_form: Form[OAuthLoginForm]): ...
#
#
# lhl = Lihil[None](routes=[token])


from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

lhl = FastAPI()


@lhl.post("/token")
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]): ...


@lhl.get("/me")
async def read_users_me(
    token: Annotated[str, Depends(OAuth2PasswordBearer(tokenUrl="token"))],
):
    return token
