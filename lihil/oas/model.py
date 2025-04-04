from enum import Enum
from typing import Annotated, Any, Literal, Sequence, TypedDict, Union

from msgspec import Meta, field

from lihil.interface import UNSET, Record, Unset
from lihil.problems import DetailBase

# from msgspec.structs import replace as struct_replace


GEZero = Annotated[int, Meta(ge=0)]


type SecuritySchemes = Literal["apiKey", "http", "oauth2", "openIdConnect"]


class OASRecord(Record): ...


class AuthBase(OASRecord, kw_only=True):
    type_: SecuritySchemes = field(name="type")
    description: Unset[str] = UNSET


class APIKeyIn(Enum):
    query = "query"
    header = "header"
    cookie = "cookie"


class APIKey(AuthBase, kw_only=True):
    type_: SecuritySchemes = field(default="apiKey", name="type")
    in_: APIKeyIn = field(name="in")
    name: str


class HTTPBase(AuthBase, kw_only=True):
    type_: SecuritySchemes = field(default="http", name="type")
    scheme: str


class HTTPBearer(HTTPBase):
    scheme: Literal["bearer"] = "bearer"
    bearerFormat: Unset[str] = UNSET


class OAuthFlow(OASRecord, kw_only=True):
    refreshUrl: Unset[str] = UNSET
    scopes: dict[str, str] = {}


class OAuthFlowImplicit(OAuthFlow):
    authorizationUrl: str


class OAuthFlowPassword(OAuthFlow):
    tokenUrl: str


class OAuthFlowClientCredentials(OAuthFlow):
    tokenUrl: str


class OAuthFlowAuthorizationCode(OAuthFlow):
    authorizationUrl: str
    tokenUrl: str


class OAuthFlows(OASRecord, kw_only=True):
    implicit: Unset[OAuthFlowImplicit] = UNSET
    password: Unset[OAuthFlowPassword] = UNSET
    clientCredentials: Unset[OAuthFlowClientCredentials] = UNSET
    authorizationCode: Unset[OAuthFlowAuthorizationCode] = UNSET


class OAuth2(AuthBase, kw_only=True):
    type_: SecuritySchemes = field(default="oauth2", name="type")
    flows: OAuthFlows


class OpenIdConnect(AuthBase, kw_only=True):
    type_: SecuritySchemes = field(default="openIdConnect", name="type")
    openIdConnectUrl: str


SecurityScheme = Union[APIKey, HTTPBase, OAuth2, OpenIdConnect, HTTPBearer]


class Contact(OASRecord, kw_only=True):
    name: Unset[str] = UNSET
    url: Unset[str] = UNSET
    email: Unset[str] = UNSET


class License(OASRecord, kw_only=True):
    name: str
    identifier: Unset[str] = UNSET
    url: Unset[str] = UNSET


class Info(OASRecord, kw_only=True):
    title: str
    summary: Unset[str] = UNSET
    description: Unset[str] = UNSET
    termsOfService: Unset[str] = UNSET
    contact: Unset[Contact] = UNSET
    license: Unset[License] = UNSET
    version: str


class ServerVariable(OASRecord, kw_only=True):
    enum: Annotated[Unset[list[str]], Meta(min_length=1)] = UNSET
    default: str
    description: Unset[str] = UNSET


class Server(OASRecord, kw_only=True):
    url: Union[str, str]
    description: Unset[str] = UNSET
    variables: Unset[dict[str, ServerVariable]] = UNSET


class Reference(OASRecord, kw_only=True):
    ref: str = field(name="$ref")


class Discriminator(OASRecord, kw_only=True):
    propertyName: str
    mapping: Unset[dict[str, str]] = UNSET


class XML(OASRecord, kw_only=True):
    name: Unset[str] = UNSET
    namespace: Unset[str] = UNSET
    prefix: Unset[str] = UNSET
    attribute: Unset[bool] = UNSET
    wrapped: Unset[bool] = UNSET


class ExternalDocumentation(OASRecord, kw_only=True):
    description: Unset[str] = UNSET
    url: str


