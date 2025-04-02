# TODO: builtin-jwt mechanism
from typing import Annotated, Any, Literal

from ididi import Resolver
from msgspec import field

from lihil.constant import status
from lihil.interface import Base, CustomDecoder, Form, Header, Payload
from lihil.interface.marks import param_mark
from lihil.oas.model import OAuth2, OAuthFlowPassword, OAuthFlows
from lihil.plugins.provider import PluginProvider
from lihil.problems import HTTPException
from lihil.vendor_types import Request

# type LoginForm = Form[]
# https://datatracker.ietf.org/doc/html/rfc6749


class OauthLoginForm(Payload):
    grant_type: str | None
    username: str
    password: str
    scope: str
    client_id: str | None
    client_secret: str | None
    scopes: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.scopes.extend(self.scope.split())


type LoginForm = Form[OauthLoginForm]


class OAuth2Plugin(PluginProvider[str | None], Base):
    scheme_name: str
    flows: OAuthFlows
    description: str | None = None
    auto_error: bool = True
    model: OAuth2 | None = None

    def __post_init__(self):
        self.model = OAuth2(flows=self.flows, description=self.description)

    async def load(self, request: Request, resolver: Resolver) -> str | None:
        authorization = request.headers.get("Authorization")
        if not authorization:
            if self.auto_error:
                raise HTTPException(problem_status=401, detail="Not authenticated")
            else:
                return None
        return authorization


class OAuth2Password(OAuth2Plugin, kw_only=True):
    tokenUrl: str
    scheme_name: str
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
