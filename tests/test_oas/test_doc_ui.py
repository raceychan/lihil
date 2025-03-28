import pytest

from lihil.oas.doc_ui import (
    get_problem_ui_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)


def test_swagger_ui():
    get_swagger_ui_html(
        openapi_url="1",
        title="2",
        swagger_js_url="1",
        swagger_css_url="2",
        swagger_ui_parameters=dict(param=2),
        oauth2_redirect_url="4",
        init_oauth=dict(a=b"4"),
    )


def test_get_swagger_ui_oauth2_redirect_html():
    assert get_swagger_ui_oauth2_redirect_html()


def test_get_problem_ui_html():
    get_problem_ui_html(
        title="test", problems={}, problem_ui_parameters={"test": "test"}
    )
