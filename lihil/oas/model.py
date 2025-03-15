from enum import Enum
from typing import (
    Annotated,
    Any,
    Optional,
    Sequence,
    TypedDict,
    Union,
    dataclass_transform,
)

from msgspec import Meta, Struct, field
from msgspec.structs import replace as struct_replace

from lihil.problems import DetailBase

# from typing_extensions import deprecated as typing_deprecated

# class SecuritySchemeType(Enum):
#     apiKey = "apiKey"
#     http = "http"
#     oauth2 = "oauth2"
#     openIdConnect = "openIdConnect"


# class SecurityBase(BaseStruct, kw_only=True):
#     type_: SecuritySchemeType = field(name="type")
#     description: Optional[str] = None


# class APIKeyIn(Enum):
#     query = "query"
#     header = "header"
#     cookie = "cookie"


# class APIKey(SecurityBase):
#     type_: SecuritySchemeType = field(default=SecuritySchemeType.apiKey, name="type")
#     in_: APIKeyIn = field(name="in")
#     name: str


# class HTTPBase(SecurityBase):
#     type_: SecuritySchemeType = field(default=SecuritySchemeType.http, name="type")
#     scheme: str


# class HTTPBearer(HTTPBase):
#     scheme: Literal["bearer"] = "bearer"
#     bearerFormat: Optional[str] = None


# class OAuthFlow(BaseStruct, kw_only=True):
#     refreshUrl: Optional[str] = None
#     scopes: dict[str, str] = {}


# class OAuthFlowImplicit(OAuthFlow):
#     authorizationUrl: str


# class OAuthFlowPassword(OAuthFlow):
#     tokenUrl: str


# class OAuthFlowClientCredentials(OAuthFlow):
#     tokenUrl: str


# class OAuthFlowAuthorizationCode(OAuthFlow):
#     authorizationUrl: str
#     tokenUrl: str


# class OAuthFlows(BaseStruct, kw_only=True):
#     implicit: Optional[OAuthFlowImplicit] = None
#     password: Optional[OAuthFlowPassword] = None
#     clientCredentials: Optional[OAuthFlowClientCredentials] = None
#     authorizationCode: Optional[OAuthFlowAuthorizationCode] = None


# class OAuth2(SecurityBase):
#     type_: SecuritySchemeType = field(default=SecuritySchemeType.oauth2, name="type")
#     flows: OAuthFlows


# class OpenIdConnect(SecurityBase):
#     type_: SecuritySchemeType = field(
#         default=SecuritySchemeType.openIdConnect, name="type"
#     )
#     openIdConnectUrl: str


# SecurityScheme = Union[APIKey, HTTPBase, OAuth2, OpenIdConnect, HTTPBearer]


@dataclass_transform(frozen_default=True)
class BaseStruct(Struct, omit_defaults=True, frozen=True):
    def replace(self, **kwargs: Any):
        return struct_replace(self, **kwargs)


GEZero = Annotated[int, Meta(ge=0)]


class Contact(BaseStruct, kw_only=True):
    name: Optional[str] = None
    url: Optional[str] = None
    email: Optional[str] = None


class License(BaseStruct, kw_only=True):
    name: str
    identifier: Optional[str] = None
    url: Optional[str] = None


class Info(BaseStruct, kw_only=True):
    title: str
    summary: Optional[str] = None
    description: Optional[str] = None
    termsOfService: Optional[str] = None
    contact: Optional[Contact] = None
    license: Optional[License] = None
    version: str


class ServerVariable(BaseStruct, kw_only=True):
    enum: Annotated[Optional[list[str]], Meta(min_length=1)] = None
    default: str
    description: Optional[str] = None


class Server(BaseStruct, kw_only=True):
    url: Union[str, str]
    description: Optional[str] = None
    variables: Optional[dict[str, ServerVariable]] = None


class Reference(BaseStruct, kw_only=True):
    ref: str = field(name="$ref")


class Discriminator(BaseStruct, kw_only=True):
    propertyName: str
    mapping: Optional[dict[str, str]] = None


class XML(BaseStruct, kw_only=True):
    name: Optional[str] = None
    namespace: Optional[str] = None
    prefix: Optional[str] = None
    attribute: Optional[bool] = None
    wrapped: Optional[bool] = None


class ExternalDocumentation(BaseStruct, kw_only=True):
    description: Optional[str] = None
    url: str


