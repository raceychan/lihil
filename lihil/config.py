import tomllib
from typing import Any

from msgspec import convert
from starlette.requests import Request

from lihil.interface import FlatRecord
from lihil.plugins.bus import EventBus

"""
[tool.lihil.server]
timeout_keep_alive: int = 5
backlog: int = 2048
interface: str = "asgi3"
asgi_version: str = "3.0"
root_path: str = ""

[tool.lihil.schema]

[tool.lihil.api]
host: str = "127.0.0.1"
port: int = 8000
version: str = "1"
"""


def is_lhl_dep(type_: type):
    "Dependencies that should be injected and managed by lihil"
    return type_ in (Request, EventBus)


class OASConfig(FlatRecord):
    oas_path: str = "/openapi"
    doc_path: str = "/docs"
    problem_path: str = "/problems"
    title: str = "lihil-OpenAPI"
    version: str = "3.1.0"


class AppConfig(FlatRecord):
    version: str = "0.1.0"
    oas: OASConfig = OASConfig()


class ServerConfig(FlatRecord):
    host: str = "127.0.0.1"
    port: int = 8000

    interface: str = "asgi3"
    asgi_version: str = "3.0"
    timeout_keep_alive: int = 5
    backlog: int = 2048
    root_path: str = ""


class Config(FlatRecord):
    # is_prod: bool
    server: ServerConfig

    # server: "Config | None" = None

    @classmethod
    def from_file(cls, filepath: str):
        """
        from pyproject.toml, settings.toml or .env?
        """

        if filepath.endswith("toml"):
            return cls.from_toml(filepath)
        raise NotImplementedError

    @classmethod
    def from_toml(cls, file: str):
        with open(file, "rb") as fp:
            content = tomllib.load(fp)

        lihil_config: dict[str, Any] = content["tool"]["lihil"]
        return convert(lihil_config, cls)


# = "pyproject.toml"
def read_config(config_file: str) -> Config | None:
    # TODO: read order cli -> env -> pyproject.toml
    return Config.from_file(config_file)
