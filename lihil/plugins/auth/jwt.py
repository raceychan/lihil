from time import time
from types import UnionType
from typing import Annotated, Any, Literal, Sequence, TypedDict
from uuid import uuid4

from ididi import Graph
from msgspec import convert
from msgspec.structs import asdict as struct_asdict
from typing_extensions import Required, Unpack

from lihil.config.app_config import AppConfig, Doc, IAppConfig
from lihil.interface import UNSET, Base, IAsyncFunc, P, R, Struct, Unset
from lihil.problems import InvalidAuthError
from lihil.signature import EndpointSignature, Param
from lihil.utils.json import encoder_factory


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


class OAuth2Token(Base):
    "https://www.oauth.com/oauth2-servers/access-tokens/access-token-response/"

    access_token: str
    expires_in: int
    token_type: Literal["Bearer"] = "Bearer"
    refresh_token: Unset[str] = UNSET
    scope: Unset[str] = UNSET


try:
    from jwt import PyJWT
    from jwt.api_jws import PyJWS
    from jwt.exceptions import InvalidTokenError
except ImportError:
    pass
else:

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
            self.jws = PyJWS(algorithms=self.jwt_algorithms, options=options)

        def decode_plugin(
            self, graph: Graph, func: IAsyncFunc[P, R], sig: EndpointSignature[Any]
        ) -> IAsyncFunc[P, R]:
            for _, param in sig.header_params.items():
                if param.source == "header" and param.alias == "Authorization":
                    param.decoder = self.jwt_decode_factory(param.type_)

            return func

        def encode_plugin(
            self,
            expires_in_s: int,
            iss: str | None = None,
            nbf: int | None = None,
            aud: str | None = None,
            scheme_type: type[OAuth2Token] = OAuth2Token,
        ):
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
            if expires_in_s < 0:
                raise ValueError(
                    "expires_in_s must be greater than 0, got {expires_in_s}"
                )

            def jwt_encoder_factory(
                graph: Graph, func: IAsyncFunc[P, R], sig: EndpointSignature[Any]
            ) -> IAsyncFunc[P, R]:
                encoder = encoder_factory()

                def encode_jwt(content: Struct | str) -> bytes:
                    if isinstance(content, str):
                        payload_dict: dict[str, Any] = dict(sub=content)
                    else:
                        payload_dict = struct_asdict(content)

                    payload_dict["iat"] = now_ = jwt_timeclaim()
                    payload_dict["jti"] = uuid_factory()
                    payload_dict["exp"] = now_ + expires_in_s

                    if iss is not None:
                        payload_dict["iss"] = iss
                    if nbf is not None:
                        payload_dict["nbf"] = nbf
                    if aud is not None:
                        payload_dict["aud"] = aud

                    payload_bytes = encoder(content)
                    jwt = self.jws.encode(payload_bytes, key=self.jwt_secret)
                    token_resp = scheme_type(access_token=jwt, expires_in=expires_in_s)
                    resp = encoder(token_resp)
                    return resp

                sig.default_return.encoder = encode_jwt

                return func

            return jwt_encoder_factory

        def jwt_decode_factory(self, payload_type: type | UnionType):
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
                    if payload_type is str:
                        return decoded["sub"]
                    return convert(decoded, payload_type)
                except InvalidTokenError:
                    raise InvalidAuthError("Unable to validate your credential")

            return decode_jwt


"""
async def login(user_profile: Annotated[UserProfile, Param("header", alias="Authorization")]) -> OAuth2Token:
"""

JWTAuthParam = Param("header", alias="Authorization", extra_meta=dict(skip_unpack=True))
# JWTCookieParam = Param(
#     "cookie", alias="access_token", extra_meta=dict(skip_unpack=True)
# )
