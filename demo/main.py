from typing import Literal

from lihil import Annotated, Lihil, Route, Struct, status
from lihil.plugins.auth.jwt import JWTAuthParam
from lihil.plugins.auth.oauth import OAuth2PasswordFlow

root = Route()


UserNames = Literal["alice", "bob", "charlie"]


@root.sub("/user").get
async def get_user(user_name: UserNames | None): ...


class UserProfile(Struct):
    user_name: str
    full_name: str | None = None
    age: int | None = None


@root.sub("/me").get(auth_scheme=OAuth2PasswordFlow(token_url="/token"))
async def get_me(profile: Annotated[str, JWTAuthParam]) -> UserProfile:
    return profile


@root.sub("/status").get
async def get_status() -> (
    Annotated[str, status.OK] | Annotated[int, status.CREATED]
): ...


app = Lihil(root)