class Schema(OASRecord, kw_only=True):
    schema_: Unset[str] = field(default=UNSET, name="$schema")
    vocabulary: Unset[str] = field(default=UNSET, name="$vocabulary")
    id: Unset[str] = field(default=UNSET, name="$id")
    anchor: Unset[str] = field(default=UNSET, name="$anchor")
    dynamicAnchor: Unset[str] = field(default=UNSET, name="$dynamicAnchor")
    ref: Unset[str] = field(default=UNSET, name="$ref")
    dynamicRef: Unset[str] = field(default=UNSET, name="$dynamicRef")
    defs: Unset[dict[str, "LenientSchema"]] = field(default=UNSET, name="$defs")
    comment: Unset[str] = field(default=UNSET, name="$comment")
    allOf: Unset[list["LenientSchema"]] = UNSET
    anyOf: Unset[list["LenientSchema"]] = UNSET
    oneOf: Unset[list["LenientSchema"]] = UNSET
    not_: Unset["LenientSchema"] = field(default=UNSET, name="not")
    if_: Unset["LenientSchema"] = field(default=UNSET, name="if")
    then: Unset["LenientSchema"] = UNSET
    else_: Unset["LenientSchema"] = field(default=UNSET, name="else")
    dependentSchemas: Unset[dict[str, "LenientSchema"]] = UNSET
    prefixItems: Unset[list["LenientSchema"]] = UNSET
    contains: Unset["LenientSchema"] = UNSET
    properties: Unset[dict[str, "LenientSchema"]] = UNSET
    patternProperties: Unset[dict[str, "LenientSchema"]] = UNSET
    additionalProperties: Unset["LenientSchema"] = UNSET
    propertyNames: Unset["LenientSchema"] = UNSET
    unevaluatedItems: Unset["LenientSchema"] = UNSET
    unevaluatedProperties: Unset["LenientSchema"] = UNSET
    type: Unset[str] = UNSET
    enum: Unset[list[Any]] = UNSET
    const: Unset[Any] = UNSET
    multipleOf: Unset[Annotated[float, Meta(gt=0)]] = UNSET
    maximum: Unset[float] = UNSET
    exclusiveMaximum: Unset[float] = UNSET
    minimum: Unset[float] = UNSET
    exclusiveMinimum: Unset[float] = UNSET
    maxLength: Unset[GEZero] = UNSET
    minLength: Unset[GEZero] = UNSET
    pattern: Unset[str] = UNSET
    maxItems: Unset[GEZero] = UNSET
    minItems: Unset[GEZero] = UNSET
    uniqueItems: Unset[bool] = UNSET
    maxContains: Unset[GEZero] = UNSET
    minContains: Unset[GEZero] = UNSET
    maxProperties: Unset[GEZero] = UNSET
    minProperties: Unset[GEZero] = UNSET
    required: Unset[list[str]] = UNSET
    dependentRequired: Unset[dict[str, set[str]]] = UNSET
    format: Unset[str] = UNSET
    contentEncoding: Unset[str] = UNSET
    contentMediaType: Unset[str] = UNSET
    contentSchema: Unset["LenientSchema"] = UNSET
    title: Unset[str] = UNSET
    description: Unset[str] = UNSET
    default: Unset[Any] = UNSET
    deprecated: Unset[bool] = UNSET
    readOnly: Unset[bool] = UNSET
    writeOnly: Unset[bool] = UNSET
    examples: Unset[list[Any]] = UNSET
    discriminator: Unset[Discriminator] = UNSET
    xml: Unset[XML] = UNSET
    externalDocs: Unset[ExternalDocumentation] = UNSET


LenientSchema = Union[Schema, Reference, bool]


class Example(TypedDict, total=False):
    summary: Unset[str]
    description: Unset[str]
    value: Unset[Any]
    externalValue: Unset[str]


class ParameterInType(Enum):
    query = "query"
    header = "header"
    path = "path"
    cookie = "cookie"


class Encoding(OASRecord, kw_only=True):
    contentType: Unset[str] = UNSET
    headers: Unset[dict[str, Union["Header", Reference]]] = UNSET
    style: Unset[str] = UNSET
    explode: Unset[bool] = UNSET
    allowReserved: Unset[bool] = UNSET


class MediaType(OASRecord, kw_only=True):
    schema_: Unset[Union[Schema, Reference]] = field(default=UNSET, name="schema")
    example: Unset[Any] = UNSET
    examples: Unset[dict[str, Union[Example, Reference]]] = UNSET
    encoding: Unset[dict[str, Encoding]] = UNSET


class ParameterBase(OASRecord, kw_only=True):
    description: Unset[str] = UNSET
    required: Unset[bool] = UNSET
    deprecated: Unset[bool] = UNSET
    # Serialization rules for simple scenarios
    style: Unset[str] = UNSET
    explode: Unset[bool] = UNSET
    allowReserved: Unset[bool] = UNSET
    schema_: Unset[Union[Schema, Reference]] = field(default=UNSET, name="schema")
    example: Unset[Any] = UNSET
    examples: Unset[dict[str, Union[Example, Reference]]] = UNSET
    # Serialization rules for more complex scenarios
    content: Unset[dict[str, MediaType]] = UNSET


