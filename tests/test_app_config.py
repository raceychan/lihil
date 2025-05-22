import argparse
from unittest.mock import patch

import pytest

from lihil import Lihil
from lihil.config import AppConfig, ConfigBase, lhl_get_config, lhl_read_config
from lihil.config.loader import ConfigLoader, convert, load_from_cli
from lihil.config.parser import StoreTrueIfProvided, build_parser, format_nested_dict
from lihil.interface import MISSING

# from lihil.config import AppConfig


def test_app_read_config():
    config = lhl_read_config("settings.toml")
    Lihil(app_config=config)
    config = lhl_get_config()
    assert config.oas.DOC_PATH == "/docs"


def test_format_nested_dict():
    """Test that flat dictionaries with dot notation are properly nested."""
    flat_dict = {
        "version": "1.0.0",
        "oas.title": "My API",
        "oas.version": "3.0.0",
        "oas.doc_path": "/api/docs",
    }

    expected = {
        "version": "1.0.0",
        "oas": {"title": "My API", "version": "3.0.0", "doc_path": "/api/docs"},
    }

    result = format_nested_dict(flat_dict)
    assert result == expected


def test_format_nested_dict_multiple_levels():
    """Test that format_nested_dict handles multiple levels of nesting."""
    flat_dict = {"a.b.c": 1, "a.b.d": 2, "a.e": 3, "f": 4}

    expected = {"a": {"b": {"c": 1, "d": 2}, "e": 3}, "f": 4}

    result = format_nested_dict(flat_dict)
    assert result == expected


def test_store_true_if_provided_action():
    """Test that StoreTrueIfProvided action correctly sets values and tracking flags."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--flag", action=StoreTrueIfProvided)

    # Test when flag is provided
    args = parser.parse_args(["--flag"])
    assert args.flag is True
    assert args.flag_provided is True

    # Test when flag is not provided
    args = parser.parse_args([])
    assert args.flag is MISSING
    assert not hasattr(args, "flag_provided")


def test_app_config_build_parser():
    """Test that AppConfig.build_parser creates a parser with expected arguments."""
    parser = build_parser(AppConfig)

    # Check that some expected arguments exist
    actions = {action.dest: action for action in parser._actions}

    # Check top-level arguments
    assert "VERSION" in actions
    assert "IS_PROD" in actions

    # Check nested arguments
    assert "oas.TITLE" in actions
    assert "oas.DOC_PATH" in actions


@patch("sys.argv", ["prog", "--VERSION", "2.0.0", "--oas.TITLE", "Custom API"])
def test_config_from_cli():
    """Test that config_from_cli correctly parses command line arguments."""
    config_dict = load_from_cli(config_type=AppConfig)

    assert config_dict is not None
    assert config_dict["VERSION"] == "2.0.0"
    assert config_dict["oas"]["TITLE"] == "Custom API"


@patch("sys.argv", ["prog", "--IS_PROD"])
def test_config_from_cli_boolean_flag():
    """Test that boolean flags are correctly handled."""
    config_dict = load_from_cli(config_type=AppConfig)

    assert config_dict is not None
    assert config_dict["IS_PROD"] is True


@patch("sys.argv", ["prog"])
def test_config_from_cli_no_args():
    """Test that config_from_cli returns None when no arguments are provided."""
    config_dict = load_from_cli(config_type=AppConfig)

    assert config_dict is None


@patch("sys.argv", ["prog", "--unknown-arg", "value"])
def test_config_from_cli_unknown_args():
    """Test that config_from_cli ignores unknown arguments."""
    config_dict = load_from_cli(config_type=AppConfig)
    assert config_dict is None  # No recognized arguments


# def test_app_load_configpath(tmp_path: Path):
#     toml_file = tmp_path / "config.toml"

#     toml_file.touch()

#     with pytest.raises(AppConfiguringError):
#         res = ConfigLoader().load_config(toml_file)


def test_enhance_app_config():
    class SupabaseConfig(ConfigBase):
        url: str
        key: str

    class MyConfig(AppConfig, kw_only=True):
        supabase: SupabaseConfig

    res = load_from_cli(
        ["prog", "--supabase.url", "myurl", "--supabase.key", "mykey"],
        config_type=MyConfig,
    )
    config = convert(res, MyConfig)
    assert config.supabase.url == "myurl"
    assert config.supabase.key == "mykey"


def test_loader():
    loader = ConfigLoader()
