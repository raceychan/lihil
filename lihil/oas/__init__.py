"""
OAS stands for `OpenAPI Specification`

https://swagger.io/docs/specification/v3_0/about/
"""

from typing import Any

from lihil.config.app_config import IOASConfig
from lihil.interface.problem import DetailBase
from lihil.routing import Route, RouteBase
from lihil.utils.json import encoder_factory
from lihil.vendors import Response

from .doc_ui import get_problem_ui_html, get_swagger_ui_html
from .model import OpenAPI
from .schema import generate_oas


def get_openapi_route(
    routes: list[RouteBase], oas_config: IOASConfig, app_version: str
) -> Route:
    oas: OpenAPI | None = None
    encoder = encoder_factory(t=OpenAPI)

    async def openapi():
        nonlocal oas
        if oas is None:
            oas = generate_oas(routes, oas_config, app_version)
        return Response(encoder(oas), media_type="application/json")

    openapi_route = Route(oas_config.OAS_PATH, in_schema=False)
    openapi_route.get(openapi)
    return openapi_route


def get_doc_route(oas_config: IOASConfig) -> Route:
    oas_path = oas_config.OAS_PATH
    docs_path = oas_config.DOC_PATH

    async def swagger():
        return get_swagger_ui_html(openapi_url=oas_path, title=oas_config.TITLE)

    doc_route = Route(docs_path, in_schema=False)
    doc_route.get(swagger)
    return doc_route


def get_problem_route(
    oas_config: IOASConfig, problems: list[type[DetailBase[Any]]]
) -> Route:
    problem_path = oas_config.PROBLEM_PATH

    async def problem_detail():
        return get_problem_ui_html(title=oas_config.PROBLEM_TITLE, problems=problems)

    problem_route = Route(problem_path, in_schema=False)
    problem_route.get(problem_detail)
    return problem_route
