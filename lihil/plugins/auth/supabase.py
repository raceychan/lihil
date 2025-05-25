from typing import Annotated

from gotrue import types as auth_types
from ididi import use
from supabase import AsyncClient

from lihil.problems import HTTPException
from lihil.signature.params import Form


async def supabase_signup(
    client: Annotated[AsyncClient, use(AsyncClient)],
    singup_form: Annotated[auth_types.SignUpWithEmailAndPasswordCredentials, Form()],
):
    resp = await client.auth.sign_up(singup_form)

    if resp.user is None:
        raise HTTPException("User not created", problem_status=400)
    return resp.user


def sign_in_endpoint_factory(
    cred_type: type[
        auth_types.SignInWithEmailAndPasswordCredentials
        | auth_types.SignInWithPhoneAndPasswordCredentials
    ],
    client: AsyncClient,
):

    match cred_type:
        case auth_types.SignInWithEmailAndPasswordCredentials:
            api = client.auth.sign_in_with_password

        case auth_types.SignInWithIdTokenCredentials:
            api = client.auth.sign_in_with_id_token

        case _:
            raise TypeError(f"{cred_type} not supported")

    async def supabase_signin(credentials: Annotated[cred_type, Form()]):

        resp = await api(credentials)

        if resp.user is None:
            raise HTTPException(
                "User not found or invalid credentials", problem_status=401
            )
        return resp.user

    return supabase_signin
