from typing import Annotated, AsyncGenerator

from fastapi import Depends, FastAPI
from pydantic import BaseModel


class User(BaseModel):
    id: int
    name: str
    email: str


class Engine: ...


async def get_engine() -> AsyncGenerator[Engine, None]:
    engine = Engine()
    yield engine


async def pydantic_user(
    user: User, engine: Annotated[Engine, Depends(get_engine)]
) -> User:
    u = User(id=user.id, name=user.name, email=user.email)
    return u


app = FastAPI()
app.add_api_route("/", pydantic_user, methods=["POST"])
