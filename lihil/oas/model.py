from enum import Enum
from typing import Annotated, Any, Literal, TypedDict, Union

from msgspec import Meta, field

from lihil.interface import UNSET, Base, Unset

GEZero = Annotated[int, Meta(ge=0)]


SecuritySchemeTypes = Literal["apiKey", "http", "oauth2", "openIdConnect"]


class OASB(Base):
    """
    Open API Specification Base
    """

    def __post_init__(self):
        """
        We replace all `None` value with msgspec.Unset

        This is because if there is any None value being encoded as `null` by msgspec
        Then swagger won't display anything.
        On the other hand, msgspec will skip field with value `UNSET` when encoding.
        """

        for field in self.__struct_fields__:
            if getattr(self, field) is None:
                setattr(self, field, UNSET)


class OASAuthModel(OASB, kw_only=True):
    type_: SecuritySchemeTypes = field(name="type")
    description: Unset[str] = UNSET


class OASAPIKeyIn(Enum):
    query = "query"
    header = "header"
    cookie = "cookie"


class OASAPIKey(OASAuthModel, kw_only=True):
    type_: SecuritySchemeTypes = field(default="apiKey", name="type")
    in_: OASAPIKeyIn = field(name="in")
    name: str


class OASHTTPBase(OASAuthModel, kw_only=True):
    type_: SecuritySchemeTypes = field(default="http", name="type")
    scheme: Literal["bearer", "digest", "basic"]


class OASHTTPBearer(OASHTTPBase):
    scheme: Literal["bearer"] = "bearer"
    bearerFormat: Unset[str] = UNSET


# ======================== OAuth ========================


class OASOAuthFlow(OASB, kw_only=True):
    refreshUrl: Unset[str] = UNSET
    scopes: dict[str, str] = {}


class OASOAuthFlowImplicit(OASOAuthFlow):
    authorizationUrl: str


class OASOAuthFlowPassword(OASOAuthFlow):
    tokenUrl: str


class OASOAuthFlowClientCredentials(OASOAuthFlow):
    tokenUrl: str


class OASOAuthFlowAuthorizationCode(OASOAuthFlow):
    authorizationUrl: str
    tokenUrl: str


class OASOAuthFlows(OASB, kw_only=True):
    implicit: Unset[OASOAuthFlowImplicit] = UNSET
    password: Unset[OASOAuthFlowPassword] = UNSET
    clientCredentials: Unset[OASOAuthFlowClientCredentials] = UNSET
    authorizationCode: Unset[OASOAuthFlowAuthorizationCode] = UNSET


class OASOAuth2(OASAuthModel, kw_only=True):
    type_: SecuritySchemeTypes = field(default="oauth2", name="type")
    flows: OASOAuthFlows


# ======================== OAuth ========================


class OASOpenIdConnect(OASAuthModel, kw_only=True):
    type_: SecuritySchemeTypes = field(default="openIdConnect", name="type")
    openIdConnectUrl: str


OASSecurityScheme = Union[OASAPIKey, OASHTTPBase, OASOAuth2, OASOpenIdConnect, OASHTTPBearer]


class OASContact(OASB, kw_only=True):
    name: Unset[str] = UNSET
    url: Unset[str] = UNSET
    email: Unset[str] = UNSET


class OASLicense(OASB, kw_only=True):
    name: str
    identifier: Unset[str] = UNSET
    url: Unset[str] = UNSET


class OASInfo(OASB, kw_only=True):
    title: str
    summary: Unset[str] = UNSET
    description: Unset[str] = UNSET
    termsOfService: Unset[str] = UNSET
    contact: Unset[OASContact] = UNSET
    license: Unset[OASLicense] = UNSET
    version: str


class OASServerVariable(OASB, kw_only=True):
    enum: Annotated[Unset[list[str]], Meta(min_length=1)] = UNSET
    default: str
    description: Unset[str] = UNSET


class OASServer(OASB, kw_only=True):
    url: Union[str, str]
    description: Unset[str] = UNSET
    variables: Unset[dict[str, OASServerVariable]] = UNSET


class OASReference(OASB, kw_only=True):
    ref: str = field(name="$ref")


class OASDiscriminator(OASB, kw_only=True):
    propertyName: str
    mapping: Unset[dict[str, str]] = UNSET


class OASXML(OASB, kw_only=True):
    name: Unset[str] = UNSET
    namespace: Unset[str] = UNSET
    prefix: Unset[str] = UNSET
    attribute: Unset[bool] = UNSET
    wrapped: Unset[bool] = UNSET


