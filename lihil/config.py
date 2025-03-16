import tomllib

# from io import BufferedReader
from pathlib import Path
from typing import Any, Self

from msgspec import convert
from starlette.requests import Request

from lihil.errors import AppConfiguringError
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


class ConfigBase(FlatRecord, forbid_unknown_fields=True): ...


# class ServerConfig(ConfigBase):
#     host: str = "127.0.0.1"
#     port: int = 8000

#     interface: str = "asgi3"
#     asgi_version: str = "3.0"
#     timeout_keep_alive: int = 5
#     backlog: int = 2048
#     root_path: str = ""


class OASConfig(ConfigBase):
    oas_path: str = "/openapi"
    doc_path: str = "/docs"
    problem_path: str = "/problems"
    title: str = "lihil-OpenAPI"
    version: str = "3.1.0"


class AppConfig(ConfigBase):
    is_prod: bool = False
    version: str = "0.1.0"
    oas: OASConfig = OASConfig()

    @classmethod
    def from_toml(cls, file_path: Path):
        with open(file_path, "rb") as fp:
            toml = tomllib.load(fp)

        lihil_config: dict[str, Any] = toml["tool"]["lihil"]
        return convert(lihil_config, cls)

    @classmethod
    def from_file(cls, config_file: Path | str | None) -> Self:
        if config_file:
            if isinstance(config_file, str):
                file_path = Path(config_file)
            else:
                file_path = config_file

            if not file_path.exists():
                raise AppConfiguringError(f"path {file_path} not exist")

            file_ext = file_path.suffix[1:]

            if file_ext == "toml":
                return cls.from_toml(file_path)
            else:
                raise AppConfiguringError(f"Not supported file type {file_path}")
        else:
            return cls()  # default
