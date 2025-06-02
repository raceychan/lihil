from copy import deepcopy
from typing import Any, ClassVar, Generic, Literal, Mapping, TypeVar, Union, overload

from ididi import DependentNode
from msgspec import DecodeError
from msgspec import Meta as Constraint
from msgspec import ValidationError, field
from starlette.datastructures import FormData

from lihil.errors import InvalidParamSourceError, NotSupportedError
from lihil.interface import BodyContentType, ParamBase, ParamSource, T, is_provided
from lihil.interface.struct import Base, IBodyDecoder, IDecoder, ITextualDecoder
from lihil.problems import (
    CustomDecodeErrorMessage,
    CustomValidationError,
    InvalidDataType,
    InvalidJsonReceived,
    MissingRequestParam,
    ValidationProblem,
)
from lihil.utils.typing import is_nontextual_sequence
from lihil.vendors import FormData, Headers, QueryParams

D = TypeVar("D", bound=bytes | FormData | str | list[str])


class PluginParam(ParamBase[Any]): ...


class ParamMeta(Base):
    source: Union[ParamSource, None] = None
    alias: Union[str, None] = None
    decoder: IBodyDecoder[Any] | ITextualDecoder[Any] | None = None
    constraint: Constraint | None = None
    extra_meta: dict[str, Any] = field(default_factory=dict[str, Any])


class BodyMeta(ParamMeta):
    source: ParamSource | None = "body"
    decoder: Any = None
    content_type: BodyContentType | None = None


class FormMeta(BodyMeta, kw_only=True):
    max_files: int | float = 1000
    max_fields: int | float = 1000
    max_part_size: int = 1024**2


def Form(
    decoder: Union[Any, None] = None,
    content_type: BodyContentType | None = None,
    max_files: int | float = 1000,
    max_fields: int | float = 1000,
    max_part_size: int = 1024**2,
    extra_meta: Union[dict[str, Any], None] = None,
) -> FormMeta:
    return FormMeta(
        content_type=content_type,
        decoder=decoder,
        max_files=max_files,
        max_fields=max_fields,
        max_part_size=max_part_size,
        extra_meta=extra_meta or {},
    )


def Param(
    source: Union[ParamSource, None] = None,
    *,
    alias: Union[str, None] = None,
    decoder: Union[Any, None] = None,
    gt: Union[int, float, None] = None,
    ge: Union[int, float, None] = None,
    lt: Union[int, float, None] = None,
    le: Union[int, float, None] = None,
    multiple_of: Union[int, float, None] = None,
    pattern: Union[str, None] = None,
    min_length: Union[int, None] = None,
    max_length: Union[int, None] = None,
    tz: Union[bool, None] = None,
    title: Union[str, None] = None,
    description: Union[str, None] = None,
    examples: Union[list[Any], None] = None,
    extra_json_schema: Union[dict[str, Any], None] = None,
    schema_extra: Union[dict[str, Any], None] = None,
    extra_meta: Union[dict[str, Any], None] = None,
) -> ParamMeta:
    param_sources: tuple[str, ...] = ParamSource.__args__
    if source is not None and source not in param_sources:
        raise InvalidParamSourceError(source, param_sources)
    if any(
        x is not None
        for x in (
            gt,
            ge,
            lt,
            le,
            multiple_of,
            pattern,
            min_length,
            max_length,
            tz,
            title,
            description,
            examples,
            extra_json_schema,
            schema_extra,
        )
    ):
        constraint = Constraint(
            gt=gt,
            ge=ge,
            lt=lt,
            le=le,
            multiple_of=multiple_of,
            pattern=pattern,
            min_length=min_length,
            max_length=max_length,
            tz=tz,
            title=title,
            description=description,
            examples=examples,
            extra_json_schema=extra_json_schema,
            extra=schema_extra,
        )
    else:
        constraint = None

    meta = ParamMeta(
        source=source,
        alias=alias,
        decoder=decoder,
        constraint=constraint,
        extra_meta=extra_meta or {},
    )
    return meta


