from typing import Annotated

import uvicorn
from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel


class User(BaseModel):
    id: int
    name: str
    email: str


rprofile = APIRouter()


async def lifespan(app):
    print(1)
    yield
    print(2)


class Engine: ...


async def get_engine() -> Engine:
    return Engine()


@rprofile.post("/profile/{pid}")
async def profile(
    pid: str, q: int, user: User, engine: Annotated[Engine, Depends(get_engine)]
) -> User:

    return User(id=user.id, name=user.name, email=user.email)


lhl = FastAPI(lifespan=lifespan)
lhl.include_router(rprofile)


@lhl.get("/")
async def ping():
    return "pong"


if __name__ == "__main__":
    uvicorn.run(lhl, access_log=None, log_level="warning")
