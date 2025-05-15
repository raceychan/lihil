from typing import Any, Awaitable, Callable, Generic

from ididi import DependentNode
from msgspec import Struct, field

from lihil.interface import Base, IEncoder, R, Record
from lihil.problems import InvalidFormError, ValidationProblem
from lihil.vendors import (
    FormData,
    Headers,
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


class ParseResult(Record):
    params: dict[str, Any]
    errors: list[ValidationProblem]

    callbacks: list[Callable[..., Awaitable[None]]] = field(default_factory=list)

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

    def prepare_params(
        self,
        req_path: dict[str, str] | None = None,
        req_query: QueryParams | None = None,
        req_header: Headers | None = None,
    ) -> ParseResult:
        verrors: list[Any] = []
        params: dict[str, Any] = {}

        if req_header:
            raw_cookies: str | None = None
            cookie_params: dict[str, str] | None = None
            for name, param in self.header_params.items():
                if param.alias == "cookie":
                    cookie: CookieParam[Any] = param  # type: ignore

                    if raw_cookies is None:
                        raw_cookie = req_header["cookie"]
                    if cookie_params is None:
                        cookie_params = cookie_parser(raw_cookie)

                    raw_cookie: str = cookie_params[cookie.cookie_name]
                    val, error = param.validate(raw_cookie)
                else:
                    val, error = param.extract(req_header)

                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        if req_path is not None:
            for name, param in self.path_params.items():
                val, error = param.extract(req_path)
                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        if req_query is not None:
            for name, param in self.query_params.items():
                val, error = param.extract(req_query)
                if val:
                    params[name] = val
                else:
                    verrors.append(error)

        parsed_result = ParseResult(params, verrors)
        return parsed_result

    async def prepare_body(self, request: Request, parsed: ParseResult) -> ParseResult:
        assert self.body_param
        name, param = self.body_param

        if form_meta := self.form_meta:
            try:
                body = await request.form(
                    max_files=form_meta.max_files,
                    max_fields=form_meta.max_fields,
                    max_part_size=form_meta.max_part_size,
                )
            except MultiPartException:
                parsed.errors.append(InvalidFormError("body", name))
                return parsed
            else:
                parsed.callbacks.append(body.close)
        else:
            body = await request.body()

        val, error = param.extract(body)
        if val:
            parsed.params[name] = val
        else:
            parsed.errors.append(error)
        return parsed

    def parse_query(self, req: Request | WebSocket) -> ParseResult:
        req_path = req.path_params if self.path_params else None
        req_query = req.query_params if self.query_params else None
        req_header = req.headers if self.header_params else None
        params = self.prepare_params(req_path, req_query, req_header)
        return params

    async def parse_command(self, req: Request) -> ParseResult:
        req_path = req.path_params if self.path_params else None
        req_query = req.query_params if self.query_params else None
        req_header = req.headers if self.header_params else None
        parsed = self.prepare_params(req_path, req_query, req_header)
        return await self.prepare_body(req, parsed)

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
        return next(iter(self.return_params.values())).content_type or default
