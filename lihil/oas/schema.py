import re
from types import UnionType
from typing import Any, Sequence, cast, get_args

from msgspec import Struct
from msgspec.json import schema_components

from lihil.config import OASConfig
from lihil.constant.status import phrase
from lihil.di import EndpointDeps, RequestParam
from lihil.interface import is_provided
from lihil.oas import model as oasmodel
from lihil.problems import DetailBase, InvalidRequestErrors, ProblemDetail
from lihil.routing import Endpoint, Route
from lihil.utils.parse import to_kebab_case, trimdoc

# from lihil.utils.phasing import encode_json

type SchemasDict = dict[str, oasmodel.LenientSchema]
type ComponentsDict = dict[str, Any]


class DefinitionOutput(Struct):
    result: oasmodel.Schema
    component: None = None


class ReferenceOutput(Struct):
    result: oasmodel.Reference
    component: SchemasDict


type SchemaOutput = DefinitionOutput | ReferenceOutput
"""When component is not None result contains reference"""

PROBLEM_CONTENTTYPE = "application/problem+json"


class OneOfOutput(Struct):
    oneOf: list[SchemaOutput]


def json_schema(types: type | UnionType) -> SchemaOutput:
    (schema,), definitions = schema_components(
        (types,),
        ref_template="#/components/schemas/{name}",
    )

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
    output = json_schema(type_)
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
            output = json_schema(var)
            output = cast(ReferenceOutput, output)
            ref = output.result
            schemas.update(output.component)
            break

    pb_name = ProblemDetail.__name__
    err_name = err_type.__name__

    # Get the problem schema from schemas
    problem_schema = schemas.get(pb_name)
    if not problem_schema:
        raise ValueError(f"Schema for {pb_name} not found in schemas")

    example = err_type.__json_example__()

    # Create a new schema for this specific error type
    if isinstance(problem_schema, oasmodel.Schema):
        # Clone the problem schema properties
        assert problem_schema.properties
        properties = problem_schema.properties.copy()

        if ref is not None:
            properties["detail"] = ref
        # Add a link to the problems page for this error type
        problem_link = f"/problems?search={example["type_"]}"
        schemas[err_name] = oasmodel.Schema(
            type="object",
            properties=properties,
            examples=[example],
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
    else:
        return problem_content


def _single_field_schema(
    param: RequestParam[Any], schemas: SchemasDict
) -> oasmodel.Parameter:
    output = json_schema(param.type_)
    param_schema: dict[str, Any] = {
        "name": param.alias,
        "in_": param.location,
        "required": True,
    }
    if output.component:  # reference
        schemas.update(output.component)
    param_schema["schema_"] = output.result
    ps = oasmodel.Parameter(**param_schema)
    return ps


def param_schema(
    ep_deps: EndpointDeps[Any], schemas: SchemasDict
) -> list[oasmodel.Parameter | oasmodel.Reference]:
    parameters: list[oasmodel.Parameter | oasmodel.Reference] = []

    for group in (ep_deps.query_params, ep_deps.path_params, ep_deps.header_params):
        for _, p in group:
            ps = _single_field_schema(p, schemas)
            parameters.append(ps)
    return parameters


def example_from_detail_base(
    err_type: type[DetailBase[Any]], problem_path: str
) -> oasmodel.Schema:
    example = err_type.__json_example__()
    err_name = err_type.__name__

    # Create a schema for this specific error type
    problem_url = f"{problem_path}/search?{example["type_"]}"
    error_schema = oasmodel.Schema(
        type="object",
        title=err_name,  # Add title to make it show up in Swagger UI
        properties={
            "type": oasmodel.Schema(type="string", examples=[example["type_"]]),
            "title": oasmodel.Schema(type="string", examples=[example["title"]]),
            "status": oasmodel.Schema(type="integer", examples=[example["status"]]),
            "detail": oasmodel.Schema(type="string", examples=["Example detail"]),
            "instance": oasmodel.Schema(type="string", examples=["Example instance"]),
        },
        examples=[example],
        description=trimdoc(err_type.__doc__) or err_name,
        externalDocs=oasmodel.ExternalDocumentation(
            description=f"Learn more about {err_name}", url=problem_url
        ),
    )
    return error_schema


def body_schema(
    ep_deps: EndpointDeps[Any], schemas: SchemasDict
) -> oasmodel.RequestBody | None:
    if not (body_param := ep_deps.body_param):
        return None
    _, param = body_param
    content = type_to_content(param.type_, schemas)
    body = oasmodel.RequestBody(content=content, required=True)
    return body


def err_resp_schema(ep: Endpoint[Any], schemas: SchemasDict, problem_path: str):
    problem_content = schemas.get(ProblemDetail.__name__, None) or type_to_content(
        ProblemDetail, schemas
    )
    problem_content = cast(dict[str, oasmodel.MediaType], problem_content)

    resps: dict[str, oasmodel.Response] = {}

    if user_provid_errors := ep.config.errors:
        errors = user_provid_errors + (InvalidRequestErrors,)
    else:
        errors = (InvalidRequestErrors,)

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
            content = detail_base_to_content(err_type, problem_content, schemas)

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
                    content = detail_base_to_content(err_type, problem_content, schemas)

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


def resp_schema(
    ep: Endpoint[Any], schemas: SchemasDict, problem_path: str
) -> dict[str, oasmodel.Response]:
    ep_return = ep.deps.return_param
    content_type = ep_return.content_type
    return_type = ep_return.type_

    resps: dict[str, oasmodel.Response] = {
        "200": oasmodel.Response(description="Sucessful Response")
    }

    if is_provided(return_type):
        if isinstance(return_type, UnionType):
            """
            TODO: handle union Resp
            def create_user() -> Resp[User, 200] | Resp[UserNotFound, 404]
            """
            pass
        content = type_to_content(return_type, schemas, content_type)
        resp = oasmodel.Response(description="Successful Response", content=content)
        resps[str(ep_return.status)] = resp

    err_resps = err_resp_schema(ep, schemas, problem_path)
    resps.update(err_resps)
    return resps


def generate_param_schema(ep_deps: EndpointDeps[Any], schemas: SchemasDict):
    params = param_schema(ep_deps, schemas)
    body = body_schema(ep_deps, schemas)
    return params, body


def generate_unique_id(ep: Endpoint[Any]) -> str:
    operation_id = f"{ep.name}{ep.path}"
    operation_id = re.sub(r"\W", "_", operation_id)
    operation_id = f"{operation_id}_{ep.method.lower()}"
    return operation_id


def generate_op_from_ep(
    ep: Endpoint[Any], schemas: SchemasDict, problem_path: str
) -> oasmodel.Operation:
    tags = [ep.tag] if ep.tag else ["root"]
    summary = ep.name.replace("_", " ").title()
    description = trimdoc(ep.func.__doc__) or "Missing Description"
    operationId = generate_unique_id(ep)
    params, body = generate_param_schema(ep.deps, schemas)

    resps = resp_schema(ep, schemas, problem_path)

    op = oasmodel.Operation(
        tags=tags,
        summary=summary,
        description=description,
        operationId=operationId,
        parameters=params,
        requestBody=body,
    )
    for status, resp in resps.items():
        op.responses[status] = resp
    return op


def path_item_from_route(
    route: Route, schemas: SchemasDict, problem_path: str
) -> oasmodel.PathItem:
    epoint_ops: dict[str, Any] = {}
    for endpoint in route.endpoints.values():
        if not endpoint.config.in_schema:
            continue
        operation = generate_op_from_ep(endpoint, schemas, problem_path)
        epoint_ops[endpoint.method.lower()] = operation

    path_item = oasmodel.PathItem(**epoint_ops)
    return path_item


class ValidationErrors(Struct):
    location: str
    param_name: str


def generate_oas(
    routes: Sequence[Route],
    oas_config: OASConfig,
    app_version: str,
) -> oasmodel.OpenAPI:
    "Return application/json response"
    paths: dict[str, oasmodel.PathItem] = {}

    components: ComponentsDict = {}
    components["schemas"] = schemas = {}
    schemas: dict[str, Any]

    for route in routes:
        if not route.config.in_schema:
            continue
        paths[route.path] = path_item_from_route(
            route, schemas, oas_config.problem_path
        )

    icom = oasmodel.Components(**components)
    info = oasmodel.Info(title=oas_config.title, version=app_version)

    oas = oasmodel.OpenAPI(
        openapi=oas_config.version,
        info=info,
        paths=paths,
        components=icom,
    )
    return oas
