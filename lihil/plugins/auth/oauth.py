from typing import Any, ClassVar

from ididi import Resolver
from msgspec import field

from lihil.interface import UNSET, Form, Payload, Unset
from lihil.oas.model import AuthBase, OAuth2, OAuthFlowPassword, OAuthFlows
from lihil.plugins.registry import PluginBase  # , PluginParam
from lihil.problems import HTTPException
from lihil.vendor_types import Request


class AuthPlugin(PluginBase):
    # security base

    def __init__(self, model: AuthBase, scheme_name: str):
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


class OAuth2Plugin(AuthPlugin):
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

        self._param_name = ""

    async def process(
        self, params: dict[str, Any], request: Request, resolver: Resolver
    ) -> None:
        authorization = request.headers.get("Authorization")
        if not authorization:
            if self.auto_error:
                raise HTTPException(problem_status=401, detail="Not authenticated")
            else:
                return None

        params[self._param_name] = authorization


class OAuth2PasswordFlow(OAuth2Plugin):
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

        self._param_name: str = ""

    # TODO: let loader receive params: dict[str, Any]
    async def process(
        self, params: dict[str, Any], request: Request, resolver: Resolver
    ) -> None:
        """
        # TODO: get app_config from request.app.app_config
        # override parse, parse payload type from type
        """
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

        assert self._param_name
        params[self._param_name] = param
