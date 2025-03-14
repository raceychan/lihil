from contextlib import asynccontextmanager

from starlette.responses import Response

from lihil import (
    HTTPException,
    Json,
    Lihil,
    Payload,
    Resp,
    Route,
    Stream,
    Text,
    run,
    status,
)
from lihil.lihil import AppState


class User(Payload, kw_only=True, tag=True):
    id: int
    name: str
    email: str


class Order(Payload, tag=True):
    order_id: str
    price: float


rusers = Route("users")


class MyState(AppState): ...


@asynccontextmanager
async def lifespan(app: Lihil[MyState]):
    yield MyState()


class UserNotFoundError(HTTPException[str]):
    "Unable to find user with given user_id"

    ...


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


rprofile = Route("profile")


@rprofile.post
async def profile(user: User) -> User:
    return User(id=user.id, name=user.name, email=user.email)


rstream = Route("stream")


@rstream.get
async def stream() -> Stream:
    const = ["hello", "world"]
    for c in const:
        yield c


lhl = Lihil(lifespan=lifespan)


lhl.include_routes(rusers, rprofile, rstream)


@lhl.get
async def ping():
    return Response(b"pong")


if __name__ == "__main__":
    run(lhl)
