"""
OAS stands for `OpenAPI Specification`

https://swagger.io/docs/specification/v3_0/about/
"""

from typing import Any

from lihil.config import OASConfig
from lihil.problems import DetailBase
from lihil.routing import Route, RouteConfig
from lihil.utils.phasing import encode_json
from lihil.vendor_types import Response

from .doc_ui import get_problem_ui_html, get_swagger_ui_html
from .schema import generate_oas


def get_openapi_route(
    oas_config: OASConfig, routes: list[Route], app_version: str
) -> Route:
    oas_path = oas_config.oas_path

    async def openapi():
        content = generate_oas(routes, oas_config, app_version)
        return Response(encode_json(content), media_type="application/json")

    openapi_route = Route(oas_path, route_config=RouteConfig(in_schema=False))
    openapi_route.get(openapi)
    return openapi_route


def get_doc_route(oas_config: OASConfig) -> Route:
    oas_path = oas_config.oas_path
    docs_path = oas_config.doc_path

    async def swagger():
        return get_swagger_ui_html(openapi_url=oas_path, title=oas_config.title)

    doc_route = Route(docs_path, route_config=RouteConfig(in_schema=False))
    doc_route.get(swagger)
    return doc_route


def get_problem_route(
    oas_config: OASConfig, problems: list[type[DetailBase[Any]]]
) -> Route:
    problem_path = oas_config.problem_path

    async def problem_detail():
        return get_problem_ui_html(title="API Problem Details", problems=problems)

    problem_route = Route(problem_path, route_config=RouteConfig(in_schema=False))
    problem_route.get(problem_detail)
    return problem_route