class Parameter(ParameterBase):
    name: str
    in_: ParameterInType = field(name="in")


class Header(ParameterBase):
    pass


class RequestBody(OASRecord, kw_only=True):
    description: Unset[str] = UNSET
    content: dict[str, MediaType]
    required: Unset[bool] = UNSET


class Link(OASRecord, kw_only=True):
    operationRef: Unset[str] = UNSET
    operationId: Unset[str] = UNSET
    parameters: Unset[dict[str, Union[Any, str]]] = UNSET
    requestBody: Unset[Union[Any, str]] = UNSET
    description: Unset[str] = UNSET
    server: Unset[Server] = UNSET


class Response(OASRecord, kw_only=True):
    description: str
    headers: Unset[dict[str, Union[Header, Reference]]] = UNSET
    content: Unset[dict[str, MediaType]] = UNSET
    links: Unset[dict[str, Union[Link, Reference]]] = UNSET


class Operation(OASRecord, kw_only=True):
    tags: Unset[list[str]] = UNSET
    summary: Unset[str] = UNSET
    description: Unset[str] = UNSET
    externalDocs: Unset[ExternalDocumentation] = UNSET
    operationId: Unset[str] = UNSET
    parameters: Unset[list[Union[Parameter, Reference]]] = UNSET
    requestBody: Unset[Union[RequestBody, Reference]] = UNSET
    # Using Any for Specification Extensions
    responses: dict[str, Union[Response, Any]] = field(default_factory=dict)
    callbacks: Unset[dict[str, Union[dict[str, "PathItem"], Reference]]] = UNSET
    deprecated: Unset[bool] = UNSET
    security: Unset[list[dict[str, list[str]]]] = UNSET
    servers: Unset[list[Server]] = UNSET


class PathItem(OASRecord, kw_only=True):
    ref: Unset[str] = field(default=UNSET, name="$ref")
    summary: Unset[str] = UNSET
    description: Unset[str] = UNSET
    get: Unset[Operation] = UNSET
    put: Unset[Operation] = UNSET
    post: Unset[Operation] = UNSET
    delete: Unset[Operation] = UNSET
    options: Unset[Operation] = UNSET
    head: Unset[Operation] = UNSET
    patch: Unset[Operation] = UNSET
    trace: Unset[Operation] = UNSET
    servers: Unset[list[Server]] = UNSET
    parameters: Unset[list[Union[Parameter, Reference]]] = UNSET


class Components(OASRecord, kw_only=True):
    schemas: Unset[dict[str, Union[Schema, Reference]]] = UNSET
    responses: Unset[dict[str, Union[Response, Reference]]] = UNSET
    parameters: Unset[dict[str, Union[Parameter, Reference]]] = UNSET
    examples: Unset[dict[str, Union[Example, Reference]]] = UNSET
    requestBodies: Unset[dict[str, Union[RequestBody, Reference]]] = UNSET
    headers: Unset[dict[str, Union[Header, Reference]]] = UNSET
    securitySchemes: Unset[dict[str, Union[SecurityScheme, Reference]]] = UNSET
    links: Unset[dict[str, Union[Link, Reference]]] = UNSET
    callbacks: Unset[dict[str, Union[dict[str, PathItem], Reference, Any]]] = UNSET
    pathItems: Unset[dict[str, Union[PathItem, Reference]]] = UNSET


class Tag(OASRecord, kw_only=True):
    name: str
    description: Unset[str] = UNSET
    externalDocs: Unset[ExternalDocumentation] = UNSET


class OpenAPI(OASRecord, kw_only=True):
    openapi: str
    info: Info
    jsonSchemaDialect: Unset[str] = UNSET
    servers: Unset[list[Server]] = UNSET
    # Using Any for Specification Extensions
    paths: Unset[dict[str, Union[PathItem, Any]]] = UNSET
    webhooks: Unset[dict[str, Union[PathItem, Reference]]] = UNSET
    components: Unset[Components] = UNSET
    security: Unset[list[dict[str, list[str]]]] = UNSET
    tags: Unset[list[Tag]] = UNSET
    externalDocs: Unset[ExternalDocumentation] = UNSET
    # responses: dict[str, Response]


class RouteConfig(Record):
    tag: str = ""
    in_schema: bool = True
    errors: Sequence[type[DetailBase[Any]]] | type[DetailBase[Any]] = field(
        default_factory=tuple
    )

    # ep_config: EndpointConfig | None = UNSET
    # if provided, apply to all endpoint
