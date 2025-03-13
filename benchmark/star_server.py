from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

from .share import endpoint


async def msgspec_user(r: Request) -> Response:
    data = await r.body()
    res = endpoint(data)
    return Response(content=res)


app = Starlette()
app.add_route("/", msgspec_user, methods=["POST"])
