"""
TODO: make some really nasty endpoints here
"""

import pytest

from lihil import Graph
from lihil.signature.parser import EndpointParser


@pytest.fixture
def ep_parser() -> EndpointParser:
    return EndpointParser(Graph(), "test")
