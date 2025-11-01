import re
from typing import Any, Sequence, cast, get_args

from msgspec import Struct

from lihil.config.app_config import IOASConfig
from lihil.constant.status import phrase
from lihil.errors import LihilError
from lihil.interface import RegularTypes, is_present, is_set
from lihil.oas import model as oasmodel
from lihil.problems import (
    DetailBase,
    InvalidAuthError,
    InvalidRequestErrors,
    ProblemDetail,
)
from lihil.routing import Endpoint, Route, RouteBase
from lihil.signature import EndpointSignature, RequestParam
from lihil.signature.parser import BodyParam, is_file_body
from lihil.utils.json import SchemaHook, json_schema
from lihil.utils.string import to_kebab_case, trimdoc

SchemasDict = dict[str, oasmodel.LenientSchema]
SecurityDict = dict[str, oasmodel.SecurityScheme | oasmodel.Reference]
ComponentsDict = dict[str, Any]


class DefinitionOutput(Struct):
    result: oasmodel.Schema
    component: None = None


class ReferenceOutput(Struct):
    result: oasmodel.Reference
    component: SchemasDict


SchemaOutput = DefinitionOutput | ReferenceOutput
"""When component is not None result contains reference"""

PROBLEM_CONTENTTYPE = "application/problem+json"


class OneOfOutput(Struct):
    oneOf: list[SchemaOutput]