class Schema(BaseStruct, kw_only=True):
    schema_: Optional[str] = field(default=None, name="$schema")
    vocabulary: Optional[str] = field(default=None, name="$vocabulary")
    id: Optional[str] = field(default=None, name="$id")
    anchor: Optional[str] = field(default=None, name="$anchor")
    dynamicAnchor: Optional[str] = field(default=None, name="$dynamicAnchor")
    ref: Optional[str] = field(default=None, name="$ref")
    dynamicRef: Optional[str] = field(default=None, name="$dynamicRef")
    defs: Optional[dict[str, "LenientSchema"]] = field(default=None, name="$defs")
    comment: Optional[str] = field(default=None, name="$comment")
    allOf: Optional[list["LenientSchema"]] = None
    anyOf: Optional[list["LenientSchema"]] = None
    oneOf: Optional[list["LenientSchema"]] = None
    not_: Optional["LenientSchema"] = field(default=None, name="not")
    if_: Optional["LenientSchema"] = field(default=None, name="if")
    then: Optional["LenientSchema"] = None
    else_: Optional["LenientSchema"] = field(default=None, name="else")
    dependentSchemas: Optional[dict[str, "LenientSchema"]] = None
    prefixItems: Optional[list["LenientSchema"]] = None
    contains: Optional["LenientSchema"] = None
    properties: Optional[dict[str, "LenientSchema"]] = None
    patternProperties: Optional[dict[str, "LenientSchema"]] = None
    additionalProperties: Optional["LenientSchema"] = None
    propertyNames: Optional["LenientSchema"] = None
    unevaluatedItems: Optional["LenientSchema"] = None
    unevaluatedProperties: Optional["LenientSchema"] = None
    type: Optional[str] = None
    enum: Optional[list[Any]] = None
    const: Optional[Any] = None
    multipleOf: Optional[Annotated[float, Meta(gt=0)]] = None
    maximum: Optional[float] = None
    exclusiveMaximum: Optional[float] = None
    minimum: Optional[float] = None
    exclusiveMinimum: Optional[float] = None
    maxLength: Optional[GEZero] = None
    minLength: Optional[GEZero] = None
    pattern: Optional[str] = None
    maxItems: Optional[GEZero] = None
    minItems: Optional[GEZero] = None
    uniqueItems: Optional[bool] = None
    maxContains: Optional[GEZero] = None
    minContains: Optional[GEZero] = None
    maxProperties: Optional[GEZero] = None
    minProperties: Optional[GEZero] = None
    required: Optional[list[str]] = None
    dependentRequired: Optional[dict[str, set[str]]] = None
    format: Optional[str] = None
    contentEncoding: Optional[str] = None
    contentMediaType: Optional[str] = None
    contentSchema: Optional["LenientSchema"] = None
    title: Optional[str] = None
    description: Optional[str] = None
    default: Optional[Any] = None
    deprecated: Optional[bool] = None
    readOnly: Optional[bool] = None
    writeOnly: Optional[bool] = None
    examples: Optional[list[Any]] = None
    discriminator: Optional[Discriminator] = None
    xml: Optional[XML] = None
    externalDocs: Optional[ExternalDocumentation] = None


LenientSchema = Union[Schema, Reference, bool]


class Example(TypedDict, total=False):
    summary: Optional[str]
    description: Optional[str]
    value: Optional[Any]
    externalValue: Optional[str]


class ParameterInType(Enum):
    query = "query"
    header = "header"
    path = "path"
    cookie = "cookie"


class Encoding(BaseStruct, kw_only=True):
    contentType: Optional[str] = None
    headers: Optional[dict[str, Union["Header", Reference]]] = None
    style: Optional[str] = None
    explode: Optional[bool] = None
    allowReserved: Optional[bool] = None


class MediaType(BaseStruct, kw_only=True):
    schema_: Optional[Union[Schema, Reference]] = field(default=None, name="schema")
    example: Optional[Any] = None
    examples: Optional[dict[str, Union[Example, Reference]]] = None
    encoding: Optional[dict[str, Encoding]] = None


