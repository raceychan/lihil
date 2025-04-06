from typing import ClassVar

# from ididi import Resolver
from msgspec import field

from lihil.interface import UNSET, Form, Payload, Unset
from lihil.oas.model import AuthModel, OAuth2, OAuthFlowPassword, OAuthFlows

# from lihil.problems import HTTPException
# from lihil.vendor_types import Request


class AuthBase:
    "A base class for all auth schemes"

    def __init__(self, model: AuthModel, scheme_name: str):
        self.model = model  # security base model
        self.scheme_name = scheme_name


class OAuthLogin(Payload):
    """
    use this with Form

    login_form: Form[OAuthLoginForm]
    """

    username: str
    password: str
    grant_type: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scope: str = ""
    scopes: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.scopes.extend(self.scope.split())


# refference: https://datatracker.ietf.org/doc/html/rfc6749
type OAuthLoginForm = Form[OAuthLogin]


class OAuth2Base(AuthBase):
    scheme_name: ClassVar[str]

    def __init__(
        self,
        description: Unset[str] = UNSET,
        auto_error: bool = True,
        flows: OAuthFlows | None = None,
        scheme_name: str | None = None,
    ):
        self.description = description
        self.auto_error = auto_error

        assert self.scheme_name, "scheme name not set"

        super().__init__(
            model=OAuth2(flows=flows or OAuthFlows(), description=self.description),
            scheme_name=scheme_name or self.scheme_name,
        )


class OAuth2PasswordFlow(OAuth2Base):
    scheme_name = "OAuth2PasswordBearer"

    # app_config: AppConfig

    def __init__(
        self,
        *,
        description: Unset[str] = UNSET,
        auto_error: bool = True,
        flows: OAuthFlows | None = None,
        scheme_name: str | None = None,
        token_url: str,
        scopes: dict[str, str] | None = None,
    ):
        flows = OAuthFlows(
            password=OAuthFlowPassword(tokenUrl=token_url, scopes=scopes or {})
        )
        super().__init__(
            flows=flows,
            description=description,
            auto_error=auto_error,
            scheme_name=scheme_name,
        )
