from time import time
from types import UnionType
from typing import Annotated, Any, ClassVar, Literal, Sequence, TypedDict, TypeVar, cast
from uuid import uuid4

from ididi import Graph
from msgspec import convert
from typing_extensions import Required, Unpack, dataclass_transform

from lihil.config import lhl_get_config
from lihil.config.app_config import AppConfig, Doc, IAppConfig
from lihil.errors import AppConfiguringError, NotSupportedError
from lihil.interface import (
    MISSING,
    UNSET,
    Base,
    IAsyncFunc,
    P,
    R,
    T,
    Unset,
    field,
    is_provided,
)
from lihil.problems import InvalidAuthError
from lihil.signature import EndpointSignature, Param
from lihil.utils.json import encode_json
from lihil.utils.typing import lexient_issubclass


def jwt_timeclaim():
    return int(time())


def uuid_factory() -> str:
    return str(uuid4())


class IJWTConfig(IAppConfig):
    @property
    def JWT_SECRET(SELF) -> str: ...
    @property
    def JWT_ALGORITHMS(self) -> str | Sequence[str]: ...


class JWTConfig(AppConfig, kw_only=True):
    JWT_SECRET: Annotated[str, Doc("Secret key for encoding and decoding JWTs")]
    JWT_ALGORITHMS: Annotated[
        str | Sequence[str], Doc("List of accepted JWT algorithms")
    ]


class JWTClaims(TypedDict, total=False):
    """
    exp_in: expire in x seconds

    """

    expires_in: Required[int]
    iss: str
    aud: str


class JWTOptions(TypedDict, total=False):
    verify_signature: bool
    verify_exp: bool
    verify_nbf: bool
    verify_iat: bool
    verify_aud: bool
    verify_iss: bool
    verify_sub: bool
    verify_jti: bool
    require: list[Any]


@dataclass_transform(kw_only_default=True)
class JWTPayload(Base, kw_only=True):
    # reff: https://en.wikipedia.org/wiki/JSON_Web_Token
    """
    | Code | Name             | Description                                                                 |
    |------|------------------|-----------------------------------------------------------------------------|
    | iss  | Issuer           | Principal that issued the JWT.                                              |
    | sub  | Subject          | The subject of the JWT.                                                     |
    | aud  | Audience         | The recipients that the JWT is intended for.                                |
    | exp  | Expiration Time  | The expiration time on and after which the JWT must not be accepted.        |
    | nbf  | Not Before       | The time on which the JWT will start to be accepted. Must be a NumericDate. |
    | iat  | Issued At        | The time at which the JWT was issued. Must be a NumericDate.                |
    | jti  | JWT ID           | Case-sensitive unique identifier of the token, even among different issuers.|
    """
    # sub: str

    __jwt_claims__: ClassVar[JWTClaims] = {"expires_in": -1}

    jti: str = field(default_factory=uuid_factory)

    exp: Unset[int] = UNSET
    nbf: Unset[int] = UNSET
    iat: Unset[int] = UNSET
    iss: Unset[str] = UNSET
    aud: Unset[str] = UNSET

    def __post_init__(self):
        exp_in = self.__jwt_claims__.get("expires_in")
        if not exp_in or exp_in <= 0:
            raise NotSupportedError(
                f"Invalid value for `expires_in`, expects a positive int, received: {exp_in}"
            )

        if is_provided(aud := self.__jwt_claims__.get("aud", MISSING)):
            self.aud = aud

        if is_provided(iss := self.__jwt_claims__.get("iss", MISSING)):
            self.iss = iss

        now_ = jwt_timeclaim()
        self.exp = now_ + exp_in
        self.nbf = self.iat = now_

    def validate_claims(self) -> None: ...


class OAuth2Token(Base):
    "https://www.oauth.com/oauth2-servers/access-tokens/access-token-response/"

    access_token: str
    expires_in: int
    token_type: Literal["Bearer"] = "Bearer"
    refresh_token: Unset[str] = UNSET
    scope: Unset[str] = UNSET


# TODO: make this a plugin

try:
    from jwt import PyJWT
    from jwt.api_jws import PyJWS
    from jwt.exceptions import InvalidTokenError
except ImportError:
    pass
