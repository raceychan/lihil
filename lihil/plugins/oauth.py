# TODO: builtin-jwt mechanism
from typing import Annotated, Any, Literal

from ididi import Resolver
from msgspec import field

from lihil.constant import status
from lihil.di.params import PluginProvider
from lihil.interface import CustomDecoder, Form, Header, Payload
from lihil.interface.marks import param_mark
from lihil.oas.model import OAuth2, OAuthFlows
from lihil.problems import HTTPException
from lihil.vendor_types import Request

# type LoginForm = Form[]
# https://datatracker.ietf.org/doc/html/rfc6749


# class OauthLoginForm(Payload):
#     grant_type: str | None
#     username: str
#     password: str
#     scope: str
#     client_id: str | None
#     client_secret: str | None
#     scopes: list[str] = field(default_factory=list)

#     def __post_init__(self):
#         self.scopes.extend(self.scope.split())


# type LoginForm = Form[OauthLoginForm]


# class OAuth2Plugin(PluginProvider[str | None], Payload):
#     model: OAuth2
#     scheme_name: str
#     auto_error: bool = True

#     async def load(self, request: Request, resolver: Resolver) -> str | None:
#         authorization = request.headers.get("Authorization")
#         if not authorization:
#             if self.auto_error:
#                 raise HTTPException(problem_status=401, detail="Not authenticated")
#             else:
#                 return None
#         return authorization


# class OAuth2PasswordBearer(OAuth2Plugin, kw_only=True):
#     tokenUrl: str
#     scheme_name: str
#     scopes: dict[str, str] | None = None
#     description: str | None
#     auto_error: bool = True

#     async def load(self, request: Request, resolver: Resolver) -> str | None:
#         authorization = request.headers.get("Authorization")

#         if not authorization:
#             scheme, param = "", ""
#         else:
#             scheme, _, param = authorization.partition(" ")

#         if not authorization or scheme.lower() != "bearer":
#             if self.auto_error:
#                 raise HTTPException(
#                     problem_status=401,
#                     detail="Not authenticated",
#                     headers={"WWW-Authenticate": "Bearer"},
#                 )
#             else:
#                 return None
#         return param


# def auth_decoder(auth: str):
#     if not auth:
#         scheme, param = "", ""
#     else:
#         scheme, _, param = auth.partition(" ")

#     if not auth or scheme.lower() != "bearer":
#         raise HTTPException(
#             problem_status=401,
#             detail="Not authenticated",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     return param


# type AuthHeader = Annotated[
#     Header[OAuth2PasswordBearer, Literal["Authorization"]], CustomDecoder(auth_decoder)
# ]
