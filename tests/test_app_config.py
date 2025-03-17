import argparse
from unittest.mock import patch

from lihil import Lihil
from lihil.config import MISSING, AppConfig, StoreTrueIfProvided, format_nested_dict

# from lihil.config import AppConfig


def test_app_read_config():
    lhl = Lihil(config_file="pyproject.toml")
    assert lhl.app_config.oas.doc_path == "/docs"


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
    parser = AppConfig.build_parser()

    # Check that some expected arguments exist
    actions = {action.dest: action for action in parser._actions}

    # Check top-level arguments
    assert "version" in actions
    assert "is_prod" in actions

    # Check nested arguments
    assert "oas.title" in actions
    assert "oas.doc_path" in actions


@patch("sys.argv", ["prog", "--version", "2.0.0", "--oas.title", "Custom API"])
def test_config_from_cli():
    """Test that config_from_cli correctly parses command line arguments."""
    config_dict = AppConfig.config_from_cli()

    assert config_dict is not None
    assert config_dict["version"] == "2.0.0"
    assert config_dict["oas"]["title"] == "Custom API"


@patch("sys.argv", ["prog", "--is_prod"])
def test_config_from_cli_boolean_flag():
    """Test that boolean flags are correctly handled."""
    config_dict = AppConfig.config_from_cli()

    assert config_dict is not None
    assert config_dict["is_prod"] is True


@patch("sys.argv", ["prog"])
def test_config_from_cli_no_args():
    """Test that config_from_cli returns None when no arguments are provided."""
    config_dict = AppConfig.config_from_cli()
    assert config_dict is None


@patch("sys.argv", ["prog", "--unknown-arg", "value"])
def test_config_from_cli_unknown_args():
    """Test that config_from_cli ignores unknown arguments."""
    config_dict = AppConfig.config_from_cli()
    assert config_dict is None  # No recognized arguments


# def test_app_config_from_cli_integration():
#     """Integration test for creating AppConfig from CLI arguments."""
#     with patch("sys.argv", ["prog", "--version", "2.0.0", "--oas.title", "Custom API"]):
#         config = AppConfig.from_cli()

#         assert config.version == "2.0.0"
#         assert config.oas.title == "Custom API"

#         # Other values should have defaults
#         assert config.is_prod is False
#         assert config.oas.doc_path == "/docs"
