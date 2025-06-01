from supabase import AsyncClient

from lihil import Lihil
from lihil.config import AppConfig, lhl_get_config, lhl_read_config
from lihil.plugins.auth.supabase import signin_route_factory


class ProjectConfig(AppConfig, kw_only=True):
    SUPABASE_URL: str
    SUPABASE_API_KEY: str


def supabase_factory() -> AsyncClient:
    config = lhl_get_config(config_type=ProjectConfig)
    return AsyncClient(
        supabase_url=config.SUPABASE_URL, supabase_key=config.SUPABASE_API_KEY
    )


async def lifespan(app: Lihil):
    app.config = lhl_read_config(
        ".env", config_type=ProjectConfig
    )  # read config from .env file as convert it to `ProjectConfig` object.
    app.graph.analyze(supabase_factory)
    # register an example factory function for supabase.AsyncClient
    app.include_routes(signin_route_factory(route_path="/login"))
    yield


lhl = Lihil(lifespan=lifespan)

if __name__ == "__main__":
    lhl.run(__file__)
