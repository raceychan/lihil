from contextlib import asynccontextmanager

from lihil import (
    Empty,
    HTTPException,
    Json,
    Lihil,
    Payload,
    Resp,
    Route,
    Stream,
    Text,
    status,
)


class Unhappiness(Payload):
    scale: int
    is_mad: bool


class UserNotHappyError(HTTPException[Unhappiness]):
    "user is not happy with what you are doing"


class VioletsAreBlue(HTTPException[str]):
    "how about you?"

    __status__ = 418


class UserNotFoundError(HTTPException[str]):
    "Unable to find user with given user_id"

    __status__ = 404

    ...


class User(Payload, kw_only=True, tag=True):
    id: int
    name: str
    email: str


class Order(Payload, tag=True):
    order_id: str
    price: float


rusers = Route("/users")


class MyState(Payload): ...


@asynccontextmanager
async def lifespan(app: Lihil[None]):
    yield dict[str, str]()


@rusers.post
async def create_user(
    user: User, q: int, r: str
) -> Resp[Json[User | Order], status.OK]:
    return User(id=user.id, name=user.name, email=user.email)


rsubu = rusers.sub("{user_id}")


@rsubu.get
async def get_user(user_id: str | int) -> Resp[Text, status.OK]:
    if user_id != "5":
        raise UserNotFoundError("You can't see me!")

    return "aloha"


rprofile = Route("profile/{pid}")


class Engine: ...


def get_engine() -> Engine:
    return Engine()


rprofile.factory(get_engine)


@rprofile.post
async def profile(
    pid: str, q: int, user: User, engine: Engine
) -> Resp[User, status.OK] | Resp[Order, status.CREATED]:
    return User(id=user.id, name=user.name, email=user.email)


rstream = Route("stream")


@rstream.get
async def stream() -> Stream[str]:
    const = ["hello", "world"]
    for c in const:
        yield c


rempty = Route("empty")


@rempty.post
async def empty_resp() -> Empty: ...


root = Route("/")


@root.get
async def roses_are_red():
    raise VioletsAreBlue("I am a pythonista")


lhl = Lihil(routes=[root, rusers, rprofile, rstream, rempty], lifespan=lifespan)
lhl.static("/ping", "pong")


# if __name__ == "__main__":
#     lhl.run(__file__)
