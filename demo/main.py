from supabase import AsyncClient, create_async_client

from lihil import AppConfig, Lihil
from lihil.config import lhl_get_config, lhl_read_config


class MyConfig(AppConfig, kw_only=True):
    supabase_url: str
    supabase_key: str


async def ls(app: Lihil[None]):
    config = lhl_get_config(MyConfig)
    supabase = create_async_client(
        supabase_url=config.supabase_url, supabase_key=config.supabase_key
    )
    app.graph.register_singleton(supabase, AsyncClient)
    yield


def app_factory():
    config = lhl_read_config("demo/settings.toml", "demo/.env", config_type=MyConfig)
    lhl = Lihil(lifespan=ls, app_config=config)
    return lhl
