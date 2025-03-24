from typing import Any, Literal


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
        super().__init__(f"Invalid status code {code}")


class AppConfiguringError(LihilError): ...


class MiddlewareBuildError(LihilError):
    def __init__(self, factory: Any):
        super().__init__(f"Unable to instantate middleware from {factory}")


class InvalidParamTypeError(LihilError):
    def __init__(self, annt: Any):
        msg = f"Unexpected param `{annt}` received, if you believe this is a bug, report an issue at https://github.com/raceychan/lihil/issues"

        if annt is Literal[None]:
            super().__init__("use `Empty` instead")
        else:
            super().__init__(msg)


class NotSupportedError(LihilError):
    def __init__(self, msg: str):
        super().__init__(msg)
