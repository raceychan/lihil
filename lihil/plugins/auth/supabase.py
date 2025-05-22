

try:
    from gotrue.types import (
        SignInWithIdTokenCredentials as SignInWithIdTokenCredentials,
    )
    from supabase import AsyncClient
except ImportError:
    pass
else:

    def generate_login_function(): ...


# class SupabasePlugin:
#     def __init__(self, supabase: AsyncClient):
#         self.supabase = supabase

#     async def __call__(self, email: str, password: str):
#         ...

#         self.supabase.auth.sign_in_with_id_token()
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
