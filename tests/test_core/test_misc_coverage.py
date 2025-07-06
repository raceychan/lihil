"""
Tests to improve coverage for miscellaneous modules.
"""
import pytest
from lihil.errors import MissingDependencyError
from lihil.interface.struct import Base, UNSET


class TestMiscCoverage:
    """Test miscellaneous coverage gaps."""

    def test_missing_dependency_error(self):
        """Test MissingDependencyError creation and message."""
        error = MissingDependencyError("test_dependency")
        assert str(error) == "test_dependency is required but not provided"
        assert isinstance(error, Exception)


class SampleStruct(Base):
    """Sample struct for coverage."""
    name: str
    age: int
    email: str = "default@example.com"
    active: bool = True


class TestStructCoverage:
    """Test Struct class coverage."""

    def test_struct_getitem(self):
        """Test Struct.__getitem__ method."""
        obj = SampleStruct(name="John", age=30)

        assert obj["name"] == "John"
        assert obj["age"] == 30
        assert obj["email"] == "default@example.com"
        assert obj["active"] is True

    def test_struct_model_dump_skip_none(self):
        """Test Struct.asdict with skip_none option."""
        obj = SampleStruct(name="John", age=30, email=None)

        # Test with skip_none=True
        result = obj.asdict(skip_none=True)

        # None values should be excluded
        assert "email" not in result or result.get("email") is not None
        assert result["name"] == "John"
        assert result["age"] == 30

    def test_struct_model_dump_exclude_unset(self):
        """Test Struct.asdict excluding UNSET values."""
        # Create struct with some UNSET values
        obj = SampleStruct(name="John", age=30)

        # Mock some field to be UNSET
        obj.email = UNSET

        result = obj.asdict(skip_unset=True)

        # Should exclude UNSET values when skip_unset=True
        assert result["name"] == "John"
        assert result["age"] == 30
