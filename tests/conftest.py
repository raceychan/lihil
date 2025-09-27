"""
Shared pytest fixtures for tests.
"""

from typing import Callable, Generator

import pytest

from lihil import Graph, Lihil
from lihil.signature.parser import EndpointParser
from lihil.vendors import TestClient


@pytest.fixture
def ep_parser() -> EndpointParser:
    return EndpointParser(Graph(), "test")


@pytest.fixture
def test_client() -> Generator[Callable[[Lihil], TestClient], None, None]:
    """Factory fixture returning a Starlette TestClient for a given ASGI app.

    Usage:
        client = test_client(app)
        with client:
            ...
    """

    clients: list[TestClient] = []

    def _factory(app: Lihil) -> TestClient:
        client = TestClient(app)
        clients.append(client)
        return client

    try:
        yield _factory
    finally:
        for c in clients:
            try:
                c.close()
            except Exception:
                pass
