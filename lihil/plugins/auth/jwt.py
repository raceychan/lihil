from time import time
from typing import Annotated, Any, ClassVar, Required, TypedDict, dataclass_transform
from uuid import uuid4

from jwt import PyJWT
from jwt.api_jws import PyJWS
from msgspec.json import encode

from lihil.interface import UNSET, Base, CustomEncoder, Payload, Unset, field
from lihil.interface.marks import JW_TOKEN_RETURN_MARK, resp_mark

# class JWTOptions(TypedDict):
#     verify_signature: bool
#     verify_exp: bool
#     verify_nbf: bool
#     verify_iat: bool
#     verify_aud: bool
#     verify_iss: bool
#     verify_sub: bool
#     verify_jti: bool
#     require: list[Any]


def jwt_timeclaim():
    return int(time())


def uuid_factory() -> str:
    return str(uuid4())


class JWTClaim(TypedDict, total=False):
    """
    exp_in: expire in x seconds

    """

    exp_in: Required[int]
    iss: str
    aud: str


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

    __jwt_claims__: ClassVar[JWTClaim] = {"exp_in": -1}

    exp: Unset[int] = UNSET
    nbf: Unset[int] = UNSET
    iat: Unset[int] = UNSET

    jti: str = field(default_factory=uuid_factory)

    def __post_init__(self):
        exp_in = self.__jwt_claims__["exp_in"]

        if exp_in <= 0:
            raise Exception("Invalid exp in")

        now_ = jwt_timeclaim()
        self.exp = now_ + exp_in
        self.nbf = self.iat = now_


"""

@users.get
async def get_user(
    name: str, token: Annotated[str, OAuth2PasswordPlugin(token_url="token")]
) -> JWToken[UserProfile]:
    ...
"""




type JWToken[T] = Annotated[T, JW_TOKEN_RETURN_MARK, "text/plain"]
