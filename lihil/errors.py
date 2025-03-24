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
        super().__init__(f"Invalid status code {code}")

class AppConfiguringError(LihilError): ...
