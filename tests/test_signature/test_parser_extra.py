from dataclasses import dataclass

import pytest
from msgspec import Struct

from ididi.errors import UnsolvableNodeError

from lihil.errors import InvalidParamError, NotSupportedError
from lihil.interface import MISSING
from lihil.signature.parser import (
    EndpointParser,
    formdecoder_factory,
    lexient_get_fields,
    req_param_factory,
)
from lihil.signature.params import EndpointParams, Form
from lihil.vendors import UploadFile


def test_lexient_get_fields_rejects_unsupported_type():
    with pytest.raises(TypeError):
        lexient_get_fields(int)


def test_formdecoder_factory_sequence_requires_structured_type():
    with pytest.raises(InvalidParamError):
        formdecoder_factory(list[int])


def test_formdecoder_factory_union_of_structured_types_not_supported():
    @dataclass
    class A:
        a: int

    @dataclass
    class B:
        b: int

    with pytest.raises(InvalidParamError):
        formdecoder_factory(A | B)


def test_req_param_factory_path_structured_rejected():
    class Payload(Struct):
        x: int

    with pytest.raises(InvalidParamError):
        req_param_factory(
            name="p", alias="p", param_type=Payload, annotation=Payload, default=MISSING, source="path"
        )


def test_req_param_factory_prefers_explicit_decoder():
    decoder_called = {}

    def dec(val):
        decoder_called["val"] = val
        return val

    param = req_param_factory(
        name="q", alias="q", param_type=int, annotation=int, default=MISSING, decoder=dec, source="query"
    )

    assert param.decoder is dec


def test_parse_body_rejects_uploadfile_list():
    parser = EndpointParser(graph=None, route_path="/")
    form_meta = Form()

    with pytest.raises(NotSupportedError):
        parser._parse_body(
            name="files",
            param_alias="files",
            type_=list[UploadFile],
            annotation=list[UploadFile],
            default=MISSING,
            param_meta=form_meta,
        )


def test_parse_raises_on_unsolvable_node(monkeypatch):
    class DummyNode:
        dependent = "dep"

    class DummyGraph:
        def should_be_scoped(self, dep):
            raise UnsolvableNodeError("fail")

    class DummyParser(EndpointParser):
        def parse_params(self, _):
            return EndpointParams(params={}, bodies={}, nodes={"d": DummyNode()}, plugins={})

    parser = DummyParser(DummyGraph(), "/route")

    def endpoint():
        return None

    with pytest.raises(InvalidParamError):
        parser.parse(endpoint)
