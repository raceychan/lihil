from pathlib import Path

from .app_config import AppConfig as AppConfig
from .app_config import OASConfig as OASConfig
from .app_config import SecurityConfig as SecurityConfig
from .app_config import ServerConfig as ServerConfig
from .parser import config_from_file

DEFAULT_CONFIG = AppConfig()


def config_registry():
    _app_config: AppConfig = DEFAULT_CONFIG

    def _set_config(app_config: AppConfig | None = None) -> None:
        # TODO? if app_config is None then reset to DEFAULT_CONFIG
        nonlocal _app_config
        if app_config is None:
            _app_config = DEFAULT_CONFIG
        else:
            _app_config = app_config

    def _read_config(
        config_file: str | Path, config_type: type[AppConfig] = AppConfig
    ) -> AppConfig:
        "Read config from config file as well as from command line arguments"
        _app_config = config_from_file(config_file, config_type=config_type)
        return _app_config

    def _get_config() -> AppConfig:
        "Get current config, low overhead"
        return _app_config

    return _set_config, _read_config, _get_config


lhl_set_config, lhl_read_config, lhl_get_config = config_registry()