class OASExternalDocumentation(OASB, kw_only=True):
    description: Unset[str] = UNSET
    url: str


class OASSchema(OASB, kw_only=True):
    schema_: Unset[str] = field(default=UNSET, name="$schema")
    vocabulary: Unset[str] = field(default=UNSET, name="$vocabulary")
    id: Unset[str] = field(default=UNSET, name="$id")
    anchor: Unset[str] = field(default=UNSET, name="$anchor")
    dynamicAnchor: Unset[str] = field(default=UNSET, name="$dynamicAnchor")
    ref: Unset[str] = field(default=UNSET, name="$ref")
    dynamicRef: Unset[str] = field(default=UNSET, name="$dynamicRef")
    defs: Unset[dict[str, "OASLenientSchema"]] = field(default=UNSET, name="$defs")
    comment: Unset[str] = field(default=UNSET, name="$comment")
    allOf: Unset[list["OASLenientSchema"]] = UNSET
    anyOf: Unset[list["OASLenientSchema"]] = UNSET
    oneOf: Unset[list["OASLenientSchema"]] = UNSET
    not_: Unset["OASLenientSchema"] = field(default=UNSET, name="not")
    if_: Unset["OASLenientSchema"] = field(default=UNSET, name="if")
    then: Unset["OASLenientSchema"] = UNSET
    else_: Unset["OASLenientSchema"] = field(default=UNSET, name="else")
    dependentSchemas: Unset[dict[str, "OASLenientSchema"]] = UNSET
    prefixItems: Unset[list["OASLenientSchema"]] = UNSET
    contains: Unset["OASLenientSchema"] = UNSET
    properties: Unset[dict[str, "OASLenientSchema"]] = UNSET
    patternProperties: Unset[dict[str, "OASLenientSchema"]] = UNSET
    additionalProperties: Unset["OASLenientSchema"] = UNSET
    propertyNames: Unset["OASLenientSchema"] = UNSET
    unevaluatedItems: Unset["OASLenientSchema"] = UNSET
    unevaluatedProperties: Unset["OASLenientSchema"] = UNSET
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
    contentSchema: Unset["OASLenientSchema"] = UNSET
    title: Unset[str] = UNSET
    description: Unset[str] = UNSET
    default: Unset[Any] = UNSET
    deprecated: Unset[bool] = UNSET
    readOnly: Unset[bool] = UNSET
    writeOnly: Unset[bool] = UNSET
    examples: Unset[list[Any]] = UNSET
    discriminator: Unset[OASDiscriminator] = UNSET
    xml: Unset[OASXML] = UNSET
    externalDocs: Unset[OASExternalDocumentation] = UNSET


OASLenientSchema = Union[OASSchema, OASReference, bool]


class OASExample(TypedDict, total=False):
    summary: Unset[str]
    description: Unset[str]
    value: Unset[Any]
    externalValue: Unset[str]


class OASParameterInType(Enum):
    query = "query"
    header = "header"
    path = "path"
    cookie = "cookie"


class OASEncoding(OASB, kw_only=True):
    contentType: Unset[str] = UNSET
    headers: Unset[dict[str, Union["OASHeader", OASReference]]] = UNSET
    style: Unset[str] = UNSET
    explode: Unset[bool] = UNSET
    allowReserved: Unset[bool] = UNSET


class OASMediaType(OASB, kw_only=True):
    schema_: Unset[Union[OASSchema, OASReference]] = field(default=UNSET, name="schema")
    example: Unset[Any] = UNSET
    examples: Unset[dict[str, Union[OASExample, OASReference]]] = UNSET
    encoding: Unset[dict[str, OASEncoding]] = UNSET


class OASParameterBase(OASB, kw_only=True):
    description: Unset[str] = UNSET
    required: Unset[bool] = UNSET
    deprecated: Unset[bool] = UNSET
    # Serialization rules for simple scenarios
    style: Unset[str] = UNSET
    explode: Unset[bool] = UNSET
    allowReserved: Unset[bool] = UNSET
    schema_: Unset[Union[OASSchema, OASReference]] = field(default=UNSET, name="schema")
    example: Unset[Any] = UNSET
    examples: Unset[dict[str, Union[OASExample, OASReference]]] = UNSET
    # Serialization rules for more complex scenarios
    content: Unset[dict[str, OASMediaType]] = UNSET


