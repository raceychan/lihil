from typing import Any


class LihilError(Exception):
    __slots__ = ()
    ...


class DuplicatedRouteError(LihilError):
    def __init__(self, new_route: Any, current_route: Any):
        msg = f"Duplicated routes [{new_route}, {current_route}]"
        super().__init__(msg)


class InvalidLifeSpanError(LihilError): ...


class StatusConflictError(LihilError):
    def __init__(self, status: int, type_: Any):
        msg = f"{status} conflicts with return type {type_}"
        super().__init__(self, msg)


class InvalidStatusError(LihilError):
    def __init__(self, code: Any) -> None:
        super().__init__(f"Invalid status code {code!r}")


class AppConfiguringError(LihilError): ...


class MiddlewareBuildError(LihilError):
    def __init__(self, factory: Any):
        super().__init__(f"Unable to instantiate middleware from {factory}")


class NotSupportedError(LihilError):
    "A generic error for behaviors we currently do not support"

    def __init__(self, msg: str):
        super().__init__(msg)


class InvalidParamError(LihilError): ...


class InvalidParamPackError(InvalidParamError): ...


class InvalidEndpointError(LihilError): ...


class UnserializableResponseError(LihilError):
    def __init__(self, ret: Any):
        super().__init__(f"Cannot serialize response of type: {type(ret)}")


class MissingDependencyError(LihilError):
    def __init__(self, dep_name: str, instruction: str = "") -> None:
        msg = f"{dep_name} is required but not provided"
        if instruction:
            msg += f", {instruction}."
        super().__init__(msg)


class InvalidParamSourceError(LihilError):
    def __init__(self, source: str, param_sources: tuple[str, ...]):
        msg = f"Invalid source {source}, expected one of {param_sources}"
        super().__init__(msg)


class RouteSetupError(LihilError):
    def __init__(self, route: Any):
        msg = f"Failed to setup route {route}"
        super().__init__(msg)


class LhilWSError(LihilError):
    "all websocket related error"


class SockRejectedError(LhilWSError):
    """Raised when a socket is rejected before accept."""