class ParameterBase(BaseStruct, kw_only=True):
    description: Optional[str] = None
    required: Optional[bool] = None
    deprecated: Optional[bool] = None
    # Serialization rules for simple scenarios
    style: Optional[str] = None
    explode: Optional[bool] = None
    allowReserved: Optional[bool] = None
    schema_: Optional[Union[Schema, Reference]] = field(default=None, name="schema")
    example: Optional[Any] = None
    examples: Optional[dict[str, Union[Example, Reference]]] = None
    # Serialization rules for more complex scenarios
    content: Optional[dict[str, MediaType]] = None


class Parameter(ParameterBase):
    name: str
    in_: ParameterInType = field(name="in")


class Header(ParameterBase):
    pass


class RequestBody(BaseStruct, kw_only=True):
    description: Optional[str] = None
    content: dict[str, MediaType]
    required: Optional[bool] = None


class Link(BaseStruct, kw_only=True):
    operationRef: Optional[str] = None
    operationId: Optional[str] = None
    parameters: Optional[dict[str, Union[Any, str]]] = None
    requestBody: Optional[Union[Any, str]] = None
    description: Optional[str] = None
    server: Optional[Server] = None


class Response(BaseStruct, kw_only=True):
    description: str
    headers: Optional[dict[str, Union[Header, Reference]]] = None
    content: Optional[dict[str, MediaType]] = None
    links: Optional[dict[str, Union[Link, Reference]]] = None


class Operation(BaseStruct, kw_only=True):
    tags: Optional[list[str]] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    externalDocs: Optional[ExternalDocumentation] = None
    operationId: Optional[str] = None
    parameters: Optional[list[Union[Parameter, Reference]]] = None
    requestBody: Optional[Union[RequestBody, Reference]] = None
    # Using Any for Specification Extensions
    responses: dict[str, Union[Response, Any]] = field(default_factory=dict)
    callbacks: Optional[dict[str, Union[dict[str, "PathItem"], Reference]]] = None
    deprecated: Optional[bool] = None
    security: Optional[list[dict[str, list[str]]]] = None
    servers: Optional[list[Server]] = None


class PathItem(BaseStruct, kw_only=True):
    ref: Optional[str] = field(default=None, name="$ref")
    summary: Optional[str] = None
    description: Optional[str] = None
    get: Optional[Operation] = None
    put: Optional[Operation] = None
    post: Optional[Operation] = None
    delete: Optional[Operation] = None
    options: Optional[Operation] = None
    head: Optional[Operation] = None
    patch: Optional[Operation] = None
    trace: Optional[Operation] = None
    servers: Optional[list[Server]] = None
    parameters: Optional[list[Union[Parameter, Reference]]] = None


class Components(BaseStruct, kw_only=True):
    schemas: Optional[dict[str, Union[Schema, Reference]]] = None
    responses: Optional[dict[str, Union[Response, Reference]]] = None
    parameters: Optional[dict[str, Union[Parameter, Reference]]] = None
    examples: Optional[dict[str, Union[Example, Reference]]] = None
    requestBodies: Optional[dict[str, Union[RequestBody, Reference]]] = None
    headers: Optional[dict[str, Union[Header, Reference]]] = None
    # securitySchemes: Optional[dict[str, Union[SecurityScheme, Reference]]] = None
    links: Optional[dict[str, Union[Link, Reference]]] = None
    # Using Any for Specification Extensions
    callbacks: Optional[dict[str, Union[dict[str, PathItem], Reference, Any]]] = None
    pathItems: Optional[dict[str, Union[PathItem, Reference]]] = None


class Tag(BaseStruct, kw_only=True):
    name: str
    description: Optional[str] = None
    externalDocs: Optional[ExternalDocumentation] = None


class OpenAPI(BaseStruct, kw_only=True):
    openapi: str
    info: Info
    jsonSchemaDialect: Optional[str] = None
    servers: Optional[list[Server]] = None
    # Using Any for Specification Extensions
    paths: Optional[dict[str, Union[PathItem, Any]]] = None
    webhooks: Optional[dict[str, Union[PathItem, Reference]]] = None
    components: Optional[Components] = None
    security: Optional[list[dict[str, list[str]]]] = None
    tags: Optional[list[Tag]] = None
    externalDocs: Optional[ExternalDocumentation] = None
    # responses: dict[str, Response]


# class IOASConfig(TypedDict, total=False):
#     errors: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]]
#     in_schema: bool


class RouteConfig(BaseStruct):
    errors: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]] = field(
        default_factory=tuple
    )
    in_schema: bool = True
