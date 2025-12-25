import pytest

from lihil.errors import AppConfiguringError
from lihil.lihil import Lihil
from lihil.routing import Route


def test_config_setter_rejects_none():
    app = Lihil()
    with pytest.raises(AppConfiguringError):
        app.config = None


def test_include_routes_warns_and_includes():
    app = Lihil()
    route = Route("/extra")

    with pytest.warns(DeprecationWarning):
        app.include_routes(route)

    assert route in app.routes
