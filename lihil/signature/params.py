from typing import Any, ClassVar, Literal, Mapping, overload

from ididi import DependentNode, INode, NodeConfig
from msgspec import DecodeError
from msgspec import Meta as ParamConstraint
from msgspec import ValidationError, field
from starlette.datastructures import FormData

from lihil.errors import NotSupportedError
from lihil.interface import (
    BodyContentType,
    Maybe,
    ParamBase,
    ParamLocation,
    is_provided,
)
from lihil.interface.marks import ParamMarkType
from lihil.interface.struct import Base, IDecoder
from lihil.problems import (
    CustomDecodeErrorMessage,
    CustomValidationError,
    InvalidDataType,
    InvalidJsonReceived,
    MissingRequestParam,
    ValidationProblem,
)
from lihil.utils.typing import is_mapping_type, is_nontextual_sequence
from lihil.vendors import FormData, Headers, QueryParams

type RequestParam[T] = PathParam[T] | QueryParam[T] | HeaderParam[T] | CookieParam[T]
type ParsedParam[T] = RequestParam[T] | BodyParam[T] | DependentNode | StateParam
type ParamResult[T] = tuple[T, None] | tuple[None, ValidationProblem]

type ParamMap[T] = dict[str, T]


class StateParam(ParamBase[Any]): ...


class Decodable[D, T](ParamBase[T], kw_only=True):
    location: ClassVar[ParamLocation]
    decoder: IDecoder[Any, T] = None  # type: ignore

    def __post_init__(self):
        super().__post_init__()

    def __repr__(self) -> str:
        name_repr = (
            self.name if self.alias == self.name else f"{self.name!r}, {self.alias!r}"
        )
        return f"{self.__class__.__name__}<{self.location}> ({name_repr}: {self.type_repr})"

    def decode(self, content: D) -> T:
        """
        for decoder in self.decoders:
            contennt = decoder(content)
        """
        return self.decoder(content)

    def validate(self, raw: D) -> ParamResult[T]:
        try:
            value = self.decode(raw)
            return value, None
        except ValidationError as mve:
            error = InvalidDataType(self.location, self.name, str(mve))
        except DecodeError:
            error = InvalidJsonReceived(self.location, self.name)
        except CustomValidationError as cve:  # type: ignore
            error = CustomDecodeErrorMessage(self.location, self.name, cve.detail)
        return None, error


class PathParam[T](Decodable[str | list[str], T], kw_only=True):
    location: ClassVar[ParamLocation] = "path"

    def __post_init__(self):
        super().__post_init__()
        if not self.required:
            raise NotSupportedError(
                f"Path param {self} with default value is not supported"
            )

    def extract(self, params: dict[str, str]) -> ParamResult[T]:
        try:
            raw = params[self.alias]
        except KeyError:
            return (None, MissingRequestParam(self.location, self.alias))

        return self.validate(raw)


class QueryParam[T](Decodable[str | list[str], T]):
    location: ClassVar[ParamLocation] = "query"
    decoder: IDecoder[str | list[str], T] = None  # type: ignore
    multivals: bool = False

    def __post_init__(self):
        super().__post_init__()

        if is_mapping_type(self.type_):
            raise NotSupportedError(
                f"query param should not be declared as mapping type, or a union that contains mapping type, received: {self.type_}"
            )

        self.multivals = is_nontextual_sequence(self.type_)

    def extract(self, queries: QueryParams | Headers) -> ParamResult[T]:
        alias = self.alias
        if self.multivals:
            raw = queries.getlist(alias)
        else:
            raw = queries.get(alias)

        if raw is None:
            if is_provided(default := self.default):
                return (default, None)
            else:
                return (None, MissingRequestParam(self.location, alias))
        return self.validate(raw)


class HeaderParam[T](QueryParam[T]):
    location: ClassVar[ParamLocation] = "header"


class CookieParam[T](HeaderParam[T], kw_only=True):
    alias = "cookie"
    cookie_name: str


class BodyParam[T](Decodable[bytes | FormData, T], kw_only=True):
    location: ClassVar[ParamLocation] = "body"
    content_type: BodyContentType = "application/json"

    def __repr__(self) -> str:
        return f"BodyParam<{self.content_type}>({self.name}: {self.type_repr})"

    def extract(self, body: bytes | FormData) -> ParamResult[T]:
        if body == b"" or (isinstance(body, FormData) and len(body) == 0):
            if is_provided(default := self.default):
                val = default
                return (val, None)
            else:
                error = MissingRequestParam(self.location, self.alias)
                return (None, error)

        return self.validate(body)


class ParamMetasBase(Base):
    metas: list[Any]


class RequestParamMeta(ParamMetasBase):
    mark_type: ParamMarkType | None = None
    custom_decoder: IDecoder[Any, Any] | None = None
    constraint: ParamConstraint | None = None


class NodeParamMeta(ParamMetasBase, kw_only=True):
    factory: Maybe[INode[..., Any]]
    node_config: NodeConfig


class EndpointParams(Base, kw_only=True):
    params: ParamMap[RequestParam[Any]] = field(default_factory=dict)
    bodies: ParamMap[BodyParam[Any]] = field(default_factory=dict)
    nodes: ParamMap[DependentNode] = field(default_factory=dict)
    states: ParamMap[StateParam] = field(default_factory=dict)

    @overload
    def get_location(
        self, location: Literal["header"]
    ) -> ParamMap[HeaderParam[Any]]: ...

    @overload
    def get_location(self, location: Literal["query"]) -> ParamMap[QueryParam[Any]]: ...

    @overload
    def get_location(self, location: Literal["path"]) -> ParamMap[PathParam[Any]]: ...

    def get_location(self, location: ParamLocation) -> Mapping[str, RequestParam[Any]]:
        return {n: p for n, p in self.params.items() if p.location == location}

    def get_body(self) -> tuple[str, BodyParam[Any]] | None:
        if not self.bodies:
            body_param = None
        elif len(self.bodies) == 1:
            body_param = next(iter(self.bodies.items()))
        else:
            # use defstruct to dynamically define a type
            raise NotSupportedError(
                "Endpoint with multiple body params is not supported"
            )
        return body_param