class SchemaGenerationError(LihilError):
    """Raised when OpenAPI schema generation fails for a specific element."""

    def __init__(
        self,
        message: str,
        *,
        type_hint: Any | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.base_message = message
        self.type_hint = self._type_repr(type_hint) if type_hint is not None else None
        self.detail = detail or ""
        self.frames: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _type_repr(value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return getattr(value, "__name__", None) or repr(value)
        except Exception:  # pragma: no cover - defensive
            return "<unrepresentable>"

    def add_frame(self, kind: str, **info: Any):
        self.frames.setdefault(kind, {}).update(info)

    def get_frame(self, kind: str) -> dict[str, Any]:
        return self.frames.get(kind, {})

    def describe(self) -> tuple[str, str | None]:
        param_info = self.get_frame("param")
        if param_info:
            source = param_info.get("source", "param")
            name = param_info.get("name", "<unknown>")
            return (f"Param {source} {name}", self.type_hint)

        resp_info = self.get_frame("response")
        if resp_info:
            status = resp_info.get("status", "<status>")
            content_type = resp_info.get("content_type")
            if content_type:
                return (f"Response {status} {content_type}", self.type_hint)
            return (f"Response {status}", self.type_hint)

        return ("Schema", self.type_hint)

    def format_context(self, descriptor: str, type_hint: str | None) -> str:
        param_info = self.get_frame("param")
        if param_info:
            source = param_info.get("source", "param")
            source_name = source.replace("_", " ").title()
            name = param_info.get("name", "<unknown>")
            detail = f"{name}: {source_name}"
            if type_hint:
                detail += f"[{type_hint}]"
            return f" ({detail})"

        resp_info = self.get_frame("response")
        if resp_info:
            status = resp_info.get("status", "<status>")
            content_type = resp_info.get("content_type")
            parts: list[str] = []
            if status:
                parts.append(str(status))
            if content_type:
                ct_part = str(content_type)
                if type_hint:
                    ct_part = f"{ct_part} [{type_hint}]"
                parts.append(ct_part)
            elif type_hint:
                parts.append(f"[{type_hint}]")
            scheme = ", ".join(parts)
            return f" -> Response[{scheme}]"

        if descriptor:
            detail = descriptor
            if type_hint:
                detail += f" [{type_hint}]"
            return f" ({detail})"

        if type_hint:
            return f" [{type_hint}]"

        return ""


class SchemaGenerationAggregateError(LihilError):
    """Aggregated schema generation errors collected across routes."""

    def __init__(self, route_map: dict[str, list[SchemaGenerationError]]) -> None:
        self.route_map = {k: list(v) for k, v in route_map.items()}
        super().__init__("Failed to generate OpenAPI schema")

    @classmethod
    def from_errors(
        cls, errors: Sequence[SchemaGenerationError]
    ) -> "SchemaGenerationAggregateError":
        route_map: dict[str, list[SchemaGenerationError]] = {}

        for error in errors:
            route_path = error.get_frame("route").get("path", "<unknown-route>")
            endpoint_info = error.get_frame("endpoint")
            method = endpoint_info.get("method", "<unknown-method>")
            name = endpoint_info.get("name", "<unknown-endpoint>")

            key = f"{method} {route_path} {name}"
            route_map.setdefault(key, []).append(error)

        return cls(route_map)

    @property
    def errors(self) -> list[SchemaGenerationError]:
        return [error for errors in self.route_map.values() for error in errors]

    def __str__(self) -> str:  # pragma: no cover - formatting helper
        lines = [super().__str__()]
        detail_blocks: list[str] = []
        seen_details: set[str] = set()

        for base_line, errors in self.route_map.items():
            for error in errors:
                descriptor, type_hint = error.describe()
                context = error.format_context(descriptor, type_hint)
                message = error.base_message
                lines.append(f"- {base_line}{context} - {message}")
                if detail := (error.detail or "").strip():
                    if detail not in seen_details:
                        seen_details.add(detail)
                        detail_blocks.append(detail)

        if detail_blocks:
            lines.append("")
            for block in detail_blocks:
                lines.extend(block.splitlines())

        return "\n".join(lines)


def oas_schema(types: RegularTypes, schema_hook: SchemaHook = None) -> SchemaOutput:
    if types is object:
        types = Any

    try:
        schema, definitions = json_schema(types, schema_hook)
    except SchemaGenerationError:
        raise
    except Exception as exc:
        raise SchemaGenerationError(
            f"Unable to build JSON schema from type",
            type_hint=types,
            detail=str(exc),
        ) from exc

    if anyOf := schema.pop("anyOf", None):  # rename
        schema["oneOf"] = anyOf

    if definitions:
        comp_dict = {
            name: oasmodel.Schema(**schema) for name, schema in definitions.items()
        }
        return ReferenceOutput(
            cast(oasmodel.Reference, schema), cast(SchemasDict, comp_dict)
        )
    else:
        return DefinitionOutput(cast(oasmodel.Schema, schema))


def type_to_content(
    type_: Any, schemas: SchemasDict, content_type: str = "application/json"
) -> dict[str, oasmodel.MediaType]:
    output = oas_schema(type_)
    if output.component:
        schemas.update(output.component)
        media_type = oasmodel.MediaType(schema_=output.result)
    else:
        media_type = oasmodel.MediaType(schema_=output.result)
    return {content_type: media_type}


def detail_base_to_content(
    err_type: type[DetailBase[Any]] | type[ProblemDetail[Any]],
    problem_content: dict[str, oasmodel.MediaType],
    schemas: SchemasDict,
    content_type: str = PROBLEM_CONTENTTYPE,
) -> dict[str, oasmodel.MediaType]:
    if not issubclass(err_type, DetailBase):
        return type_to_content(err_type, schemas)

    ref: oasmodel.Reference | None = None
    org_base = getattr(err_type, "__orig_bases__", ())
    for base in org_base:
        typevars = get_args(base)
        for var in typevars:
            if var is str:
                continue
            output = oas_schema(var)
            output = cast(ReferenceOutput, output)
            ref = output.result
            schemas.update(output.component)
            break

    pb_name = ProblemDetail.__name__
    err_name = err_type.__name__

    # Get the problem schema from schemas
    problem_schema = schemas.get(pb_name)

    # if not problem_schema: unreachable
    #     raise ValueError(f"Schema for {pb_name} not found in schemas")

    # Create a new schema for this specific error type
    assert isinstance(problem_schema, oasmodel.Schema)

    # Clone the problem schema properties
    assert is_set(problem_schema.properties)
    properties = problem_schema.properties.copy()

    if ref is not None:
        properties["detail"] = ref

    example = err_type.__json_example__()
    # Add a link to the problems page for this error type
    problem_type = example.type_
    problem_link = f"/problems?search={problem_type}"

    # Get schema from ProblemDetail using json_schema
    schema_output = oas_schema(type(example))
    if schema_output.component:
        schemas.update(schema_output.component)

    schemas[err_name] = oasmodel.Schema(
        type="object",
        properties=properties,
        examples=[example.asdict()],
        description=trimdoc(err_type.__doc__) or f"{err_name}",
        externalDocs=oasmodel.ExternalDocumentation(
            description=f"Learn more about {err_name}", url=problem_link
        ),
    )

    # Return a reference to this schema
    return {
        content_type: oasmodel.MediaType(
            schema_=oasmodel.Reference(ref=f"#/components/schemas/{err_name}")
        )
    }


def _single_field_schema(
    param: "RequestParam[Any]", schemas: SchemasDict
) -> oasmodel.Parameter:
    output = oas_schema(param.type_)
    param_schema: dict[str, Any] = {
        "name": param.alias,
        "in_": param.source,
        "required": param.required,
    }
    if output.component:  # reference
        schemas.update(output.component)
    param_schema["schema_"] = output.result
    ps = oasmodel.Parameter(**param_schema)
    return ps


def param_schema(
    ep_deps: EndpointSignature[Any], schemas: SchemasDict
) -> list[oasmodel.Parameter | oasmodel.Reference]:
    parameters: list[oasmodel.Parameter | oasmodel.Reference] = []
    single_value_param_group = (
        ep_deps.query_params,
        ep_deps.path_params,
        ep_deps.header_params,
    )

    for group in single_value_param_group:
        for p in group.values():
            try:
                ps = _single_field_schema(p, schemas)
            except SchemaGenerationError as exc:
                exc.add_frame("param", name=p.name, source=p.source)
                raise
            parameters.append(ps)
    return parameters


def example_from_detail_base(
    err_type: type[DetailBase[Any]], problem_path: str
) -> oasmodel.Schema:
    example = err_type.__json_example__()
    err_name = err_type.__name__

    # Create a schema for this specific error type
    problem_type = example.type_
    problem_url = f"{problem_path}/search?{problem_type}"
    error_schema = oasmodel.Schema(
        type="object",
        title=err_name,  # Add title to make it show up in Swagger UI
        properties={
            "type": oasmodel.Schema(type="string", examples=[example.type_]),
            "title": oasmodel.Schema(type="string", examples=[example.title]),
            "status": oasmodel.Schema(type="integer", examples=[example.status]),
            "detail": oasmodel.Schema(type="string", examples=[example.detail]),
            "instance": oasmodel.Schema(type="string", examples=[example.instance]),
        },
        examples=[example.asdict()],
        description=trimdoc(err_type.__doc__) or err_name,
        externalDocs=oasmodel.ExternalDocumentation(
            description=f"Learn more about {err_name}", url=problem_url
        ),
    )
    return error_schema


def file_body_to_content(
    param: BodyParam[Any, Any], _: SchemasDict
) -> dict[str, oasmodel.MediaType]:
    schema = {"type": "string", "format": "binary"}
    # if False: # list[UploadFile], not Implemented
    # schema = {"type": "array", "items": schema}

    schema = {
        "type": "object",
        "properties": {param.name: schema},
        "required": [param.name],
    }
    media_type = oasmodel.MediaType(schema_=schema)
    return {"multipart/form-data": media_type}


def body_schema(
    ep_deps: EndpointSignature[Any], schemas: SchemasDict
) -> oasmodel.RequestBody | None:
    if not (body_param := ep_deps.body_param):
        return None
    _, param = body_param
    if is_file_body(param.type_):
        content = file_body_to_content(param, schemas)
    else:
        try:
            content = type_to_content(param.type_, schemas, param.content_type)
        except SchemaGenerationError as exc:
            exc.add_frame("param", name=param.name, source="body")
            raise
    body = oasmodel.RequestBody(content=content, required=True)
    return body


def get_err_resp_schemas(ep: Endpoint[Any], schemas: SchemasDict, problem_path: str):
    try:
        problem_content = schemas.get(ProblemDetail.__name__, None) or type_to_content(
            ProblemDetail, schemas
        )
    except SchemaGenerationError as exc:
        exc.add_frame("response", status="problem", content_type=PROBLEM_CONTENTTYPE)
        raise
    problem_content = cast(dict[str, oasmodel.MediaType], problem_content)

    resps: dict[str, oasmodel.Response] = {}

    if user_provid_errors := ep.props.problems:
        errors = user_provid_errors + [InvalidRequestErrors]
    else:
        errors = (InvalidRequestErrors,)

    if ep.props.auth_scheme:
        errors += (InvalidAuthError,)

    errors_by_status: dict[int, list[type[DetailBase[Any]]]] = {}

    for err in errors:
        status_code = err.__status__
        if status_code in errors_by_status:
            errors_by_status[status_code].append(err)
        else:
            errors_by_status[status_code] = [err]

    # Create response objects for each status code
    for status_code, error_types in errors_by_status.items():
        status_str = str(status_code)

        if len(error_types) == 1:
            # Single error type for this status code
            err_type = error_types[0]
            err_name = err_type.__name__
            try:
                content = detail_base_to_content(err_type, problem_content, schemas)
            except SchemaGenerationError as exc:
                exc.add_frame(
                    "response",
                    status=status_str,
                    content_type=PROBLEM_CONTENTTYPE,
                )
                raise

            # Create link to problem documentation
            resps[status_str] = oasmodel.Response(
                description=phrase(status_code),
                content=content,
            )
        else:
            # Multiple error types for this status code - use oneOf
            one_of_schemas: list[Any] = []
            error_descriptions: list[str] = []
            error_names: list[str] = []

            for err_type in error_types:
                err_name = err_type.__name__
                error_names.append(err_name)

                if err_name not in schemas:
                    schemas[err_name] = example_from_detail_base(err_type, problem_path)
                    try:
                        content = detail_base_to_content(
                            err_type, problem_content, schemas
                        )
                    except SchemaGenerationError as exc:
                        exc.add_frame(
                            "response",
                            status=status_str,
                            content_type=PROBLEM_CONTENTTYPE,
                        )
                        raise

                # Create a schema with title that references the actual schema
                schema_with_title = oasmodel.Schema(
                    title=err_name,
                    allOf=[oasmodel.Reference(ref=f"#/components/schemas/{err_name}")],
                )

                # Add the schema with title to the oneOf list
                one_of_schemas.append(schema_with_title)
                error_descriptions.append(err_name)

            error_mapping = {
                err_type.__problem_type__
                or to_kebab_case(
                    err_type.__name__
                ): f"#/components/schemas/{err_type.__name__}"
                for err_type in error_types
            }

            one_of_schema = oasmodel.Schema(
                oneOf=one_of_schemas,
                discriminator=oasmodel.Discriminator(
                    propertyName="type", mapping=error_mapping
                ),
                description=f"chek {problem_path} for further details",
            )

            # Add to responses
            resps[status_str] = oasmodel.Response(
                description=phrase(status_code),
                content={
                    PROBLEM_CONTENTTYPE: oasmodel.MediaType(schema_=one_of_schema)
                },
            )

    return resps


def get_resp_schemas(
    ep: Endpoint[Any], schemas: SchemasDict, problem_path: str
) -> dict[str, oasmodel.Response]:
    resps: dict[str, oasmodel.Response] = {
        "200": oasmodel.Response(description="Sucessful Response")
    }

    for status, ep_return in ep.sig.return_params.items():
        return_type = ep_return.type_
        content_type = ep_return.content_type or "Missing"
        if status < 400:
            description = "Successful Response"
        elif status < 500:
            description = "ClientSide Error"
        else:
            description = "ServerSide Error"

        status = str(status)

        if not is_present(return_type):
            # TODO: show no return type here
            return resps
        else:
            if ep_return.mark_type == "empty":
                resps[status] = oasmodel.Response(description="No Content")
            else:
                try:
                    content = type_to_content(return_type, schemas, content_type)
                except SchemaGenerationError as exc:
                    exc.add_frame(
                        "response",
                        status=status,
                        content_type=content_type,
                    )
                    raise
                resp = oasmodel.Response(description=description, content=content)
                resps[status] = resp
    return resps


def generate_param_schema(ep_deps: EndpointSignature[Any], schemas: SchemasDict):
    params = param_schema(ep_deps, schemas)
    body = body_schema(ep_deps, schemas)
    return params, body


def generate_unique_id(ep: Endpoint[Any]) -> str:
    operation_id = f"{ep.name}{ep.path}"
    operation_id = re.sub(r"\W", "_", operation_id)
    operation_id = f"{operation_id}_{ep.method.lower()}"
    return operation_id


def get_ep_security(
    ep: Endpoint[Any], security_schemas: SecurityDict
) -> list[dict[str, list[str]]]:
    security_scopes: list[dict[str, list[str]]] = []
    auth_scheme = ep.props.auth_scheme
    if auth_scheme:
        scheme_name = auth_scheme.scheme_name
        security_schemas[scheme_name] = cast(oasmodel.SecurityScheme, auth_scheme.model)
        security: dict[str, list[str]] = {scheme_name: []}
        if auth_scopes := auth_scheme.scopes:
            for name, scope in auth_scopes.items():
                security[name].append(scope)

        security_scopes.append(security)
    # TODO: http auth
    return security_scopes


def generate_op_from_ep(
    ep: Endpoint[Any],
    schemas: SchemasDict,
    security_schemas: SecurityDict,
    problem_path: str,
) -> oasmodel.Operation:
    tags = ep.props.tags
    summary = ep.name.replace("_", " ").title()
    description = trimdoc(ep.unwrapped_func.__doc__) or "Missing Description"
    operationId = generate_unique_id(ep)

    try:
        params, body = generate_param_schema(ep.sig, schemas)
        resps = get_resp_schemas(ep, schemas, problem_path)
        err_resps = get_err_resp_schemas(ep, schemas, problem_path)
    except SchemaGenerationError as exc:
        exc.add_frame("endpoint", method=ep.method, name=ep.name)
        raise

    security = get_ep_security(ep, security_schemas)
    resps.update(err_resps)

    op = oasmodel.Operation(
        tags=tags or oasmodel.UNSET,
        summary=summary,
        description=description,
        operationId=operationId,
        parameters=params,
        security=security,
        requestBody=body or oasmodel.UNSET,
    )
    for status, resp in resps.items():
        op.responses[status] = resp
    return op


def get_path_item_from_route(
    route: Route,
    schemas: SchemasDict,
    security_schemas: SecurityDict,
    problem_path: str,
) -> oasmodel.PathItem:

    # 1 pathitem = 1 route
    # 1 operation = 1 endpoint

    epoint_ops: dict[str, Any] = {}
    for endpoint in route.endpoints.values():
        if not endpoint.props.in_schema:
            continue
        try:
            operation = generate_op_from_ep(
                ep=endpoint,
                schemas=schemas,
                security_schemas=security_schemas,
                problem_path=problem_path,
            )
        except SchemaGenerationError as exc:
            exc.add_frame("route", path=route.path)
            raise
        epoint_ops[endpoint.method.lower()] = operation

    path_item = oasmodel.PathItem(**epoint_ops)
    return path_item


class ValidationErrors(Struct):
    location: str
    param_name: str


def generate_oas(
    routes: Sequence[RouteBase],
    oas_config: IOASConfig,
    app_version: str,
) -> oasmodel.OpenAPI:
    "Return application/json response"
    paths: dict[str, oasmodel.PathItem] = {}
    components: ComponentsDict = {}
    schemas: dict[str, Any] = {}
    security_schemas: SecurityDict = {}
    errors: list[SchemaGenerationError] = []

    for route in routes:
        if not isinstance(route, Route) or not route.props.in_schema:
            continue
        try:
            paths[route.path] = get_path_item_from_route(
                route=route,
                schemas=schemas,
                security_schemas=security_schemas,
                problem_path=oas_config.PROBLEM_PATH,
            )
        except SchemaGenerationError as exc:
            errors.append(exc)

    if errors:
        raise SchemaGenerationAggregateError.from_errors(errors)
    if schemas:
        components["schemas"] = schemas

    if security_schemas:
        components["securitySchemes"] = security_schemas

    comp = oasmodel.Components(**components)
    info = oasmodel.Info(title=oas_config.TITLE, version=app_version)

    oas = oasmodel.OpenAPI(
        openapi=oas_config.VERSION,
        info=info,
        paths=paths,
        components=comp,
    )
    return oas
