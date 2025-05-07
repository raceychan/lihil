from typing import Annotated, Any, Protocol, Sequence

from msgspec import field
from typing_extensions import Doc

from lihil.interface import Record


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
    port: Annotated[int | None, Doc("Port number to listen on e.g., 8000")] = None
    workers: Annotated[int | None, Doc("Number of worker processes")] = None
    reload: Annotated[bool | None, Doc("Enable auto-reloading during development")] = (
        None
    )
    root_path: Annotated[
        str | None, Doc("Root path to mount the app under (if behind a proxy)")
    ] = None


class IOASConfig(Protocol):
    oas_path: str
    doc_path: str
    title: str
    problem_path: str
    problem_title: str
    version: str


class IServerConfig(Protocol):
    host: str
    port: int
    workers: int
    reload: bool

    def asdict(self) -> dict[str, Any]: ...


class IAppConfig(Protocol):
    max_thread_workers: int
    version: str
    server: IServerConfig
    oas: IOASConfig


class IJWTConfig(IAppConfig):
    jwt_secret: str
    jwt_algorithms: str | Sequence[str]


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


class JWTConfig(AppConfig, kw_only=True):
    jwt_secret: Annotated[str, Doc("Secret key for encoding and decoding JWTs")]
    jwt_algorithms: Annotated[
        str | Sequence[str], Doc("List of accepted JWT algorithms")
    ]
