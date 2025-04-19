import tomllib
from pathlib import Path
from typing import Sequence

from msgspec import field

from lihil.errors import AppConfiguringError
from lihil.interface import UNSET, Record, StrDict, Unset


def get_thread_cnt() -> int:
    import os

    default_max = os.cpu_count() or 1
    return default_max


class ConfigBase(Record, forbid_unknown_fields=True, frozen=True): ...


class OASConfig(ConfigBase):
    oas_path: str = "/openapi"
    "Route path for openapi json schema"
    doc_path: str = "/docs"
    "Route path for swagger ui"
    title: str = "lihil-OpenAPI"
    "Title of your swagger ui"
    problem_path: str = "/problems"
    "Route path for problem page"
    problem_title: str = "lihil-Problem Page"
    "Title of your problem page"
    version: str = "3.1.0"
    "Swagger UI version"


class ServerConfig(ConfigBase):
    host: str | None = None
    port: int | None = None
    workers: int | None = None
    reload: bool | None = None
    root_path: str | None = None


class SecurityConfig(ConfigBase):
    jwt_secret: str
    jwt_algorithms: Sequence[str]


class AppConfig(ConfigBase):
    is_prod: bool = False
    version: str = "0.1.0"
    max_thread_workers: int = field(default_factory=get_thread_cnt)
    oas: OASConfig = field(default_factory=OASConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    security: Unset[SecurityConfig] = UNSET

    @classmethod
    def _from_toml(cls, file_path: Path) -> StrDict:

        with open(file_path, "rb") as fp:
            toml = tomllib.load(fp)

        try:
            lihil_config: StrDict = toml["tool"]["lihil"]
        except KeyError:
            try:
                lihil_config: StrDict = toml["lihil"]
            except KeyError:
                raise AppConfiguringError(f"can't find table lihil from {file_path}")
        return lihil_config

    # _from_env

    @classmethod
    def from_file(cls, file_path: Path) -> StrDict:
        if not file_path.exists():
            raise AppConfiguringError(f"path {file_path} not exist")

        file_ext = file_path.suffix[1:]
        if file_ext != "toml":
            raise AppConfiguringError(f"Not supported file type {file_ext}")
        return cls._from_toml(file_path)
