from typing import Annotated

import uvicorn
from fastapi import APIRouter, Depends, FastAPI
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class User(BaseModel):
    id: int
    name: str
    email: str


class Order(BaseModel):
    order_id: str


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
    pid: str,
    q: int,
    user: User,
    engine: Annotated[Engine, Depends(get_engine)],
) -> User | Order:
    return User(id=user.id, name=user.name, email=user.email)


app = FastAPI(lifespan=lifespan)
app.include_router(rprofile)


def sencond_q(q: str):
    return q


def require_q(q: str):
    return q


@app.get("/aloha")
async def only_in_dep(
    name: Annotated[str, Depends(require_q)], n2: Annotated[str, Depends(sencond_q)]
):
    print(f"got {name=}, {n2=}")


# @app.get("/")
# async def ping():
#     return "pong"


# @app.get("/items/")
# async def read_items(token: Annotated[str, Depends(oauth2_scheme)]):
#     return {"token": token}


if __name__ == "__main__":
    uvicorn.run(app, access_log=None, log_level="warning")
