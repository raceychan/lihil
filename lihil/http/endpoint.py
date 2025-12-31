from concurrent.futures.thread import ThreadPoolExecutor
from inspect import isasyncgen, isgenerator
from typing import Any, Awaitable, Callable, Generic, Literal, Sequence, TypedDict

from ididi import Graph
from ididi.graph import Resolver
from typing_extensions import Unpack

from lihil.errors import UnserializableResponseError
from lihil.interface import (
    HTTP_METHODS,
    MISSING,
    IAsyncFunc,
    IEncoder,
    IReceive,
    IScope,
    ISend,
    P,
    R,
    Record,
    field,
)
from lihil.plugins import IPlugin
from lihil.plugins.auth.oauth import AuthBase
from lihil.problems import (
    DetailBase,
    InvalidFormError,
    InvalidRequestErrors,
    get_solver,
)
from lihil.signature import EndpointSignature, Injector, ParseResult
from lihil.signature.returns import agen_encode_wrapper, syncgen_encode_wrapper
from lihil.utils.threading import async_wrapper
from lihil.vendors import MultiPartException, Request, Response, StreamingResponse


class IEndpointProps(TypedDict, total=False):
    problems: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]]
    "Errors that might be raised from the current `endpoint`. These will be treated as responses and displayed in OpenAPI documentation."
    in_schema: bool
    "Whether to include this endpoint inside openapi docs"
    to_thread: bool
    "Whether this endpoint should be run wihtin a separate thread, only apply to sync function"
    scoped: Literal[True] | None
    "Whether current endpoint should be scoped"
    auth_scheme: AuthBase | None
    "Auth Scheme for access control"
    tags: list[str] | None
    "OAS tag, endpoints with the same tag will be grouped together"
    encoder: IEncoder | None
    "Return Encoder"
    plugins: list[IPlugin]
    "Decorators to decorate the endpoint function"
    deps: list[Any] | None
    "Dependencies that might be used in "
    # responses: dict[int, OASResponse] | None
    # "Custom responses for OpenAPI documentation"


class EndpointProps(Record, kw_only=True):
    problems: list[type[DetailBase[Any]]] = field(
        default_factory=list[type[DetailBase[Any]]]
    )
    to_thread: bool = True
    in_schema: bool = True
    scoped: Literal[True] | None = None
    auth_scheme: AuthBase | None = None
    tags: list[str] | None = None
    encoder: IEncoder | None = None
    plugins: list[IPlugin] = field(default_factory=list[IPlugin])
    deps: list[Any] | None = None
    # responses: dict[int, OASResponse] | None = None

    @classmethod
    def from_unpack(cls, **iconfig: Unpack[IEndpointProps]):
        if problems := iconfig.get("problems"):
            if not isinstance(problems, Sequence):
                problems = [problems]

            iconfig["problems"] = problems
        return cls(**iconfig)  # type: ignore


class HTTPInjector(Injector[R]):
    async def validate_request(self, req: Request, resolver: Resolver):
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
            if val is not MISSING:
                params[name] = val
            else:
                errors.append(error)  # type: ignore

        if errors:
            raise InvalidRequestErrors(detail=errors)

        for name, p in self.state_params:
            ptype = p.type_
            if not isinstance(ptype, type):
                continue
            if issubclass(ptype, Request):
                params[name] = req
            elif issubclass(ptype, Resolver):
                params[name] = resolver

        for name, dep in self.deps:
            params[name] = await resolver.aresolve(dep.dependent, **params)

        for p in self.transitive_params:
            params.pop(p)

        return parsed


class EndpointInfo(Record, Generic[P, R]):
    graph: Graph
    func: IAsyncFunc[P, R]
    sig: EndpointSignature[R]


