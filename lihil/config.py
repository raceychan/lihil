import argparse
import tomllib
from pathlib import Path
from types import UnionType
from typing import Any, Sequence, Union, cast, get_args, get_origin

from msgspec import convert, field
from msgspec.structs import FieldInfo, fields

from lihil.errors import AppConfiguringError
from lihil.interface import MISSING, Maybe, Record, get_maybe_vars, is_provided

StrDict = dict[str, Any]


def get_thread_cnt() -> int:
    import os

    default_max = os.cpu_count() or 1
    return default_max


def format_nested_dict(flat_dict: StrDict) -> StrDict:
    """
    Convert a flat dictionary with dot notation keys to a nested dictionary.

    Example:
        {"oas.title": "API Docs"} -> {"oas": {"title": "API Docs"}}
    """
    result: StrDict = {}

    for key, value in flat_dict.items():
        if "." in key:
            parts = key.split(".")
            current = result
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        else:
            result[key] = value
    return result


def deep_update(original: StrDict, update_data: StrDict) -> StrDict:
    """
    Recursively update a nested dictionary without overwriting entire nested structures.
    """
    for key, value in update_data.items():
        if (
            key in original
            and isinstance(original[key], dict)
            and isinstance(value, dict)
        ):
            deep_update(original[key], cast(Any, value))
        else:
            original[key] = value
    return original


class StoreTrueIfProvided(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ):
        setattr(namespace, self.dest, True)
        # Set a flag to indicate this argument was provided
        setattr(namespace, f"{self.dest}_provided", True)

    def __init__[**P](self, *args: P.args, **kwargs: P.kwargs):
        # Set nargs to 0 for store_true action
        kwargs["nargs"] = 0
        kwargs["default"] = MISSING
        super().__init__(*args, **kwargs)  # type: ignore


class ConfigBase(Record, forbid_unknown_fields=True): ...


class OASConfig(ConfigBase):
    oas_path: str = "/openapi"
    doc_path: str = "/docs"
    problem_path: str = "/problems"
    problem_title: str = "lihil-Problem Page"
    title: str = "lihil-OpenAPI"
    version: str = "3.1.0"


class ServerConfig(ConfigBase):
    host: str | None = None
    port: int | None = None
    workers: int | None = None
    reload: bool | None = None
    root_path: str | None = None


def parse_field_type(field: FieldInfo) -> type:
    "Todo: parse Maybe[int] = MISSING"

    ftype = field.type
    origin = get_origin(ftype)

    if origin is UnionType or origin is Union:
        unions = get_args(ftype)
        assert unions
        for targ in unions:
            return targ
    elif origin is Maybe:
        maybe_var = get_maybe_vars(ftype)
        assert maybe_var
        return maybe_var

    return ftype


class AppConfig(ConfigBase):
    is_prod: bool = False
    version: str = "0.1.0"
    max_thread_workers: int = field(default_factory=get_thread_cnt)
    oas: OASConfig = OASConfig()
    server: ServerConfig = ServerConfig()

    @classmethod
    def from_toml(cls, file_path: Path) -> StrDict:
        with open(file_path, "rb") as fp:
            toml = tomllib.load(fp)

        try:
            lihil_config: StrDict = toml["tool"]["lihil"]
        except KeyError:
            try:
                lihil_config: StrDict = toml["lihil"]
            except KeyError:
                raise AppConfiguringError(f"can't find table lihil from {file_path}")
        return lihil_config


def generate_parser_actions(
    config_type: type[ConfigBase], prefix: str = ""
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    cls_fields = fields(config_type)

    for field_info in cls_fields:
        field_name = field_info.encode_name
        field_type = field_info.type
        field_default = MISSING  # if field_type is not bool else field_info.default

        full_field_name = f"{prefix}.{field_name}" if prefix else field_name
        arg_name = f"--{full_field_name}"

        if isinstance(field_type, type) and issubclass(field_type, ConfigBase):
            nested_actions = generate_parser_actions(field_type, full_field_name)
            actions.extend(nested_actions)
        else:
            if field_type is bool:
                action = {
                    "name": arg_name,
                    "type": "bool",
                    "action": "store_true",
                    "default": field_default,
                    "help": f"Set {full_field_name} (default: {field_default})",
                }
            else:
                action = {
                    "name": arg_name,
                    "type": parse_field_type(field_info),
                    "default": field_default,
                    "help": f"Set {full_field_name} (default: {field_default})",
                }
            actions.append(action)
    return actions


def build_parser(config_type: type[ConfigBase]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="lihil application configuration")
    actions = generate_parser_actions(config_type)

    for action in actions:
        if action["type"] == "bool":
            parser.add_argument(
                action["name"],
                action=action["action"],
                default=action["default"],
                help=action["help"],
            )
        else:
            parser.add_argument(
                action["name"],
                type=action["type"],
                default=action["default"],
                help=action["help"],
            )
    return parser


def config_from_cli(config_type: type[AppConfig]) -> StrDict | None:
    parser = build_parser(config_type)
    known_args = parser.parse_known_args()[0]
    args = known_args.__dict__

    # Filter out _provided flags and keep only provided values
    cli_args: StrDict = {k: v for k, v in args.items() if is_provided(v)}

    if not cli_args:
        return None

    config_dict = format_nested_dict(cli_args)
    return config_dict


def config_from_file(
    config_file: Path | str | None, *, config_type: type[AppConfig] = AppConfig
) -> AppConfig:
    if config_file is None:
        return config_type()  # everything default

    if isinstance(config_file, str):
        file_path = Path(config_file)
    else:
        file_path = config_file

    if not file_path.exists():
        raise AppConfiguringError(f"path {file_path} not exist")

    file_ext = file_path.suffix[1:]

    if file_ext == "toml":
        config_dict = config_type.from_toml(file_path)
    else:
        raise AppConfiguringError(f"Not supported file type {file_ext}")

    cli_config = config_from_cli(config_type)
    if cli_config:
        deep_update(config_dict, cli_config)

    config = convert(config_dict, config_type)
    return config
