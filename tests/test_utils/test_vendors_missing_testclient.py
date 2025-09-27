import importlib
import sys


def test_vendors_handles_missing_testclient(monkeypatch):
    """Force-import lihil.vendors with starlette.testclient missing to cover fallback."""
    # Ensure a clean import
    sys.modules.pop("lihil.vendors", None)

    # Simulate missing starlette.testclient
    monkeypatch.setitem(sys.modules, "starlette.testclient", None)

    # Import and reload to trigger the try/except path
    import lihil.vendors as vendors

    importlib.reload(vendors)

    # Module should import successfully even without TestClient
    assert vendors is not None
