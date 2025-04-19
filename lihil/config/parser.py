import argparse
from pathlib import Path
from typing import Any, Sequence, TypeGuard, cast, get_args

from msgspec import convert
from msgspec.structs import FieldInfo, fields
from typing_extensions import Doc

from lihil.config.app_config import AppConfig, ConfigBase
from lihil.interface import MISSING, UNSET, Record, StrDict, is_provided
from lihil.utils.typing import get_origin_pro, is_union_type


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

    def both_instance(a: Any, b: Any, t: type) -> bool:
        return isinstance(a, t) and isinstance(b, t)

    for key, value in update_data.items():
        if key not in original:
            original[key] = value
        else:
            ori_val = original[key]
            if both_instance(ori_val, value, dict):
                deep_update(cast(StrDict, ori_val), cast(StrDict, value))
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


def is_config_type(ftype: Any) -> TypeGuard[type[ConfigBase]]:
    return isinstance(ftype, type) and issubclass(ftype, ConfigBase)


class ConfigField(Record):
    field_type: type
    doc: str


def parse_field_type(field: FieldInfo) -> ConfigField:
    "Todo: parse Maybe[int] = MISSING"

    ftype, metas = get_origin_pro(field.type)
    doc: str = ""
    if metas:
        for m in metas:
            if isinstance(m, Doc):
                doc = m.documentation
                break

    if is_union_type(ftype):
        unions = get_args(ftype)
        ftype = next(filter(lambda x: x not in (None, UNSET, MISSING), unions))

    return ConfigField(cast(type, ftype), doc)


def generate_parser_actions(
    config_type: type[ConfigBase], prefix: str = ""
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    cls_fields = fields(config_type)

    for field_info in cls_fields:
        field_name = field_info.encode_name
        field_default: Any = MISSING  # if field_type is not bool else field_info.default

        full_field_name = f"{prefix}.{field_name}" if prefix else field_name
        arg_name = f"--{full_field_name}"

        config_field = parse_field_type(field_info)

        field_type = config_field.field_type
        if is_config_type(field_type):
            nested_actions = generate_parser_actions(field_type, full_field_name)
            actions.extend(nested_actions)
        else:
            help_msg = f"{config_field.doc}"
            if is_provided(field_default):
                help_msg += f"default: {field_default})"

            if field_type is bool:
                action = {
                    "name": arg_name,
                    "type": "bool",
                    "action": "store_true",
                    "default": field_default,
                    "help": help_msg,
                }
            else:
                action = {
                    "name": arg_name,
                    "type": field_type,
                    "default": field_default,
                    "help": help_msg,
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
    if config_file is not None:
        file_path = Path(config_file) if isinstance(config_file, str) else config_file
        config_dict = config_type.from_file(file_path)
    else:
        config_dict = config_type().asdict(skip_unset=True)

    cli_config = config_from_cli(config_type)
    if cli_config:
        deep_update(config_dict, cli_config)

    config = convert(config_dict, config_type)
    return config
