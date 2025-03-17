import tomllib
from pathlib import Path
from typing import Any, Self

from msgspec import convert, field
from starlette.requests import Request

from lihil.errors import AppConfiguringError
from lihil.interface import FlatRecord
from lihil.plugins.bus import EventBus

# class ServerConfig(ConfigBase):
#     host: str = "127.0.0.1"
#     port: int = 8000

#     interface: str = "asgi3"
#     asgi_version: str = "3.0"
#     timeout_keep_alive: int = 5
#     backlog: int = 2048
#     root_path: str = ""


def is_lhl_dep(type_: type):
    "Dependencies that should be injected and managed by lihil"
    return type_ in (Request, EventBus)


class ConfigBase(FlatRecord, forbid_unknown_fields=True): ...


def get_thread_cnt() -> int:
    import os

    default_max = os.cpu_count() or 1
    return default_max


class OASConfig(ConfigBase):
    oas_path: str = "/openapi"
    doc_path: str = "/docs"
    problem_path: str = "/problems"
    title: str = "lihil-OpenAPI"
    version: str = "3.1.0"


class AppConfig(ConfigBase):
    is_prod: bool = False
    version: str = "0.1.0"
    max_thread_workers: int = field(default_factory=get_thread_cnt)
    oas: OASConfig = OASConfig()

    @classmethod
    def from_toml(cls, file_path: Path) -> Self:
        with open(file_path, "rb") as fp:
            toml = tomllib.load(fp)

        try:
            lihil_config: dict[str, Any] = toml["tool"]["lihil"]
        except KeyError:
            raise AppConfiguringError(f"can't find table tool.lihil from {file_path}")

        config = convert(lihil_config, cls)
        return config

    @classmethod
    def from_file(cls, config_file: Path | str | None) -> Self:
        if config_file is None:
            return cls()  # everything default

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
            raise AppConfiguringError(f"Not supported file type {file_ext}")
