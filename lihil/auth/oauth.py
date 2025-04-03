from ididi import Resolver
from msgspec import field

# from lihil.constant import status
from lihil.interface import Base, Payload

# from lihil.interface.marks import param_mark
from lihil.oas.model import AuthBase, OAuth2, OAuthFlowPassword, OAuthFlows

# from lihil.plugins.provider import PluginProvider, register_plugin_provider
from lihil.problems import HTTPException
from lihil.vendor_types import Request

# type LoginForm = Form[]
# https://datatracker.ietf.org/doc/html/rfc6749

"""
TODO:
since password grant is already deprecated,
we should first make an ordinary login form here
"""

# class UserCredential


# type LoginForm


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


# class AuthPlugin[Model: AuthBase](Base):
#     # security base
#     model: Model  # security base model
#     scheme_name: str


# class OAuth2Plugin(AuthPlugin[OAuth2]):
#     flows: OAuthFlows = OAuthFlows()
#     scheme_name: str | None = None
#     description: str | None = None
#     auto_error: bool = True
#     model: OAuth2 | None = None

#     def __post_init__(self):
#         self.model = OAuth2(flows=self.flows, description=self.description)
#         self.scheme_name = self.scheme_name or self.__class__.__name__

#     async def load(self, request: Request, resolver: Resolver) -> str | None:
#         authorization = request.headers.get("Authorization")
#         if not authorization:
#             if self.auto_error:
#                 raise HTTPException(problem_status=401, detail="Not authenticated")
#             else:
#                 return None
#         return authorization


# class OAuth2PasswordPlugin(OAuth2Plugin, kw_only=True):
#     tokenUrl: str
#     scopes: dict[str, str] = field(default_factory=dict)

#     def __post_init__(self):
#         self.flows = OAuthFlows(
#             password=OAuthFlowPassword(tokenUrl=self.tokenUrl, scopes=self.scopes)
#         )

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
