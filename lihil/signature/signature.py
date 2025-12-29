from typing import Any, Awaitable, Callable, Generic

from ididi import DependentNode
from msgspec import Struct

from lihil.interface import MISSING, Base, R, Record
from lihil.problems import ValidationProblem
from lihil.vendors import (
    FormData,
    HTTPConnection,
    cookie_parser,
)

from .params import (
    BodyParam,
    CookieParam,
    FormMeta,
    HeaderParam,
    ParamMap,
    PathParam,
    PluginParam,
    QueryParam,
)
from .returns import EndpointReturn

AnyAwaitble = Callable[..., Awaitable[None]]


class ParseResult(Record):
    params: dict[str, Any]
    errors: list[ValidationProblem]

    callbacks: list[AnyAwaitble]


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
    plugins: ParamMap[PluginParam]

    scoped: bool
    form_meta: FormMeta | None

    return_params: dict[int, EndpointReturn[R]]

    @property
    def default_return(self) -> EndpointReturn[R]:
        return next(iter(self.return_params.values()))

    @property
    def status_code(self) -> int:
        return self.default_return.status

    @property
    def encoder(self) -> Callable[[Any], bytes]:
        return self.default_return.encoder

    @property
    def static(self) -> bool:
        return not any(
            (
                self.path_params,
                self.query_params,
                self.header_params,
                self.body_param,
                self.dependencies,
                self.plugins,
            )
        )

    @property
    def media_type(self) -> str:
        return self.default_return.content_type or "application/json"


class Injector(Generic[R]):
    def __init__(self, sig: EndpointSignature[R]):
        self._sig = sig
        self.header_params = self._sig.header_params.items()
        self.path_params = self._sig.path_params.items()
        self.query_params = self._sig.query_params.items()
        self.body_param = self._sig.body_param
        self.form_meta = self._sig.form_meta
        self.state_params = self._sig.plugins.items()
        self.deps = self._sig.dependencies.items()
        self.transitive_params: tuple[str, ...] = tuple(self._sig.transitive_params)

    def _validate_conn(self, conn: HTTPConnection) -> ParseResult:
        verrors: list[Any] = []
        params: dict[str, Any] = {}

        if self.header_params:
            headers = conn.headers

            cookie_params: dict[str, str] | None = None
            for name, param in self.header_params:
                if param.alias == "cookie":
                    if cookie_params is None:
                        cookie_params = cookie_parser(headers["cookie"])
                    cookie: str = cookie_params[param.cookie_name]  # type: ignore
                    val, error = param.validate(cookie)
                else:
                    val, error = param.extract(headers)

                if val is not MISSING:
                    params[name] = val
                else:
                    verrors.append(error)

        if self.path_params:
            paths = conn.path_params
            for name, param in self.path_params:
                val, error = param.extract(paths)
                if val is not MISSING:
                    params[name] = val
                else:
                    verrors.append(error)

        if self.query_params:
            queries = conn.query_params
            for name, param in self.query_params:
                val, error = param.extract(queries)
                if val is not MISSING:
                    params[name] = val
                else:
                    verrors.append(error)

        parsed_result = ParseResult(params, verrors, [])
        return parsed_result
