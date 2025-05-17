from typing import Any, Awaitable, Callable, Generic, cast

from ididi import DependentNode, Resolver
from msgspec import Struct, field

from lihil.interface import Base, IEncoder, R, Record
from lihil.plugins.bus import BusTerminal, EventBus
from lihil.problems import InvalidFormError, InvalidRequestErrors, ValidationProblem
from lihil.vendors import (
    FormData,
    Headers,
    HTTPConnection,
    MultiPartException,
    QueryParams,
    Request,
    WebSocket,
    cookie_parser,
)

from .params import (
    BodyParam,
    CookieParam,
    FormMeta,
    HeaderParam,
    ParamMap,
    PathParam,
    QueryParam,
    StateParam,
)
from .returns import EndpointReturn

AnyAwaitble = Callable[..., Awaitable[None]]


class ParseResult(Record):
    params: dict[str, Any]
    errors: list[ValidationProblem]

    callbacks: list[AnyAwaitble] = field(default_factory=list)

    def __getitem__(self, key: str):
        return self.params[key]


class EndpointSignature(Base, Generic[R]):
    route_path: str

    query_params: ParamMap[QueryParam[Any]]
    path_params: ParamMap[PathParam[Any]]
    header_params: ParamMap[HeaderParam[Any] | CookieParam[Any]]
    body_param: tuple[str, BodyParam[bytes | FormData, Struct]] | None

    dependencies: ParamMap[DependentNode]
    transitive_params: set[str]
    """
    Transitive params are parameters required by dependencies, but not directly required by the endpoint function.
    """
    states: ParamMap[StateParam]

    scoped: bool
    form_meta: FormMeta | None

    status_code: int
    return_encoder: IEncoder[R]
    return_params: dict[int, EndpointReturn[R]]

    def _validate_conn(self, conn: HTTPConnection) -> ParseResult:
        verrors: list[Any] = []
        params: dict[str, Any] = {}

        if self.header_params:
            headers = conn.headers

            cookie_params: dict[str, str] | None = None
            for name, param in self.header_params.items():
                if param.alias == "cookie":
                    if cookie_params is None:
                        cookie_params = cookie_parser(headers["cookie"])
                    cookie: str = cookie_params[param.cookie_name]  # type: ignore
                    val, error = param.validate(cookie)
                else:
                    val, error = param.extract(headers)

                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        if self.path_params:
            paths = conn.path_params
            for name, param in self.path_params.items():
                val, error = param.extract(paths)
                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        if self.query_params:
            queries = conn.query_params
            for name, param in self.query_params.items():
                val, error = param.extract(queries)
                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        parsed_result = ParseResult(params, verrors)
        return parsed_result

    async def validate_websocket(
        self, ws: WebSocket, resolver: Resolver, busterm: BusTerminal
    ):
        parsed_result = self._validate_conn(ws)

        if errors := parsed_result.errors:
            raise InvalidRequestErrors(detail=errors)

        params = parsed_result.params
        for name, p in self.states.items():
            ptype = cast(type, p.type_)
            if issubclass(ptype, WebSocket):
                params[name] = ws
            elif issubclass(ptype, EventBus):
                bus = busterm.create_event_bus(resolver)
                params[name] = bus
            elif issubclass(ptype, Resolver):
                params[name] = resolver
            else:  # AppState
                raise TypeError(f"Unsupported type {ptype} for parameter {name}")

        for name, dep in self.dependencies.items():
            params[name] = await resolver.aresolve(dep.dependent, **params)

        return parsed_result

    async def validate_request(
        self, req: Request, resolver: Resolver, busterm: BusTerminal
    ):
        parsed = self._validate_conn(req)
        params, errors = parsed.params, parsed.errors

        if self.body_param:
            name, param = self.body_param

            if form_meta := self.form_meta:
                try:
                    body = await req.form(
                        max_files=form_meta.max_files,
                        max_fields=form_meta.max_fields,
                        max_part_size=form_meta.max_part_size,
                    )
                except MultiPartException:
                    body = b""
                    errors.append(InvalidFormError("body", name))
                else:
                    parsed.callbacks.append(body.close)
            else:
                body = await req.body()

            val, error = param.extract(body)
            if val:
                params[name] = val
            else:
                errors.append(error)

        if errors:
            raise InvalidRequestErrors(detail=errors)

        for name, p in self.states.items():
            ptype = cast(type, p.type_)
            if issubclass(ptype, Request):
                params[name] = req
            elif issubclass(ptype, EventBus):
                bus = busterm.create_event_bus(resolver)
                params[name] = bus
            elif issubclass(ptype, Resolver):
                params[name] = resolver
            else:
                raise TypeError(f"Unsupported state type {ptype} for {name} in {self}")

        for name, dep in self.dependencies.items():
            params[name] = await resolver.aresolve(dep.dependent, **params)

        for p in self.transitive_params:
            params.pop(p)

        return parsed

    @property
    def static(self) -> bool:
        return not any(
            (
                self.path_params,
                self.query_params,
                self.header_params,
                self.body_param,
                self.dependencies,
                self.states,
            )
        )

    @property
    def media_type(self) -> str:
        default = "application/json"
        first_return = next(iter(self.return_params.values()))
        return first_return.content_type or default