class OASParameter(OASParameterBase):
    name: str
    in_: OASParameterInType = field(name="in")


class OASHeader(OASParameterBase):
    pass


class OASRequestBody(OASB, kw_only=True):
    description: Unset[str] = UNSET
    content: dict[str, OASMediaType]
    required: Unset[bool] = UNSET


class OASLink(OASB, kw_only=True):
    operationRef: Unset[str] = UNSET
    operationId: Unset[str] = UNSET
    parameters: Unset[dict[str, Union[Any, str]]] = UNSET
    requestBody: Unset[Union[Any, str]] = UNSET
    description: Unset[str] = UNSET
    server: Unset[OASServer] = UNSET


class OASResponse(OASB, kw_only=True):
    description: str
    headers: Unset[dict[str, Union[OASHeader, OASReference]]] = UNSET
    content: Unset[dict[str, OASMediaType]] = UNSET
    links: Unset[dict[str, Union[OASLink, OASReference]]] = UNSET


class OASOperation(OASB, kw_only=True):
    tags: Unset[list[str]] = UNSET
    summary: Unset[str] = UNSET
    description: Unset[str] = UNSET
    externalDocs: Unset[OASExternalDocumentation] = UNSET
    operationId: Unset[str] = UNSET
    parameters: Unset[list[Union[OASParameter, OASReference]]] = UNSET
    requestBody: Unset[Union[OASRequestBody, OASReference]] = UNSET
    # Using Any for Specification Extensions
    responses: dict[str, Union[OASResponse, Any]] = field(
        default_factory=dict[str, Union[OASResponse, Any]]
    )
    callbacks: Unset[dict[str, Union[dict[str, "OASPathItem"], OASReference]]] = UNSET
    deprecated: Unset[bool] = UNSET
    security: Unset[list[dict[str, list[str]]]] = UNSET
    servers: Unset[list[OASServer]] = UNSET


class OASPathItem(OASB, kw_only=True):
    ref: Unset[str] = field(default=UNSET, name="$ref")
    summary: Unset[str] = UNSET
    description: Unset[str] = UNSET
    get: Unset[OASOperation] = UNSET
    put: Unset[OASOperation] = UNSET
    post: Unset[OASOperation] = UNSET
    delete: Unset[OASOperation] = UNSET
    options: Unset[OASOperation] = UNSET
    head: Unset[OASOperation] = UNSET
    patch: Unset[OASOperation] = UNSET
    trace: Unset[OASOperation] = UNSET
    servers: Unset[list[OASServer]] = UNSET
    parameters: Unset[list[Union[OASParameter, OASReference]]] = UNSET


class OASComponents(OASB, kw_only=True):
    schemas: Unset[dict[str, Union[OASSchema, OASReference]]] = UNSET
    responses: Unset[dict[str, Union[OASResponse, OASReference]]] = UNSET
    parameters: Unset[dict[str, Union[OASParameter, OASReference]]] = UNSET
    examples: Unset[dict[str, Union[OASExample, OASReference]]] = UNSET
    requestBodies: Unset[dict[str, Union[OASRequestBody, OASReference]]] = UNSET
    headers: Unset[dict[str, Union[OASHeader, OASReference]]] = UNSET
    securitySchemes: Unset[dict[str, Union[OASSecurityScheme, OASReference]]] = UNSET
    links: Unset[dict[str, Union[OASLink, OASReference]]] = UNSET
    callbacks: Unset[dict[str, Union[dict[str, OASPathItem], OASReference, Any]]] = UNSET
    pathItems: Unset[dict[str, Union[OASPathItem, OASReference]]] = UNSET


class OASTag(OASB, kw_only=True):
    name: str
    description: Unset[str] = UNSET
    externalDocs: Unset[OASExternalDocumentation] = UNSET


class OASOpenAPI(OASB, kw_only=True):
    openapi: str
    info: OASInfo
    jsonSchemaDialect: Unset[str] = UNSET
    servers: Unset[list[OASServer]] = UNSET
    # Using Any for Specification Extensions
    paths: Unset[dict[str, Union[OASPathItem, Any]]] = UNSET
    webhooks: Unset[dict[str, Union[OASPathItem, OASReference]]] = UNSET
    components: Unset[OASComponents] = UNSET
    security: Unset[list[dict[str, list[str]]]] = UNSET
    tags: Unset[list[OASTag]] = UNSET
    externalDocs: Unset[OASExternalDocumentation] = UNSET
    # responses: dict[str, OASResponse]