class Endpoint(Generic[R]):
    def __init__(
        self,
        path: str,
        method: HTTP_METHODS,
        func: Callable[..., R],
        props: EndpointProps,
        workers: ThreadPoolExecutor | None,
    ):
        self._path = path
        self._method: HTTP_METHODS = method
        self._unwrapped_func = func
        self._func = async_wrapper(func, threaded=props.to_thread, workers=workers)
        self._props = props
        self._name: str = func.__name__
        self._is_setup: bool = False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._method}: {self._path!r} {self._func})"

    @property
    def props(self) -> EndpointProps:
        return self._props

    @property
    def path(self) -> str:
        return self._path

    @property
    def name(self) -> str:
        return self._name

    @property
    def sig(self) -> EndpointSignature[R]:
        return self._sig

    @property
    def method(self) -> HTTP_METHODS:
        return self._method

    @property
    def scoped(self) -> bool:
        return self._scoped

    @property
    def encoder(self) -> Callable[[Any], bytes]:
        return self._encoder

    @property
    def unwrapped_func(self) -> Callable[..., R]:
        return self._unwrapped_func

    @property
    def is_setup(self) -> bool:
        return self._is_setup

    def _chainup_plugins(
        self, func: Callable[..., Awaitable[R]], sig: EndpointSignature[R], graph: Graph
    ) -> Callable[..., Awaitable[R]]:
        seen: set[int] = set()
        for decor in self._props.plugins:
            if (decor_id := id(decor)) in seen:
                continue

            ep_info = EndpointInfo(graph, func, sig)
            func = decor(ep_info)
            seen.add(decor_id)
        return func

    def setup(self, sig: EndpointSignature[R], graph: Graph) -> None:
        if self._is_setup:
            raise Exception(f"`setup` is called more than once in {self}")

        self._sig = sig
        self._graph = graph
        self._func = self._chainup_plugins(self._func, self._sig, graph)
        self._injector = HTTPInjector(self._sig)

        self._static = sig.static
        self._status_code = sig.status_code
        self._scoped: bool = sig.scoped or self._props.scoped is True
        self._encoder = self._props.encoder or sig.encoder

        self._media_type = sig.media_type

        self._is_setup = True

    async def make_static_call(
        self, scope: IScope, receive: IReceive, send: ISend
    ) -> R | Response:
        try:
            return await self._func()
        except Exception as exc:
            request = Request(scope, receive, send)
            if solver := get_solver(exc):
                return solver(request, exc)
            raise

    async def make_call(
        self, scope: IScope, receive: IReceive, send: ISend, resolver: Resolver
    ) -> R | ParseResult | Response:
        request = Request(scope, receive, send)
        callbacks = None
        try:
            parsed = await self._injector.validate_request(request, resolver)
            params, callbacks = parsed.params, parsed.callbacks
            return await self._func(**params)
        except Exception as exc:
            if solver := get_solver(exc):
                return solver(request, exc)
            raise
        finally:
            if callbacks:
                for cb in callbacks:
                    await cb()

    def return_to_response(self, raw_return: Any) -> Response:
        if isinstance(raw_return, Response):
            return raw_return

        if isasyncgen(raw_return):
            encode_wrapper = agen_encode_wrapper(raw_return, self._encoder)
            resp = StreamingResponse(
                encode_wrapper,
                media_type="text/event-stream",
                status_code=self._status_code,
            )
        elif isgenerator(raw_return):
            encode_wrapper = syncgen_encode_wrapper(raw_return, self._encoder)
            resp = StreamingResponse(
                encode_wrapper,
                media_type="text/event-stream",
                status_code=self._status_code,
            )
        else:
            try:
                content = self._encoder(raw_return)
            except TypeError as exc:
                raise UnserializableResponseError(raw_return) from exc
            resp = Response(
                content=content,
                media_type=self._media_type,
                status_code=self._status_code,
            )
        return resp

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if self._scoped:
            async with self._graph.ascope() as resolver:
                raw_return = await self.make_call(scope, receive, send, resolver)
                response = self.return_to_response(raw_return)
                return await response(scope, receive, send)
        if self._static:  # when there is no params at all
            raw_return = await self.make_static_call(scope, receive, send)
        else:
            raw_return = await self.make_call(scope, receive, send, self._graph)
        response = self.return_to_response(raw_return)
        await response(scope, receive, send)
