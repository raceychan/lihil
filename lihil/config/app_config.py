from typing import Annotated, Any, Protocol, Sequence

from msgspec import field
from typing_extensions import Doc

from lihil.interface import Record


class IOASConfig(Protocol):
    @property
    def oas_path(self) -> str: ...
    @property
    def doc_path(self) -> str: ...
    @property
    def title(self) -> str: ...
    @property
    def problem_path(self) -> str: ...
    @property
    def problem_title(self) -> str: ...
    @property
    def version(self) -> str: ...


class IServerConfig(Protocol):
    @property
    def host(self) -> str: ...
    @property
    def port(self) -> int: ...
    @property
    def workers(self) -> int: ...
    @property
    def reload(self) -> bool: ...
    def asdict(self) -> dict[str, Any]: ...


class IAppConfig(Protocol):
    @property
    def version(self) -> str: ...
    @property
    def server(self) -> IServerConfig: ...
    @property
    def oas(self) -> IOASConfig: ...


class IJWTConfig(IAppConfig):
    @property
    def jwt_secret(self) -> str: ...
    @property
    def jwt_algorithms(self) -> str | Sequence[str]: ...


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
    host: Annotated[str, Doc("Host address to bind to (e.g., '127.0.0.1')")] = (
        "127.0.0.1"
    )
    port: Annotated[int, Doc("Port number to listen on e.g., 8000")] = 8000
    workers: Annotated[int, Doc("Number of worker processes")] = 1
    reload: Annotated[bool, Doc("Enable auto-reloading during development")] = False
    root_path: Annotated[
        str, Doc("Root path to mount the app under (if behind a proxy)")
    ] = ""


class AppConfig(ConfigBase):
    is_prod: Annotated[bool, Doc("Whether the current environment is production")] = (
        False
    )
    version: Annotated[str, Doc("Application version")] = "0.1.0"
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
