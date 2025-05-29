from typing import Annotated, Any, Protocol

from msgspec import field
from typing_extensions import Doc

from lihil.interface import Record


class IOASConfig(Protocol):
    @property
    def OAS_PATH(self) -> str: ...
    @property
    def DOC_PATH(self) -> str: ...
    @property
    def TITLE(self) -> str: ...
    @property
    def PROBLEM_PATH(self) -> str: ...
    @property
    def PROBLEM_TITLE(self) -> str: ...
    @property
    def VERSION(self) -> str: ...


class IServerConfig(Protocol):
    @property
    def HOST(self) -> str: ...
    @property
    def PORT(self) -> int: ...
    @property
    def WORKERS(self) -> int: ...
    @property
    def RELOAD(self) -> bool: ...
    @property
    def ROOT_PATH(self) -> str: ...
    def asdict(self) -> dict[str, Any]: ...


class IAppConfig(Protocol):
    @property
    def IS_PROD(self) -> bool: ...
    @property
    def VERSION(self) -> str: ...
    @property
    def server(self) -> IServerConfig: ...
    @property
    def oas(self) -> IOASConfig: ...


class ConfigBase(Record, forbid_unknown_fields=True): ...


class OASConfig(ConfigBase):
    OAS_PATH: Annotated[str, Doc("Route path for OpenAPI JSON schema")] = "/openapi"
    DOC_PATH: Annotated[str, Doc("Route path for Swagger UI")] = "/docs"
    TITLE: Annotated[str, Doc("Title of your Swagger UI")] = "lihil-OpenAPI"
    PROBLEM_PATH: Annotated[str, Doc("Route path for problem page")] = "/problems"
    PROBLEM_TITLE: Annotated[str, Doc("Title of your problem page")] = (
        "lihil-Problem Page"
    )
    VERSION: Annotated[str, Doc("Swagger UI version")] = "3.1.0"


class ServerConfig(ConfigBase):
    HOST: Annotated[str, Doc("Host address to bind to (e.g., '127.0.0.1')")] = (
        "127.0.0.1"
    )
    PORT: Annotated[int, Doc("Port number to listen on e.g., 8000")] = 8000
    WORKERS: Annotated[int, Doc("Number of worker processes")] = 1
    RELOAD: Annotated[bool, Doc("Enable auto-reloading during development")] = False
    ROOT_PATH: Annotated[
        str, Doc("Root path to mount the app under (if behind a proxy)")
    ] = ""


class AppConfig(ConfigBase):
    IS_PROD: Annotated[bool, Doc("Whether the current environment is production")] = (
        False
    )
    VERSION: Annotated[str, Doc("Application version")] = "0.1.0"
    oas: Annotated[OASConfig, Doc("OpenAPI and Swagger UI configuration")] = field(
        default_factory=OASConfig
    )
    server: Annotated[ServerConfig, Doc("Server runtime configuration")] = field(
        default_factory=ServerConfig
    )
