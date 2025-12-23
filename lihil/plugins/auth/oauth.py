from typing import Annotated, ClassVar, Literal

from msgspec import field

from lihil.interface import UNSET, Base, Payload, UnsetType, Unset
from lihil.oas.model import (
    OASAuthModel,
    OASOAuth2,
    OASOAuthFlowPassword,
    OASOAuthFlows,
)
from lihil.signature.params import Form


class OAuth2Token(Base):
    "https://www.oauth.com/oauth2-servers/access-tokens/access-token-response/"

    access_token: str
    expires_in: int
    token_type: Literal["Bearer"] = "Bearer"
    refresh_token: Unset[str] = UNSET
    scope: Unset[str] = UNSET


class OAuthLogin(Payload):
    """
    OAuth2 login form model.

    This model is used to represent the data required for OAuth2 password grant type authentication.
    It includes fields for username, password, grant type, client ID, client secret, scope, and scopes.
    refference: https://datatracker.ietf.org/doc/html/rfc6749
    """

    username: str
    password: str
    grant_type: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scope: str = ""
    scopes: list[str] = field(default_factory=list[str])

    def __post_init__(self):
        self.scopes.extend(self.scope.split())


OAuthLoginForm = Annotated[OAuthLogin, Form()]


class AuthBase:
    "A base class for all auth schemes"

    def __init__(
        self,
        model: OASAuthModel,
        scheme_name: str,
        scopes: dict[str, str] | None = None,
    ):
        self.model = model
        self.scheme_name = scheme_name
        self.scopes = scopes


class OAuth2Base(AuthBase):
    scheme_name: ClassVar[str]

    def __init__(
        self,
        description: UnsetType | str = UNSET,
        auto_error: bool = True,
        flows: OASOAuthFlows | None = None,
        scheme_name: str | None = None,
        scopes: dict[str, str] | None = None,
    ):
        self.description = description
        self.auto_error = auto_error

        assert self.scheme_name, "scheme name not set"

        super().__init__(
            model=OASOAuth2(
                flows=flows or OASOAuthFlows(), description=self.description
            ),
            scheme_name=scheme_name or self.scheme_name,
            scopes=scopes,
        )


class OAuth2PasswordFlow(OAuth2Base):
    scheme_name = "OAuth2PasswordBearer"

    def __init__(
        self,
        *,
        token_url: str,
        description: UnsetType | str = UNSET,
        auto_error: bool = True,
        flows: OASOAuthFlows | None = None,
        scheme_name: str | None = None,
        scopes: dict[str, str] | None = None,
    ):

        password_flow = OASOAuthFlowPassword(tokenUrl=token_url, scopes=(scopes or {}))
        flows = OASOAuthFlows(password=password_flow)
        super().__init__(
            flows=flows,
            description=description,
            auto_error=auto_error,
            scheme_name=scheme_name,
            scopes=scopes,
        )
