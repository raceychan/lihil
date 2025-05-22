import argparse
import tempfile
from typing import Optional, Union

import pytest
from msgspec.structs import FieldInfo

from lihil import Request
from lihil.config import (
    DEFAULT_CONFIG,
    AppConfig,
    ConfigLoader,
    lhl_get_config,
    lhl_set_config,
)
from lihil.config.loader import deep_update, load_from_cli
from lihil.config.parser import (
    ConfigBase,
    StoreTrueIfProvided,
    build_parser,
    format_nested_dict,
    generate_parser_actions,
    parse_field_type,
)
from lihil.errors import AppConfiguringError
from lihil.interface import MISSING, Maybe, is_provided
from lihil.plugins.bus import EventBus
from lihil.signature.parser import is_lhl_primitive


def test_format_nested_dict():
    """Test conversion of flat dict with dot notation to nested dict"""
    flat_dict = {
        "simple": "value",
        "oas.title": "API Docs",
        "server.host": "localhost",
        "server.port": 8000,
        "a.b.c.d": "nested",
    }

    result = format_nested_dict(flat_dict)

    assert result["simple"] == "value"
    assert result["oas"]["title"] == "API Docs"
    assert result["server"]["host"] == "localhost"
    assert result["server"]["port"] == 8000
    assert result["a"]["b"]["c"]["d"] == "nested"


def test_deep_update():
    """Test recursive update of nested dictionaries"""
    original = {"a": 1, "b": {"c": 2, "d": 3}, "e": {"f": 4}}

    update_data = {"a": 10, "b": {"c": 20}, "g": 5}

    result = deep_update(original, update_data)

    assert result["a"] == 10
    assert result["b"]["c"] == 20
    assert result["b"]["d"] == 3  # Unchanged
    assert result["e"]["f"] == 4  # Unchanged
    assert result["g"] == 5  # New key


def test_store_true_if_provided():
    """Test the StoreTrueIfProvided action"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--flag", action=StoreTrueIfProvided)

    # Test when flag is provided
    args = parser.parse_args(["--flag"])
    assert args.flag is True
    assert getattr(args, "flag_provided", False) is True

    # Test when flag is not provided
    args = parser.parse_args([])
    assert args.flag is MISSING
    assert getattr(args, "flag_provided", False) is False


def test_is_lhl_dep():
    """Test identification of lihil dependencies"""
    assert is_lhl_primitive(Request) is True
    assert is_lhl_primitive(EventBus) is False
    assert is_lhl_primitive(str) is False
    assert is_lhl_primitive(int) is False
    assert is_lhl_primitive(AppConfig) is False


def test_parse_field_type():
    """Test parsing field types including Optional types"""
    from msgspec.structs import fields as msgspec_fields

    class TestStruct(ConfigBase):
        regular: int = 0
        optional: Optional[str] = None
        union: Union[int, str] = 1

    # Get field information using msgspec's introspection
    fields = msgspec_fields(TestStruct)

    regular_field = next(f for f in fields if f.name == "regular")
    optional_field = next(f for f in fields if f.name == "optional")
    union_field = next(f for f in fields if f.name == "union")

    # Regular type
    assert parse_field_type(regular_field).field_type == int

    # Optional type should return the non-None type
    assert parse_field_type(optional_field).field_type == str

    # Union type should return the first non-None type
    # Note: behavior depends on the order of types in the Union
    result = parse_field_type(union_field)
    assert result.field_type in (int, str)


def test_build_parser():
    """Test building an argument parser from a config type"""
    parser = build_parser(AppConfig)

    # Check that basic arguments are added
    actions = {action.dest: action for action in parser._actions}

    assert "IS_PROD" in actions
    assert "VERSION" in actions

    # Check nested config arguments
    assert "oas.TITLE" in actions
    assert "server.HOST" in actions
    assert "server.PORT" in actions


def test_load_config_toml():
    """Test loading config from a TOML file"""
    with tempfile.NamedTemporaryFile(suffix=".toml", mode="w+") as tmp:
        tmp.write(
            """
        [lihil]
        IS_PROD = true
        VERSION = "1.0.0"

        [lihil.oas]
        TITLE = "Test API"

        [lihil.server]
        HOST = "127.0.0.1"
        PORT = 9000
        """
        )
        tmp.flush()

        config = ConfigLoader().load_config(tmp.name)

        assert config.IS_PROD is True
        assert config.VERSION == "1.0.0"
        assert config.oas.TITLE == "Test API"
        assert config.server.HOST == "127.0.0.1"
        assert config.server.PORT == 9000


def test_load_config_toml_alternative_format():
    """Test loading config from a TOML file with alternative format"""
    with tempfile.NamedTemporaryFile(suffix=".toml", mode="w+") as tmp:
        tmp.write(
            """
        [lihil]
        IS_PROD = true
        VERSION = "1.0.0"

        [lihil.oas]
        TITLE = "Test API"
        """
        )
        tmp.flush()

        config = ConfigLoader().load_config(tmp.name)

        assert config.IS_PROD is True
        assert config.VERSION == "1.0.0"
        assert config.oas.TITLE == "Test API"


def test_load_config_nonexistent():
    """Test error when config file doesn't exist"""
    with pytest.raises(AppConfiguringError, match="not exist"):
        ConfigLoader().load_config("nonexistent_file.toml")


