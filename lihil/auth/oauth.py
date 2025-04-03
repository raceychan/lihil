from typing import Any

from ididi import Resolver
from msgspec import field

from lihil.interface import Payload
from lihil.interface.marks import param_mark
from lihil.oas.model import AuthBase, OAuth2, OAuthFlowPassword, OAuthFlows
from lihil.plugins.provider import ProviderMixin, register_plugin_provider
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


class OAuthLogin(Payload):
    """
    use this with Form

    login_form: Form[OAuthLoginForm]
    """

    grant_type: str | None
    username: str
    password: str
    scope: str
    client_id: str | None
    client_secret: str | None
    scopes: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.scopes.extend(self.scope.split())


class AuthProvider[Model: AuthBase](ProviderMixin[Any]):
    # security base

    def __init__(self, model: Model, scheme_name: str):
        self.model = model  # security base model
        self.scheme_name = scheme_name


# class AccessControl(Base):
#     # security requirement
#     security_scheme: AuthPlugin[Any]
#     scopes: Sequence[str] | None = None


# OAuth2Provider
class OAuth2Provider(AuthProvider[OAuth2]):

    def __init__(
        self,
        description: str,
        auto_error: bool,
        flows: OAuthFlows | None = None,
        scheme_name: str | None = None,
    ):
        self.description = description
        self.auto_error = auto_error

        super().__init__(
            model=OAuth2(flows=flows or OAuthFlows(), description=self.description),
            scheme_name=scheme_name or self.__class__.__name__,
        )

    async def load(self, request: Request, resolver: Resolver) -> str | None:
        authorization = request.headers.get("Authorization")
        if not authorization:
            if self.auto_error:
                raise HTTPException(problem_status=401, detail="Not authenticated")
            else:
                return None
        return authorization


class OAuth2PasswordPlugin(OAuth2Provider):
    tokenUrl: str
    scopes: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.flows = OAuthFlows(
            password=OAuthFlowPassword(tokenUrl=self.tokenUrl, scopes=self.scopes)
        )

    async def load(self, request: Request, resolver: Resolver) -> str | None:
        authorization = request.headers.get("Authorization")

        if not authorization:
            scheme, param = "", ""
        else:
            scheme, _, param = authorization.partition(" ")

        if not authorization or scheme.lower() != "bearer":
            if self.auto_error:
                raise HTTPException(
                    problem_status=401,
                    detail="Not authenticated",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            else:
                return None
        return param