class Decodable(ParamBase[T], Generic[D, T], kw_only=True):
    source: ClassVar[ParamSource]
    decoder: IDecoder[D, T]

    def __post_init__(self):
        super().__post_init__()

    def __repr__(self) -> str:
        name_repr = (
            self.name if self.alias == self.name else f"{self.name!r}, {self.alias!r}"
        )
        return (
            f"{self.__class__.__name__}<{self.source}> ({name_repr}: {self.type_repr})"
        )

    def decode(self, content: D) -> T:
        return self.decoder(content)

    def validate(self, raw: D) -> "ParamResult[T]":
        try:
            value = self.decode(raw)
            return value, None
        except ValidationError as mve:
            error = InvalidDataType(self.source, self.name, str(mve))
        except DecodeError:
            error = InvalidJsonReceived(self.source, self.name)
        except CustomValidationError as cve:  # type: ignore
            error = CustomDecodeErrorMessage(self.source, self.name, cve.detail)
        return None, error


class PathParam(Decodable[str, T], Generic[T], kw_only=True):
    source: ClassVar[ParamSource] = "path"

    def __post_init__(self):
        super().__post_init__()
        if not self.required:
            raise NotSupportedError(
                f"Path param {self} with default value is not supported"
            )

    def extract(self, params: Mapping[str, str]) -> "ParamResult[T]":
        try:
            raw = params[self.alias]
        except KeyError:
            return (None, MissingRequestParam(self.source, self.alias))

        return self.validate(raw)


class QueryParam(Decodable[str | list[str], T], kw_only=True):
    source: ClassVar[ParamSource] = "query"
    decoder: ITextualDecoder[T]
    multivals: bool = False

    def __post_init__(self):
        super().__post_init__()

        self.multivals = is_nontextual_sequence(self.type_)

    def extract(self, queries: QueryParams | Headers) -> "ParamResult[T]":
        alias = self.alias
        is_multivals = self.multivals
        if is_multivals:
            raw = queries.getlist(alias)
        else:
            raw = queries.get(alias)

        if raw is None:
            if is_provided(default := self.default):
                if is_multivals:
                    return (deepcopy(default), None)
                return (default, None)
            else:
                return (None, MissingRequestParam(self.source, alias))
        return self.validate(raw)


class HeaderParam(QueryParam[T]):
    source: ClassVar[ParamSource] = "header"


class CookieParam(HeaderParam[T], kw_only=True):
    alias = "cookie"
    cookie_name: str


B = TypeVar("B", bound=bytes | FormData)


class BodyParam(Decodable[B, T], kw_only=True):
    source: ClassVar[ParamSource] = "body"
    content_type: BodyContentType = "application/json"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}<{self.content_type}>({self.name}: {self.type_repr})"

    def extract(self, body: B) -> "ParamResult[T]":
        if body == b"":
            if is_provided(default := self.default):
                val = default
                return (val, None)
            else:
                error = MissingRequestParam(self.source, self.alias)
                return (None, error)

        return self.validate(body)


class FormParam(BodyParam[FormData, T], kw_only=True):
    content_type: BodyContentType = "multipart/form-data"
    meta: FormMeta

    def extract(self, body: FormData) -> "ParamResult[T]":
        if len(body) == 0:
            if is_provided(default := self.default):
                val = default
                return (val, None)
            else:
                error = MissingRequestParam(self.source, self.alias)
                return (None, error)

        return self.validate(body)


RequestParam = Union[PathParam[T], QueryParam[T], HeaderParam[T], CookieParam[T]]
ParsedParam = (
    RequestParam[T] | BodyParam[bytes, T] | FormParam[T] | DependentNode | PluginParam
)
ParamResult = tuple[T, None] | tuple[None, ValidationProblem]
ParamMap = dict[str, T]


class EndpointParams(Base, kw_only=True):
    params: ParamMap[RequestParam[Any]]
    bodies: ParamMap[BodyParam[Any, Any]]
    nodes: ParamMap[DependentNode]
    plugins: ParamMap[PluginParam]

    @overload
    def get_source(self, source: Literal["header"]) -> ParamMap[HeaderParam[Any]]: ...

    @overload
    def get_source(self, source: Literal["query"]) -> ParamMap[QueryParam[Any]]: ...

    @overload
    def get_source(self, source: Literal["path"]) -> ParamMap[PathParam[Any]]: ...

    def get_source(self, source: ParamSource) -> Mapping[str, RequestParam[Any]]:
        return {n: p for n, p in self.params.items() if p.source == source}

    def get_body(self) -> tuple[str, BodyParam[Any, Any]] | None:
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
