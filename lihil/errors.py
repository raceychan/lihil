class LihilError(Exception):
    __slots__ = ()
    ...


class DuplicatedRouteError(LihilError):
    def __init__(self, new_route, current_route):
        msg = f"Duplicated routes [{new_route}, {current_route}]"
        super().__init__(msg)


class InvalidLifeSpanError(LihilError):
    ...