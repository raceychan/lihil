import importlib
import sys

from lihil.lihil import Lihil
from lihil.routing import Route


async def test_lihil_init_with_root_route():
    """Cover branch where a root Route is passed into Lihil constructor."""
    root = Route("/")

    async def root_handler():
        return {"message": "ok"}

    root.get(root_handler)

    app = Lihil(root)

    # Ensure root was set and included
    assert app.root is root
    assert any(r is root for r in app.routes)


def test_lihil_run_default_runner(monkeypatch):
    """Cover default runner import path by stubbing out uvicorn.run."""
    # Make sure uvicorn import path resolves to our stub
    class FakeUvicorn:
        def __init__(self):
            self.called = False

        def run(self, app, **kwargs):  # type: ignore[no-redef]
            self.called = True
            # app passed directly when not using app string
            assert isinstance(app, Lihil)

    fake = FakeUvicorn()
    monkeypatch.setitem(sys.modules, "uvicorn", fake)

    app = Lihil()

    # Call with no explicit runner to hit the "from uvicorn import run" path
    app.run(__file__)
