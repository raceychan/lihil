from time import time
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

from lihil import status
from lihil.errors import NotSupportedError
from lihil.interface import MISSING, UNSET, Base, Unset, field, is_provided
from lihil.interface.marks import HEADER_REQUEST_MARK, JW_TOKEN_RETURN_MARK
from lihil.problems import HTTPException
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


class JWTOptions(TypedDict):
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
        exp_in = self.__jwt_claims__["expires_in"]

        if is_provided(aud := self.__jwt_claims__.get("aud", MISSING)):
            self.aud = aud

        if is_provided(iss := self.__jwt_claims__.get("iss", MISSING)):
            self.iss = iss

        if exp_in <= 0:
            raise NotSupportedError("Invalid exp in")

        now_ = jwt_timeclaim()
        self.exp = now_ + exp_in
        self.nbf = self.iat = now_


# from starlette.responses import Response


# class OAuth2Token(Base):
#     access_token: str
#     expires_in: int
#     refresh_token: Unset[str] = UNSET
#     scope: Unset[str] = UNSET
#     token_type: Literal["Bearer"] = "Bearer"


# class TokenResponse(Response): ...


class InvalidAuthError(HTTPException[str]):

    def __ini__(self, detail: str = "Invalid Authorization-header"):
        super().__init__(
            detail=detail,
            problem_status=status.UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
        )


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
        algorithms: Sequence[str],
        options: JWTOptions | None = None,
        payload_type: type[T],
    ):

        if not isinstance(payload_type, type) or not issubclass(
            payload_type, (JWTPayload, str)
        ):
            raise TypeError("Must be str or subclass of JWTPayload")

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
            token_resp = {
                "access_token": jwt,
                "token_type": "Bearer",
                "expires_in": expires,
            }
            resp = encode_json(token_resp)
            return resp

        return encoder

    def jwt_decoder_factory[T](
        *,
        secret: str,
        algorithms: Sequence[str],
        options: JWTOptions | None = None,
        payload_type: type[T],
    ):

        jwt = PyJWT()

        def decoder(content: str) -> T:
            # TODO: raise HTTPException directly

            try:
                scheme, _, token = content.partition(" ")
                if scheme != "Bearer":
                    raise InvalidAuthError(f"Invalid authorization scheme {scheme}")
                decoded: dict[str, Any] = jwt.decode(
                    token, key=secret, algorithms=algorithms, options=options
                )
                return convert(decoded, payload_type)
            except InvalidTokenError as de:
                raise InvalidAuthError()

        return decoder


type JWToken[T: JWTPayload | str | bytes] = Annotated[
    T,
    Literal["Authorization"],
    HEADER_REQUEST_MARK,
    JW_TOKEN_RETURN_MARK,
    "application/json",
]
