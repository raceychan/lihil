from pathlib import Path
from typing import TypeVar, cast, overload

from ididi import Ignore

from .app_config import AppConfig as AppConfig
from .app_config import ConfigBase as ConfigBase
from .app_config import IAppConfig as IAppConfig
from .app_config import OASConfig as OASConfig
from .app_config import ServerConfig as ServerConfig
from .loader import ConfigLoader as ConfigLoader

DEFAULT_CONFIG: IAppConfig = AppConfig()


TConfig = TypeVar("TConfig", bound=AppConfig)


def config_registry():
    _app_config: IAppConfig = DEFAULT_CONFIG

    def _set_config(app_config: IAppConfig | None = None) -> None:
        "Set app config, if no config provided, reset to DEFAULT_CONFIG"
        nonlocal _app_config
        if app_config is None:
            _app_config = DEFAULT_CONFIG
        else:
            _app_config = app_config

    def _read_config(
        *config_files: str | Path, config_type: type[TConfig] = AppConfig
    ) -> TConfig | None:
        """Read config from config file as well as from command line arguments
        Read Order
        files -> env vars -> cli args"""
        loader = ConfigLoader()
        _app_config = loader.load_config(*config_files, config_type=config_type)
        return _app_config

    @overload
    def _get_config(config_type: type[TConfig]) -> TConfig: ...
    @overload
    def _get_config(config_type: None = None) -> IAppConfig: ...

    def _get_config(
        config_type: Ignore[type[TConfig] | None] = None,
    ) -> TConfig | IAppConfig:
        "Get current config, low overhead"
        return cast(TConfig, _app_config)

    return _set_config, _read_config, _get_config


lhl_set_config, lhl_read_config, lhl_get_config = config_registry()
