import tomllib
from pathlib import Path
from typing import Annotated, Sequence

from msgspec import field
from typing_extensions import Doc

from lihil.errors import AppConfiguringError
from lihil.interface import UNSET, Record, StrDict, Unset


def get_thread_cnt() -> int:
    import os

    default_max = os.cpu_count() or 1
    return default_max


class ConfigBase(Record, forbid_unknown_fields=True, frozen=True): ...


class OASConfig(ConfigBase):
    oas_path: Annotated[str, Doc("Route path for OpenAPI JSON schema")] = "/openapi"
    doc_path: Annotated[str, Doc("Route path for Swagger UI")] = "/docs"
    title: Annotated[str, Doc("Title of your Swagger UI")] = "lihil-OpenAPI"
    problem_path: Annotated[str, Doc("Route path for problem page")] = "/problems"
    problem_title: Annotated[str, Doc("Title of your problem page")] = (
        "lihil-Problem Page"
    )
    version: Annotated[str, Doc("Swagger UI version")] = "3.1.0"


class ServerConfig(ConfigBase):
    host: Annotated[str | None, Doc("Host address to bind to (e.g., '127.0.0.1')")] = (
        None
    )
    port: Annotated[int | None, Doc("Port number to listen on")] = None
    workers: Annotated[int | None, Doc("Number of worker processes")] = None
    reload: Annotated[bool | None, Doc("Enable auto-reloading during development")] = (
        None
    )
    root_path: Annotated[
        str | None, Doc("Root path to mount the app under (if behind a proxy)")
    ] = None


class SecurityConfig(ConfigBase):
    jwt_secret: Annotated[str, Doc("Secret key for encoding and decoding JWTs")]
    jwt_algorithms: Annotated[
        str | Sequence[str], Doc("List of accepted JWT algorithms")
    ]




class AppConfig(ConfigBase):
    is_prod: Annotated[bool, Doc("Whether the current environment is production")] = (
        False
    )
    version: Annotated[str, Doc("Application version")] = "0.1.0"
    max_thread_workers: Annotated[int, Doc("Maximum number of thread workers")] = field(
        default_factory=get_thread_cnt
    )
    oas: Annotated[OASConfig, Doc("OpenAPI and Swagger UI configuration")] = field(
        default_factory=OASConfig
    )
    server: Annotated[ServerConfig, Doc("Server runtime configuration")] = field(
        default_factory=ServerConfig
    )
    security: Annotated[
        Unset[SecurityConfig], Doc("Security-related configuration, e.g., JWT settings")
    ] = UNSET

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
