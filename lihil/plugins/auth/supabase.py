from typing import Annotated, Literal

from gotrue import AuthResponse
from gotrue import types as auth_types
from gotrue.errors import AuthError
from supabase import AsyncClient
from typing_extensions import Unpack

from lihil import use
from lihil.interface import HTTP_METHODS
from lihil.problems import HTTPException
from lihil.routing import IEndpointProps, Route
from lihil.signature.params import Form


def signup_route_factory(
    route_path: str,
    *,
    sign_up_with: Literal["phone", "email"] = "email",
    method: HTTP_METHODS = "POST",
    **props: Unpack[IEndpointProps],
):
    if sign_up_with == "email":
        SignupForm = Annotated[auth_types.SignUpWithEmailAndPasswordCredentials, Form()]
    else:
        SignupForm = Annotated[auth_types.SignUpWithPhoneAndPasswordCredentials, Form()]

    async def supabase_signup(
        singup_form: SignupForm,
        client: Annotated[AsyncClient, use(AsyncClient, ignore="options")],
    ) -> auth_types.User:
        try:
            resp: AuthResponse = await client.auth.sign_up(singup_form)
        except AuthError as ae:
            raise HTTPException(str(ae), problem_status=400)

        if resp.user is None:
            raise HTTPException("User not created", problem_status=400)
        return resp.user

    route = Route(route_path)
    route.add_endpoint(method, func=supabase_signup, **props)
    return route


def signin_route_factory(
    route_path: str,
    *,
    sign_in_with: Literal["phone", "email"] = "email",
    method: HTTP_METHODS = "POST",
    **props: Unpack[IEndpointProps],
):
    if sign_in_with == "email":
        LoginForm = Annotated[auth_types.SignInWithEmailAndPasswordCredentials, Form()]
    elif sign_in_with == "phone":
        LoginForm = Annotated[auth_types.SignInWithPhoneAndPasswordCredentials, Form()]

    async def supabase_signin(
        login_form: LoginForm,
        client: Annotated[AsyncClient, use(AsyncClient, ignore="options")],
    ) -> auth_types.User:
        match sign_in_with:
            case "email":
                api = client.auth.sign_in_with_password(login_form)
            case "phone":
                api = client.auth.sign_in_with_password(login_form)
            case _:
                raise Exception

        try:
            resp: AuthResponse = await api
        except AuthError as ae:
            raise HTTPException(str(ae), problem_status=400)

        if resp.user is None:
            raise HTTPException(
                "User not found or invalid credentials", problem_status=401
            )
        return resp.user

    route = Route(route_path)
    route.add_endpoint(method, func=supabase_signin, **props)
    return route