def test_load_config_unsupported_format():
    """Test error when config file has unsupported format"""
    with tempfile.NamedTemporaryFile(suffix=".xyz") as tmp:
        with pytest.raises(AppConfiguringError, match="Loader for .xyz is not found"):
            ConfigLoader().load_config(tmp.name)


def test_load_config_missing_table():
    """Test error when TOML file doesn't have lihil table"""
    with tempfile.NamedTemporaryFile(suffix=".toml", mode="w+") as tmp:
        tmp.write(
            """
        [some_other_tool]
        option = "value"
        """
        )
        tmp.flush()

        with pytest.raises(AppConfiguringError):
            ConfigLoader().load_config(tmp.name)


def test_config_from_cli(monkeypatch):
    """Test loading config from command line arguments"""
    # Mock sys.argv to simulate command line arguments
    test_args = ["prog", "--IS_PROD", "--VERSION", "2.0.0", "--server.PORT", "8080"]
    monkeypatch.setattr("sys.argv", test_args)

    config_dict = load_from_cli(config_type=AppConfig)

    assert config_dict is not None
    assert config_dict["IS_PROD"] is True
    assert config_dict["VERSION"] == "2.0.0"
    assert config_dict["server"]["PORT"] == 8080


def test_config_from_cli_empty(monkeypatch):
    """Test that config_from_cli returns None when no args are provided"""
    # Mock sys.argv with no relevant arguments
    test_args = ["prog"]
    monkeypatch.setattr("sys.argv", test_args)

    config_dict = load_from_cli(config_type=AppConfig)

    assert config_dict is None


def test_config_from_cli_should_filter_provided_flags(monkeypatch):
    """Test that config_from_cli should filter out _provided attributes"""
    # Mock sys.argv with a boolean flag
    test_args = ["prog", "--IS_PROD"]
    monkeypatch.setattr("sys.argv", test_args)

    # Get CLI config
    cli_config = load_from_cli(config_type=AppConfig)

    # The current implementation includes _provided flags, which is problematic
    assert cli_config is not None

    # This test will fail with the current implementation
    # It should pass once config_from_cli is fixed to filter out _provided attributes
    for key in cli_config:
        assert not key.endswith("_provided"), f"Found unexpected _provided flag: {key}"

    # Check that the actual flag is still there
    assert "IS_PROD" in cli_config
    assert cli_config["IS_PROD"] is True


def test_config_from_cli_fix():
    """Demonstrate how to fix config_from_cli"""
    # This is a demonstration of how config_from_cli should be fixed

    # Mock namespace with _provided flags
    class MockNamespace:
        def __init__(self):
            self.is_prod = True
            self.is_prod_provided = True
            self.version = "1.0.0"
            self.version_provided = True

    mock_args = MockNamespace()
    args_dict = vars(mock_args)

    # Current implementation (problematic)
    current_result = {k: v for k, v in args_dict.items() if is_provided(v)}
    assert "is_prod_provided" in current_result  # This will cause validation errors

    # Fixed implementation
    fixed_result = {
        k: v
        for k, v in args_dict.items()
        if is_provided(v) and not k.endswith("_provided")
    }
    assert "is_prod" in fixed_result
    assert "is_prod_provided" not in fixed_result  # This is what we want


def test_filed_type():
    fi = FieldInfo(name="is_prod", type=Maybe[int], encode_name="is_prod")

    assert parse_field_type(fi).field_type is int


def test_build_parser_with_bool():

    class NestedConfig(ConfigBase):
        name: str

    class NewConfig(ConfigBase):
        nested: NestedConfig

    parser = build_parser(NewConfig)
    res = parser.parse_args(["--nested.name", "lihil"])
    assert getattr(res, "nested.name") == "lihil"


def test_generate_app_confg_acotions():
    generate_parser_actions(AppConfig)


def test_empty_set_config_reset_config():
    config = AppConfig(IS_PROD=True)
    lhl_set_config(config)
    assert lhl_get_config() is config

    lhl_set_config()
    assert lhl_get_config() is DEFAULT_CONFIG
