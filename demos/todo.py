from pydantic import BaseModel

from lihil import Lihil, Route
from lihil.config import lhl_read_config
from lihil.plugins.auth.supabase import SupabaseConfig, signin_route_factory


async def lifespan(app: Lihil):
    app.config = lhl_read_config(
        ".env", config_type=SupabaseConfig
    )  # read config from .env file as convert it to `ProjectConfig` object.
    app.include_routes(signin_route_factory(route_path="/login"))
    yield


class Profile(BaseModel):
    name: str
    age: int


root = Route()


@root.post
async def create_profile(p: Profile): ...


lhl = Lihil(root, lifespan=lifespan)

if __name__ == "__main__":
    lhl.run(__file__)
