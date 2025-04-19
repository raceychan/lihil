from time import time
from types import UnionType
from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    Required,
    Sequence,
    TypedDict,
    dataclass_transform,
)
from uuid import uuid4

from msgspec import convert

from lihil.errors import NotSupportedError
from lihil.interface import MISSING, UNSET, Base, Unset, field, is_provided
from lihil.interface.marks import HEADER_REQUEST_MARK, JW_TOKEN_RETURN_MARK
from lihil.problems import InvalidAuthError
from lihil.utils.json import encode_json


def jwt_timeclaim():
    return int(time())


def uuid_factory() -> str:
    return str(uuid4())


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


# from starlette.responses import Response
# class TokenResponse(Response): ...


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

    def jwt_encoder_factory[T](
        *,
        secret: str,
        algorithms: str | Sequence[str],
        options: JWTOptions | None = None,
        payload_type: type[T] | UnionType,
    ):

        if not isinstance(payload_type, type) or not issubclass(
            payload_type, (JWTPayload, str)
        ):
            raise NotSupportedError(
                "payload type must be str or subclass of JWTPayload"
            )

        if isinstance(algorithms, str):
            algorithms = [algorithms]

        jws_encode = PyJWS(algorithms=algorithms, options=options).encode

        if issubclass(payload_type, JWTPayload):
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

    def jwt_decoder_factory[T](
        *,
        secret: str,
        algorithms: str | Sequence[str],
        options: JWTOptions | None = None,
        payload_type: type[T] | UnionType,
    ):

        jwt = PyJWT(options)  # type: ignore

        def decoder(content: str) -> T:
            try:
                scheme, _, token = content.partition(" ")
                if scheme.lower() != "bearer":
                    raise InvalidAuthError(f"Invalid authorization scheme {scheme}")
                # TODO: rewrite jwt.decode_complete
                # payload = decode(deocded)
                # payload.validate_claims()
                # return payload

                algos = [algorithms] if isinstance(algorithms, str) else algorithms

                decoded: dict[str, Any] = jwt.decode(
                    token, key=secret, algorithms=algos
                )
                return convert(decoded, payload_type)
            except InvalidTokenError:
                raise InvalidAuthError("Not able to validate your credential")

        return decoder


type AuthHeader[T] = Annotated[T, Literal["Authorization"], HEADER_REQUEST_MARK]
type JWTAuth[T: JWTPayload | str | bytes] = Annotated[
    AuthHeader[T],
    JW_TOKEN_RETURN_MARK,
    "application/json",
]
