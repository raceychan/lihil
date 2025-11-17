from typing import Literal

from lihil import Lihil, Route

root = Route()


UserNames = Literal["alice", "bob", "charlie"]


@root.sub("/user").get
async def get_user(user_name: UserNames | None): ...


app = Lihil(root)


# from fastapi import APIRouter, FastAPI


# root = APIRouter()

# @root.get("/user")
# async def get_user(user_name: str | None):
#     return {"user_name": user_name}


# app = FastAPI()
# app.include_router(root)
