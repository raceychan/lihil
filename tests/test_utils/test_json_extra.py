import pytest
from pytest import importorskip

importorskip("pydantic")
pytestmark = pytest.mark.requires_pydantic

import math

from pydantic import BaseModel

from lihil.utils.json import is_json_compatible, json_schema


def test_json_schema_uses_schema_generator_when_present():
    calls: list[object] = []

    class PModel(BaseModel):
        x: int

        @classmethod
        def model_json_schema(cls, *, ref_template=None, schema_generator=None):
            calls.append(schema_generator)
            return {"type": "object", "properties": {"x": {"type": "integer"}}, "$defs": {}}

    schema, defs = json_schema(PModel, schema_generator="GEN")

    assert schema["properties"]["x"]["type"] == "integer"
    assert defs == {}
    assert calls[-1] == "GEN"


def test_is_json_compatible_branch_coverage():
    assert is_json_compatible(None)
    assert is_json_compatible("ok")
    assert not is_json_compatible(float("nan"))
    assert not is_json_compatible(float("inf"))
    assert is_json_compatible([1, 2, 3])
    assert not is_json_compatible([1, math.nan])
    assert is_json_compatible((1, 2))
    assert not is_json_compatible({1: "a"})
    assert is_json_compatible({"a": {"b": 2}})
    assert not is_json_compatible(set([1, 2]))
