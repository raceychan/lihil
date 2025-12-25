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

SchemasDict = dict[str, oasmodel.OASLenientSchema]
SecurityDict = dict[str, oasmodel.OASSecurityScheme | oasmodel.OASReference]
ComponentsDict = dict[str, Any]


class ParamError(Struct):
    name: str
    source: str

    @property
    def source_name(self) -> str:
        return self.source.replace("_", " ").title()


class ResponseError(Struct):
    status: str
    content_type: str


class DefinitionOutput(Struct):
    result: oasmodel.OASSchema
    component: None = None


class ReferenceOutput(Struct):
    result: oasmodel.OASReference
    component: SchemasDict


SchemaOutput = DefinitionOutput | ReferenceOutput
"""When component is not None result contains reference"""

PROBLEM_CONTENTTYPE = "application/problem+json"


class OneOfOutput(Struct):
    oneOf: list[SchemaOutput]


class SchemaGenerationError(LihilError):
    """Base error for OpenAPI schema generation failures."""

    def __init__(
        self,
        message: str,
        *,
        type_hint: Any,
        detail: str,
        endpoint_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.base_message = message
        self.type_hint = self._type_repr(type_hint)
        self.detail = detail
        self.endpoint_name = endpoint_name

    @staticmethod
    def _type_repr(value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return getattr(value, "__name__", None) or repr(value)
        except Exception:  # pragma: no cover - defensive
            return "<unrepresentable>"

    def describe(self) -> tuple[str, str]:
        return ("Schema", self.type_hint)

    def format_context(self, descriptor: str, type_hint: str) -> str:
        if descriptor:
            detail = descriptor
            if type_hint:
                detail += f" [{type_hint}]"
            return f" ({detail})"
        if type_hint:
            return f" [{type_hint}]"
        return ""


class ParamSchemaGenerationError(SchemaGenerationError):
    def __init__(
        self,
        message: str,
        *,
        type_hint: Any,
        detail: str,
        endpoint_name: str | None = None,
        param_error: ParamError,
    ) -> None:
        super().__init__(
            message, type_hint=type_hint, detail=detail, endpoint_name=endpoint_name
        )
        self.param_error: ParamError = param_error

    def describe(self) -> tuple[str, str]:
        source = self.param_error.source
        name = self.param_error.name
        return (f"Param {source} {name}", self.type_hint)

    def format_context(self, descriptor: str, type_hint: str) -> str:
        source_name = self.param_error.source_name
        name = self.param_error.name
        detail = f"{name}: {source_name}"
        if type_hint:
            detail += f"[{type_hint}]"
        return f" ({detail})"


class ResponseGenerationError(SchemaGenerationError):
    def __init__(
        self,
        message: str,
        *,
        type_hint: Any,
        detail: str,
        endpoint_name: str | None = None,
        response_error: ResponseError,
    ) -> None:
        super().__init__(
            message, type_hint=type_hint, detail=detail, endpoint_name=endpoint_name
        )
        self.response_error: ResponseError = response_error

    def describe(self) -> tuple[str, str]:
        status = self.response_error.status
        content_type = self.response_error.content_type
        if content_type:
            return (f"Response {status} {content_type}", self.type_hint)
        return (f"Response {status}", self.type_hint)

    def format_context(self, descriptor: str, type_hint: str | None) -> str:
        status = self.response_error.status
        content_type = self.response_error.content_type
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


class SchemaGenerationAggregateError(LihilError):
    """Aggregated schema generation errors collected across routes and methods."""

    def __init__(
        self, error_map: dict[str, dict[str, list[SchemaGenerationError]]]
    ) -> None:
        # Deep copy simple structures
        self.error_map: dict[str, dict[str, list[SchemaGenerationError]]] = {
            route: {method: list(errs) for method, errs in methods.items()}
            for route, methods in error_map.items()
        }
        super().__init__("Failed to generate OpenAPI schema")

    @property
    def errors(self) -> list[SchemaGenerationError]:
        return [
            error
            for methods in self.error_map.values()
            for errors in methods.values()
            for error in errors
        ]

    def __str__(self) -> str:  # pragma: no cover - formatting helper
        lines = [super().__str__()]
        detail_blocks: list[str] = []
        seen_details: set[str] = set()

        for route_path, methods in self.error_map.items():
            for method, errors in methods.items():
                # Group parameter errors by (endpoint, message, type_hint)
                param_groups: dict[
                    tuple[str, str, str | None], list[ParamSchemaGenerationError]
                ] = {}
                other_errors: list[SchemaGenerationError] = []

                for error in errors:
                    if isinstance(error, ParamSchemaGenerationError):
                        key = (
                            error.endpoint_name or "<unknown-endpoint>",
                            error.base_message,
                            error.type_hint,
                        )
                        param_groups.setdefault(key, []).append(error)
                    else:
                        other_errors.append(error)

                # Emit grouped parameter errors
                for (ep_name, message, type_hint), group in param_groups.items():
                    parts: list[str] = []
                    for err in group:
                        src = err.param_error.source_name
                        name = err.param_error.name
                        detail = f"{name}: {src}"
                        if type_hint:
                            detail += f"[{type_hint}]"
                        parts.append(detail)
                    combined = ", ".join(parts)
                    base_line = f"{method} {route_path} {ep_name}"
                    lines.append(f"- {base_line} ({combined}) - {message}")
                    # attach unique details from the first error in group (others are same root cause)
                    first_detail = (group[0].detail or "").strip()
                    if first_detail and first_detail not in seen_details:
                        seen_details.add(first_detail)
                        detail_blocks.append(first_detail)

                # Emit other errors one-by-one
                for error in other_errors:
                    descriptor, type_hint = error.describe()
                    context = error.format_context(descriptor, type_hint)
                    message = error.base_message
                    ep_display = error.endpoint_name or "<unknown-endpoint>"
                    base_line = f"{method} {route_path} {ep_display}"
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
    try:
        schema, definitions = json_schema(types, schema_hook)
    except TypeError as exc:
        raise SchemaGenerationError(
            f"Unable to build JSON schema from type {types}",
            type_hint=types,
            detail=str(exc),
        ) from exc

    if anyOf := schema.pop("anyOf", None):  # rename
        schema["oneOf"] = anyOf

    if definitions:
        comp_dict = {
            name: oasmodel.OASSchema(**schema) for name, schema in definitions.items()
        }
        return ReferenceOutput(
            cast(oasmodel.OASReference, schema), cast(SchemasDict, comp_dict)
        )
    else:
        return DefinitionOutput(cast(oasmodel.OASSchema, schema))


def type_to_content(
    type_: Any, schemas: SchemasDict, content_type: str = "application/json"
) -> dict[str, oasmodel.OASMediaType]:
    output = oas_schema(type_)
    if output.component:
        schemas.update(output.component)
        media_type = oasmodel.OASMediaType(schema_=output.result)
    else:
        media_type = oasmodel.OASMediaType(schema_=output.result)
    return {content_type: media_type}


def detail_base_to_content(
    err_type: type[DetailBase[Any]] | type[ProblemDetail[Any]],
    problem_content: dict[str, oasmodel.OASMediaType],
    schemas: SchemasDict,
    content_type: str = PROBLEM_CONTENTTYPE,
) -> dict[str, oasmodel.OASMediaType]:
    if not issubclass(err_type, DetailBase):
        return type_to_content(err_type, schemas)

    ref: oasmodel.OASReference | None = None
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
    assert isinstance(problem_schema, oasmodel.OASSchema)

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

    schemas[err_name] = oasmodel.OASSchema(
        type="object",
        properties=properties,
        examples=[example.asdict()],
        description=trimdoc(err_type.__doc__) or f"{err_name}",
        externalDocs=oasmodel.OASExternalDocumentation(
            description=f"Learn more about {err_name}", url=problem_link
        ),
    )

    # Return a reference to this schema
    return {
        content_type: oasmodel.OASMediaType(
            schema_=oasmodel.OASReference(ref=f"#/components/schemas/{err_name}")
        )
    }


def _single_field_schema(
    param: "RequestParam[Any]", schemas: SchemasDict
) -> oasmodel.OASParameter:
    output = oas_schema(param.type_)
    param_schema: dict[str, Any] = {
        "name": param.alias,
        "in_": param.source,
        "required": param.required,
    }
    if output.component:  # reference
        schemas.update(output.component)
    param_schema["schema_"] = output.result
    ps = oasmodel.OASParameter(**param_schema)
    return ps


def param_schema(
    ep_deps: EndpointSignature[Any],
    schemas: SchemasDict,
    endpoint_name: str,
    errors: list[SchemaGenerationError],
) -> list[oasmodel.OASParameter | oasmodel.OASReference]:
    parameters: list[oasmodel.OASParameter | oasmodel.OASReference] = []
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
                errors.append(
                    ParamSchemaGenerationError(
                        exc.base_message,
                        type_hint=exc.type_hint,
                        detail=exc.detail,
                        endpoint_name=endpoint_name,
                        param_error=ParamError(name=p.name, source=p.source),
                    )
                )
                continue
            parameters.append(ps)
    return parameters


def example_from_detail_base(
    err_type: type[DetailBase[Any]], problem_path: str
) -> oasmodel.OASSchema:
    example = err_type.__json_example__()
    err_name = err_type.__name__

    # Create a schema for this specific error type
    problem_type = example.type_
    problem_url = f"{problem_path}/search?{problem_type}"
    error_schema = oasmodel.OASSchema(
        type="object",
        title=err_name,  # Add title to make it show up in Swagger UI
        properties={
            "type": oasmodel.OASSchema(type="string", examples=[example.type_]),
            "title": oasmodel.OASSchema(type="string", examples=[example.title]),
            "status": oasmodel.OASSchema(type="integer", examples=[example.status]),
            "detail": oasmodel.OASSchema(type="string", examples=[example.detail]),
            "instance": oasmodel.OASSchema(type="string", examples=[example.instance]),
        },
        examples=[example.asdict()],
        description=trimdoc(err_type.__doc__) or err_name,
        externalDocs=oasmodel.OASExternalDocumentation(
            description=f"Learn more about {err_name}", url=problem_url
        ),
    )
    return error_schema


def file_body_to_content(
    param: BodyParam[Any, Any], _: SchemasDict
) -> dict[str, oasmodel.OASMediaType]:
    schema = {"type": "string", "format": "binary"}
    # if False: # list[UploadFile], not Implemented
    # schema = {"type": "array", "items": schema}

    schema = {
        "type": "object",
        "properties": {param.name: schema},
        "required": [param.name],
    }
    media_type = oasmodel.OASMediaType(schema_=schema)
    return {"multipart/form-data": media_type}


def body_schema(
    ep_deps: EndpointSignature[Any],
    schemas: SchemasDict,
    endpoint_name: str,
    errors: list[SchemaGenerationError],
) -> oasmodel.OASRequestBody | None:
    if not (body_param := ep_deps.body_param):
        return None
    _, param = body_param
    if is_file_body(param.type_):
        content = file_body_to_content(param, schemas)
    else:
        try:
            content = type_to_content(param.type_, schemas, param.content_type)
        except SchemaGenerationError as exc:
            errors.append(
                ParamSchemaGenerationError(
                    exc.base_message,
                    type_hint=exc.type_hint,
                    detail=exc.detail,
                    endpoint_name=endpoint_name,
                    param_error=ParamError(name=param.name, source="body"),
                )
            )
            return None
    body = oasmodel.OASRequestBody(content=content, required=True)
    return body


def get_err_resp_schemas(ep: Endpoint[Any], schemas: SchemasDict, problem_path: str):
    try:
        problem_content = schemas.get(ProblemDetail.__name__, None) or type_to_content(
            ProblemDetail, schemas
        )
    except SchemaGenerationError as exc:
        raise ResponseGenerationError(
            exc.base_message,
            type_hint=exc.type_hint,
            detail=exc.detail,
            endpoint_name=ep.name,
            response_error=ResponseError(
                status="problem", content_type=PROBLEM_CONTENTTYPE
            ),
        ) from exc
    problem_content = cast(dict[str, oasmodel.OASMediaType], problem_content)

    resps: dict[str, oasmodel.OASResponse] = {}

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
                raise ResponseGenerationError(
                    exc.base_message,
                    type_hint=exc.type_hint,
                    detail=exc.detail,
                    endpoint_name=ep.name,
                    response_error=ResponseError(
                        status=status_str, content_type=PROBLEM_CONTENTTYPE
                    ),
                ) from exc

            # Create link to problem documentation
            resps[status_str] = oasmodel.OASResponse(
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
                        raise ResponseGenerationError(
                            exc.base_message,
                            type_hint=exc.type_hint,
                            detail=exc.detail,
                            endpoint_name=ep.name,
                            response_error=ResponseError(
                                status=status_str, content_type=PROBLEM_CONTENTTYPE
                            ),
                        ) from exc

                # Create a schema with title that references the actual schema
                schema_with_title = oasmodel.OASSchema(
                    title=err_name,
                    allOf=[
                        oasmodel.OASReference(ref=f"#/components/schemas/{err_name}")
                    ],
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

            one_of_schema = oasmodel.OASSchema(
                oneOf=one_of_schemas,
                discriminator=oasmodel.OASDiscriminator(
                    propertyName="type", mapping=error_mapping
                ),
                description=f"chek {problem_path} for further details",
            )

            # Add to responses
            resps[status_str] = oasmodel.OASResponse(
                description=phrase(status_code),
                content={
                    PROBLEM_CONTENTTYPE: oasmodel.OASMediaType(schema_=one_of_schema)
                },
            )

    return resps


def get_resp_schemas(
    ep: Endpoint[Any], schemas: SchemasDict, problem_path: str
) -> dict[str, oasmodel.OASResponse]:
    resps: dict[str, oasmodel.OASResponse] = {
        "200": oasmodel.OASResponse(description="Sucessful Response")
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
                resps[status] = oasmodel.OASResponse(description="No Content")
            else:
                try:
                    content = type_to_content(return_type, schemas, content_type)
                except SchemaGenerationError as exc:
                    raise ResponseGenerationError(
                        exc.base_message,
                        type_hint=exc.type_hint,
                        detail=exc.detail,
                        endpoint_name=ep.name,
                        response_error=ResponseError(
                            status=status, content_type=content_type
                        ),
                    ) from exc
                resp = oasmodel.OASResponse(description=description, content=content)
                resps[status] = resp
    return resps


def generate_param_schema(
    ep_deps: EndpointSignature[Any],
    schemas: SchemasDict,
    endpoint_name: str,
    errors: list[SchemaGenerationError],
):
    params = param_schema(ep_deps, schemas, endpoint_name, errors)
    body = body_schema(ep_deps, schemas, endpoint_name, errors)
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
        security_schemas[scheme_name] = cast(
            oasmodel.OASSecurityScheme, auth_scheme.model
        )
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
) -> tuple[oasmodel.OASOperation | None, list[SchemaGenerationError]]:
    tags = ep.props.tags
    summary = ep.name.replace("_", " ").title()
    description = trimdoc(ep.unwrapped_func.__doc__) or "Missing Description"
    operationId = generate_unique_id(ep)

    ep_errors: list[SchemaGenerationError] = []
    params, body = generate_param_schema(ep.sig, schemas, ep.name, ep_errors)
    if ep_errors:
        return None, ep_errors
    try:
        resps = get_resp_schemas(ep, schemas, problem_path)
        err_resps = get_err_resp_schemas(ep, schemas, problem_path)
    except SchemaGenerationError as exc:
        ep_errors.append(exc)
        return None, ep_errors

    security = get_ep_security(ep, security_schemas)
    resps.update(err_resps)

    op = oasmodel.OASOperation(
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
    return op, []


def get_path_item_from_route(
    route: Route,
    schemas: SchemasDict,
    security_schemas: SecurityDict,
    problem_path: str,
    error_map: dict[str, dict[str, list[SchemaGenerationError]]],
) -> oasmodel.OASPathItem:

    # 1 pathitem = 1 route
    # 1 operation = 1 endpoint

    epoint_ops: dict[str, Any] = {}
    for endpoint in route.endpoints.values():
        if not endpoint.props.in_schema:
            continue
        operation, errs = generate_op_from_ep(
            ep=endpoint,
            schemas=schemas,
            security_schemas=security_schemas,
            problem_path=problem_path,
        )
        if errs:
            methods = error_map.setdefault(route.path, {})
            for e in errs:
                if not e.endpoint_name:
                    e.endpoint_name = endpoint.name
                methods.setdefault(endpoint.method, []).append(e)
            continue
        assert operation is not None
        epoint_ops[endpoint.method.lower()] = operation

    path_item = oasmodel.OASPathItem(**epoint_ops)
    return path_item


class ValidationErrors(Struct):
    location: str
    param_name: str


def generate_oas(
    routes: Sequence[RouteBase],
    oas_config: IOASConfig,
    app_version: str,
) -> oasmodel.OASOpenAPI:
    "Return application/json response"
    paths: dict[str, oasmodel.OASPathItem] = {}
    components: ComponentsDict = {}
    schemas: dict[str, Any] = {}
    security_schemas: SecurityDict = {}
    error_map: dict[str, dict[str, list[SchemaGenerationError]]] = {}

    for route in routes:
        if not isinstance(route, Route) or not route.props.in_schema:
            continue
        path_item = get_path_item_from_route(
            route=route,
            schemas=schemas,
            security_schemas=security_schemas,
            problem_path=oas_config.PROBLEM_PATH,
            error_map=error_map,
        )
        paths[route.path] = path_item

    if error_map:
        raise SchemaGenerationAggregateError(error_map)
    if schemas:
        components["schemas"] = schemas

    if security_schemas:
        components["securitySchemes"] = security_schemas

    comp = oasmodel.OASComponents(**components)
    info = oasmodel.OASInfo(title=oas_config.TITLE, version=app_version)

    oas = oasmodel.OASOpenAPI(
        openapi=oas_config.VERSION,
        info=info,
        paths=paths,
        components=comp,
    )
    return oas
