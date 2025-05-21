# from inspect import signature


# from lihil import Request
# from supabase import AsyncClient

# # from lihil.errors import MissingDependencyError
# from lihil.routing import Route
# from lihil.interface import AppState, Record

from supabase import AsyncClient

from gotrue.types import SignInWithIdTokenCredentials as SignInWithIdTokenCredentials




class SupabasePlugin:
    def __init__(self, supabase: AsyncClient):
        self.supabase = supabase

    async def __call__(self, email: str, password: str):
        ...

        self.supabase.auth.sign_in_with_id_token()
        # user = await self.supabase.auth.sign_up(email=email, password=password)
        # return user


# class PhoneSignup(Record): ...


# def create_singup(client_name: str):
#     async def signup(dummy: AppState[AsyncClient]): ...

#     fsig = signature(signup)
#     # fsig.parameters[]
#     fsig.replace()

#     return signup


# func = create_singup("supb")
