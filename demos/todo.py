from lihil import Annotated, Lihil, Param, Route
from lihil.plugins.auth.jwt import JWTAuthParam
from lihil.plugins.auth.oauth import OAuth2PasswordFlow, OAuth2Token, OAuthLoginForm

tokens = Route("/token")
me = Route("/users/me")


@tokens.post
async def login_get_token(form: OAuthLoginForm):
    return OAuth2Token("123", 123)


@me.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))
async def get_user(
    auth: Annotated[str | None, Param("header", alias="authorization")] = "",
):
    breakpoint()


async def debug(app):
    yield


lhl = Lihil(lifespan=debug)
lhl.include_routes(tokens, me)

if __name__ == "__main__":
    lhl.run(__file__)
