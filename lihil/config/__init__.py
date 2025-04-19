from lihil.errors import AppConfiguringError

from .app_config import AppConfig as AppConfig
from .app_config import OASConfig as OASConfig
from .app_config import SecurityConfig as SecurityConfig
from .app_config import ServerConfig as ServerConfig
from .parser import config_from_file

DEFAULT_CONFIG = AppConfig()


def config_registry():
    _app_config: AppConfig = DEFAULT_CONFIG
    from pathlib import Path

    def _set_config(
        config_file: str | Path | None = None, app_config: AppConfig | None = None
    ) -> None:
        if config_file and app_config:
            raise AppConfiguringError(
                "Can't set both config_file and app_config, choose either one of them"
            )

        nonlocal _app_config
        if app_config:
            _app_config = app_config
        else:
            _app_config = config_from_file(config_file)

    def _get_config() -> AppConfig:
        return _app_config

    return _set_config, _get_config


lhl_set_config, lhl_get_config = config_registry()
