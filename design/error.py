"""
# RFC9457
ref: https://www.rfc-editor.org/rfc/rfc9457.html

class ErrorResponse[Exc]:
    status: 422
    # The "status" member is a JSON number indicating the HTTP status code

    type: https://example.net/validation-error
    # human-readable documentation for the problem type 

    title: "You do not have enough credit.",
    #  a short, human-readable summary of the problem type.

    detail: "Your current balance is 30, but that costs 50."
    # a human-readable explanation specific to this occurrence of the problem.


    instance: "/account/12345/msgs/abc",
    # a URI reference that identifies the specific occurrence of the problem.
    # When the "instance" URI is dereferenceable, the problem details object can be fetched from it. It might also return information about the problem occurrence in other formats through use of proactive content negotiation

    def __init__(self, exc: Exc):
        error_base = "api/v1/errors/"

        self.type = error_base + keba_case(exc.__class__.__name__)
        self.title = exc.__class__.__doc__
        self.detail = exc.detail
        self.instance = exc.entity_path + exc.entity_id

class Exc(ty.Protocol):
    __doc__: str
    __status__: int

    detail: str
    entity_id: str
"""

import typing as ty


class ErorrResponse[Exc: Exception]:
    status: int
    type: str
    title: str
    detail: str
    instance: str

    def __init__(self, exc: Exc):
        """
        error_base = "api/v1/errors/"

        self.type = error_base + keba_case(exc.__class__.__name__)
        self.title = exc.__class__.__doc__
        self.detail = exc.detail
        self.instance = exc.entity_path + exc.entity_id

        """


type Result[Ok, Err: Exception] = ty.Annotated[Ok, Err]
"""
Carry normal return and exception  

type CreateUserError = (
    UserNotFoundError
    | InvalidStateError
    | ReplicatedUserError
    | BannedUserError
    | LongNameErrror
    | AnyNewError
)

async def create_user(cmd: CreateUser, user_repo) -> Result[str, CreateUserError]: ...

async def create_user(
    cmd: CreateUser,
    user_repo: UserRepo,
    token_registry: TokenRegistry,
    event_store: EventStore,
) -> Result[str, CreateUserError]:
"""


class EUserNotCreated(Exception): ...


class EDuplicatedUser(Exception): ...


type CreateUserError = EUserNotCreated | EDuplicatedUser


async def create_user() -> Result[int, CreateUserError]:
    return 3