else:

    def jwt_encoder_factory(
        *, payload_type: type[T] | UnionType, app_config: IAppConfig | None = None
    ):
        app_config = app_config or lhl_get_config()

        if not hasattr(app_config, "JWT_SECRET") or not hasattr(
            app_config, "JWT_ALGORITHMS"
        ):
            raise AppConfiguringError(
                f"JWTAuth requires 'JWT_SECRET' and 'JWT_ALGORITHMS' attributes in {type(app_config)}"
            )

        config = cast(IJWTConfig, app_config)
        secret = config.JWT_SECRET
        algorithms = config.JWT_ALGORITHMS
        options = None

        if not isinstance(payload_type, type) or not lexient_issubclass(
            payload_type, (JWTPayload, str)
        ):
            raise NotSupportedError(
                f"payload type must be str or subclass of JWTPayload, got {payload_type}"
            )

        if isinstance(algorithms, str):
            algorithms = [algorithms]

        jws_encode = PyJWS(algorithms=algorithms, options=options).encode

        if lexient_issubclass(payload_type, JWTPayload):
            try:
                encode_fields = getattr(payload_type, "__struct_encode_fields__")
                assert "sub" in encode_fields or "sub" in payload_type.__struct_fields__
            except (AttributeError, AssertionError):
                raise NotSupportedError(
                    "JWTPayload class must have a field with name `sub` or field(name=`sub`)"
                )

        def encoder(content: JWTPayload) -> bytes:
            payload_bytes = encode_json(content)
            jwt = jws_encode(payload_bytes, key=secret)
            expires = content.__jwt_claims__["expires_in"]
            token_resp = OAuth2Token(access_token=jwt, expires_in=expires)
            resp = encode_json(token_resp)
            return resp

        return encoder

    class JWTAuthPlugin:
        def __init__(
            self,
            jwt_secret: str,
            jwt_algorithms: str | Sequence[str],
            **options: Unpack[JWTOptions],
        ):
            self.jwt_secret = jwt_secret
            self.jwt_algorithms: Sequence[str] = (
                [jwt_algorithms] if isinstance(jwt_algorithms, str) else jwt_algorithms
            )
            self.options = options
            self.jwt = PyJWT(options=options)

        def decode_plugin(
            self, graph: Graph, func: IAsyncFunc[P, R], sig: EndpointSignature[Any]
        ) -> IAsyncFunc[P, R]:
            for _, param in sig.header_params.items():
                if param.alias == "Authorization":
                    if lexient_issubclass(param.type_, JWTPayload):
                        param.decoder = self.jwt_decode_factory(param.type_)
            return func

        def encode_plugin(self, scheme_type: type[OAuth2Token]):
            def jwt_encoder_factory(
                graph: Graph, func: IAsyncFunc[P, R], sig: EndpointSignature[Any]
            ) -> IAsyncFunc[P, R]:

                for code, param in sig.return_params.items():
                    param_type = param.type_
                    if issubclass(param_type, JWTPayload):

                        def encode_jwt(content: JWTPayload) -> bytes:
                            payload_bytes = encode_json(content)
                            jwt = PyJWS(algorithms=self.jwt_algorithms).encode(
                                payload_bytes, key=self.jwt_secret
                            )
                            expires = param_type.__jwt_claims__["expires_in"]
                            token_resp = OAuth2Token(
                                access_token=jwt, expires_in=expires
                            )
                            resp = encode_json(token_resp)
                            return resp

                        sig.return_params[code] = param.replace(encoder=encode_jwt)
                    break

                return func

            return jwt_encoder_factory

        def jwt_decode_factory(self, payload_type: JWTPayload):
            def decode_jwt(content: str | list[str]):
                if isinstance(content, list):
                    raise InvalidAuthError(
                        "Multiple authorization headers are not allowed"
                    )

                try:
                    scheme, _, token = content.partition(" ")
                    if scheme.lower() != "bearer":
                        raise InvalidAuthError(f"Invalid authorization scheme {scheme}")

                    decoded: dict[str, Any] = self.jwt.decode(
                        token, key=self.jwt_secret, algorithms=self.jwt_algorithms
                    )
                    return convert(decoded, payload_type)
                except InvalidTokenError:
                    raise InvalidAuthError("Unable to validate your credential")

            return decode_jwt


TPayload = TypeVar("TPayload", bound=JWTPayload | str | bytes)

JWTAuth = Annotated[
    TPayload,
    Param("header", alias="Authorization", extra_meta=dict(skip_unpack=True)),
    "application/json",
]

"""
async def login(user_profile: Annotated[UserProfile, Param("header", alias="Authorization")]) -> OAuth2Token:
"""
