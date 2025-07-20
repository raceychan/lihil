"""
Tests to verify that dependency injection has higher priority than body param parsing.

When an object is registered in the Dependency Graph, it should be parsed as a dependency
before being considered as a body param, even if it's a structured type that could normally
be used as a body parameter (e.g., Payload, Struct, dataclass).
"""

import pytest
from dataclasses import dataclass
from typing import Annotated

from ididi import Graph
from msgspec import Struct

from lihil import Payload
from lihil.signature.parser import BodyParam, DependentNode, EndpointParser


class ConfigPayload(Payload):
    """A structured type that could be both a dependency and body param."""
    database_url: str
    debug_mode: bool = False


class ConfigStruct(Struct):
    """A msgspec Struct that could be both a dependency and body param."""
    api_key: str
    timeout: int = 30


@dataclass
class ConfigDataclass:
    """A dataclass that could be both a dependency and body param."""
    host: str
    port: int = 8080


class TestDependencyPriority:
    """Test that dependency parsing has higher priority than body param parsing."""

    @pytest.fixture
    def empty_parser(self) -> EndpointParser:
        """Parser with empty dependency graph."""
        return EndpointParser(Graph(), "/test")

    @pytest.fixture
    def parser_with_payload_dep(self) -> EndpointParser:
        """Parser with ConfigPayload registered as dependency."""
        graph = Graph()
        graph.node(ConfigPayload)
        return EndpointParser(graph, "/test")

    @pytest.fixture
    def parser_with_struct_dep(self) -> EndpointParser:
        """Parser with ConfigStruct registered as dependency."""
        graph = Graph()
        graph.node(ConfigStruct)
        return EndpointParser(graph, "/test")

    @pytest.fixture
    def parser_with_dataclass_dep(self) -> EndpointParser:
        """Parser with ConfigDataclass registered as dependency."""
        graph = Graph()
        graph.node(ConfigDataclass)
        return EndpointParser(graph, "/test")

    def test_payload_without_dependency_becomes_body_param(self, empty_parser: EndpointParser):
        """When Payload is not in dependency graph, it should be parsed as body param."""
        result = empty_parser.parse_param("config", ConfigPayload)

        assert len(result) == 1
        param = result[0]
        assert isinstance(param, BodyParam)
        assert param.type_ == ConfigPayload
        assert param.name == "config"

    def test_payload_with_dependency_becomes_dependency_param(self, parser_with_payload_dep: EndpointParser):
        """When Payload is in dependency graph, it should be parsed as dependency."""
        result = parser_with_payload_dep.parse_param("config", ConfigPayload)

        # Should return dependency node and any sub-dependencies
        assert len(result) >= 1
        assert isinstance(result[0], DependentNode)
        assert result[0].dependent == ConfigPayload

    def test_struct_without_dependency_becomes_body_param(self, empty_parser: EndpointParser):
        """When Struct is not in dependency graph, it should be parsed as body param."""
        result = empty_parser.parse_param("config", ConfigStruct)

        assert len(result) == 1
        param = result[0]
        assert isinstance(param, BodyParam)
        assert param.type_ == ConfigStruct
        assert param.name == "config"

    def test_struct_with_dependency_becomes_dependency_param(self, parser_with_struct_dep: EndpointParser):
        """When Struct is in dependency graph, it should be parsed as dependency."""
        result = parser_with_struct_dep.parse_param("config", ConfigStruct)

        # Should return dependency node and any sub-dependencies
        assert len(result) >= 1
        assert isinstance(result[0], DependentNode)
        assert result[0].dependent == ConfigStruct

    def test_dataclass_without_dependency_becomes_body_param(self, empty_parser: EndpointParser):
        """When dataclass is not in dependency graph, it should be parsed as body param."""
        result = empty_parser.parse_param("config", ConfigDataclass)

        assert len(result) == 1
        param = result[0]
        assert isinstance(param, BodyParam)
        assert param.type_ == ConfigDataclass
        assert param.name == "config"

    def test_dataclass_with_dependency_becomes_dependency_param(self, parser_with_dataclass_dep: EndpointParser):
        """When dataclass is in dependency graph, it should be parsed as dependency."""
        result = parser_with_dataclass_dep.parse_param("config", ConfigDataclass)

        # Should return dependency node and any sub-dependencies
        assert len(result) >= 1
        assert isinstance(result[0], DependentNode)
        assert result[0].dependent == ConfigDataclass

    def test_endpoint_signature_with_dependency_priority(self, parser_with_payload_dep: EndpointParser):
        """Test full endpoint parsing with dependency priority."""

        def endpoint_with_config(config: ConfigPayload, data: dict[str, str]):
            """Endpoint that expects config as dependency and data as body."""
            return {"config": config, "data": data}

        signature = parser_with_payload_dep.parse(endpoint_with_config)

        # config should be in dependencies, not body
        assert "config" in signature.dependencies
        assert isinstance(signature.dependencies["config"], DependentNode)
        assert signature.dependencies["config"].dependent == ConfigPayload

        # data should be body param
        assert signature.body_param is not None
        body_name, body_param = signature.body_param
        assert body_name == "data"
        assert body_param.type_ == dict[str, str]

    def test_multiple_structured_types_priority(self):
        """Test multiple structured types with mixed dependency registration."""
        graph = Graph()
        graph.node(ConfigPayload)  # Only ConfigPayload is registered as dependency
        parser = EndpointParser(graph, "/test")

        def endpoint(
            config: ConfigPayload,  # Should be dependency
            settings: ConfigStruct,  # Should be body param
        ):
            return {"config": config, "settings": settings}

        signature = parser.parse(endpoint)

        # config should be dependency
        assert "config" in signature.dependencies
        assert isinstance(signature.dependencies["config"], DependentNode)

        # settings should be body param since it's not in dependency graph
        assert signature.body_param is not None
        body_name, body_param = signature.body_param
        assert body_name == "settings"
        assert body_param.type_ == ConfigStruct

    def test_annotated_dependency_priority(self, parser_with_payload_dep: EndpointParser):
        """Test that explicit body annotation takes precedence over dependency detection."""
        from lihil import Param

        # When explicitly annotated as body, it should be body param even if in dependency graph
        result = parser_with_payload_dep.parse_param(
            "config",
            Annotated[ConfigPayload, Param("body")]
        )

        # Should be body param because explicit annotation takes precedence
        assert len(result) == 1
        assert isinstance(result[0], BodyParam)
        assert result[0].type_ == ConfigPayload

        # But without explicit annotation, it should be dependency
        result_no_annotation = parser_with_payload_dep.parse_param("config", ConfigPayload)
        assert len(result_no_annotation) >= 1
        assert isinstance(result_no_annotation[0], DependentNode)
        assert result_no_annotation[0].dependent == ConfigPayload

    def test_dependency_with_subdependencies(self):
        """Test dependency priority with nested dependencies."""

        class DatabaseService:
            def __init__(self, config: ConfigPayload):
                self.config = config

        graph = Graph()
        graph.node(ConfigPayload)
        graph.node(DatabaseService)
        parser = EndpointParser(graph, "/test")

        result = parser.parse_param("db_service", DatabaseService)

        # Should return multiple items: the service itself and its dependencies
        assert len(result) >= 1
        assert isinstance(result[0], DependentNode)
        assert result[0].dependent == DatabaseService

        # ConfigPayload should also be included as a transitive dependency
        # The exact structure depends on the dependency resolution implementation
