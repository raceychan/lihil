"""
Tests to improve coverage for signature parser dataclass and TypedDict functionality.
"""
import pytest
from dataclasses import dataclass, field
from typing import TypedDict, Optional, Union
from lihil.signature.parser import lexient_get_fields, NODEFAULT


@dataclass
class SampleDataclass:
    """Sample dataclass for coverage."""
    name: str
    age: int
    email: str = "default@example.com"
    active: bool = field(default=True)
    tags: list = field(default_factory=list)


class SampleTypedDict(TypedDict):
    """Sample TypedDict for coverage."""
    name: str
    age: int
    email: str


class SampleOptionalTypedDict(TypedDict, total=False):
    """Sample TypedDict with optional fields."""
    name: str
    age: int
    email: str  # This will be optional


class TestSignatureParserDataclass:
    """Test signature parser with dataclass types."""

    def test_parse_dataclass_fields(self):
        """Test parsing dataclass fields."""
        result = lexient_get_fields(SampleDataclass)

        assert len(result) == 5

        # Check required fields
        name_field = next(f for f in result if f.name == "name")
        assert name_field.type == str
        assert name_field.default == NODEFAULT
        assert name_field.default_factory == NODEFAULT

        age_field = next(f for f in result if f.name == "age")
        assert age_field.type == int
        assert age_field.default == NODEFAULT

        # Check fields with defaults
        email_field = next(f for f in result if f.name == "email")
        assert email_field.type == str
        assert email_field.default == "default@example.com"

        active_field = next(f for f in result if f.name == "active")
        assert active_field.type == bool
        assert active_field.default is True

        # Check field with default_factory
        tags_field = next(f for f in result if f.name == "tags")
        assert tags_field.type == list
        assert tags_field.default == NODEFAULT
        assert callable(tags_field.default_factory)

    def test_parse_dataclass_with_no_defaults(self):
        """Test parsing dataclass with no default values."""
        @dataclass
        class SimpleDataclass:
            name: str
            age: int

        result = lexient_get_fields(SimpleDataclass)

        assert len(result) == 2

        for field_info in result:
            assert field_info.default == NODEFAULT
            assert field_info.default_factory == NODEFAULT


class TestSignatureParserTypedDict:
    """Test signature parser with TypedDict types."""

    def test_parse_typeddict_fields(self):
        """Test parsing TypedDict fields."""
        result = lexient_get_fields(SampleTypedDict)

        assert len(result) == 3

        # All fields should be required (no defaults)
        for field_info in result:
            assert field_info.default == NODEFAULT
            assert field_info.default_factory == NODEFAULT

        # Check field types
        name_field = next(f for f in result if f.name == "name")
        assert name_field.type == str

        age_field = next(f for f in result if f.name == "age")
        assert age_field.type == int

        email_field = next(f for f in result if f.name == "email")
        assert email_field.type == str

    def test_parse_typeddict_with_optional_fields(self):
        """Test parsing TypedDict with optional fields."""
        result = lexient_get_fields(SampleOptionalTypedDict)

        assert len(result) == 3

        # All fields should have None as default since total=False
        for field_info in result:
            assert field_info.default is None
            # Type should be Union with None
            assert hasattr(field_info.type, '__origin__')  # Union type

    def test_parse_typeddict_mixed_required_optional(self):
        """Test parsing TypedDict with mixed required/optional fields."""
        class MixedTypedDict(TypedDict, total=False):
            name: str
            age: int

        # Add some required keys
        MixedTypedDict.__required_keys__ = frozenset(["name"])
        MixedTypedDict.__optional_keys__ = frozenset(["age"])

        result = lexient_get_fields(MixedTypedDict)

        assert len(result) == 2

        name_field = next(f for f in result if f.name == "name")
        age_field = next(f for f in result if f.name == "age")

        # name should be required (no default)
        assert name_field.default == NODEFAULT

        # age should be optional (default None)
        assert age_field.default is None


class TestSignatureParserComplexTypes:
    """Test signature parser with complex nested types."""

    def test_parse_nested_dataclass(self):
        """Test parsing nested dataclass structures."""
        @dataclass
        class Address:
            street: str
            city: str

        @dataclass
        class Person:
            name: str
            address: Address

        result = lexient_get_fields(Person)

        assert len(result) == 2

        name_field = next(f for f in result if f.name == "name")
        assert name_field.type == str

        address_field = next(f for f in result if f.name == "address")
        assert address_field.type == Address

    def test_parse_dataclass_with_complex_defaults(self):
        """Test parsing dataclass with complex default values."""
        @dataclass
        class ComplexDataclass:
            name: str
            metadata: dict = field(default_factory=dict)
            options: Optional[list] = None

        result = lexient_get_fields(ComplexDataclass)

        assert len(result) == 3

        name_field = next(f for f in result if f.name == "name")
        assert name_field.default == NODEFAULT

        metadata_field = next(f for f in result if f.name == "metadata")
        assert metadata_field.default == NODEFAULT
        assert callable(metadata_field.default_factory)

        options_field = next(f for f in result if f.name == "options")
        assert options_field.default is None

    def test_parse_typeddict_with_complex_types(self):
        """Test parsing TypedDict with complex field types."""
        class ComplexTypedDict(TypedDict):
            name: str
            tags: list[str]
            metadata: dict[str, int]

        result = lexient_get_fields(ComplexTypedDict)

        assert len(result) == 3

        # Verify types are preserved
        tags_field = next(f for f in result if f.name == "tags")
        metadata_field = next(f for f in result if f.name == "metadata")

        # These should maintain their complex types
        assert tags_field.type == list[str]
        assert metadata_field.type == dict[str, int]
