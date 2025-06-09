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
    _loader = ConfigLoader()

    def _set_config(app_config: IAppConfig | None = None) -> None:
        """
        ## Set Configuration

        Sets the current application configuration.

        ### Parameters
        - `app_config` (Optional[`IAppConfig`]):
            - If provided, sets the application configuration to the given instance.
            - If `None`, resets the configuration to the default (`DEFAULT_CONFIG`).

        ### Example
        ```python
        lhl_set_config(AppConfig(...))   # Set a custom config
        lhl_set_config()                 # Reset to default
        ```

        ---
        """

        nonlocal _app_config
        if app_config is None:
            _app_config = DEFAULT_CONFIG
        else:
            _app_config = app_config

    def _read_config(
        *config_files: str | Path,
        config_type: type[TConfig] = AppConfig,
        raise_on_not_found: bool = True,
    ) -> TConfig | None:
        """
        ## Read Configuration

        Reads configuration from one or more files and merges them, followed by parsing CLI arguments.

        ### Parameters
        - `*config_files` (str | Path):
            One or more config file paths. If multiple files are passed, later ones override earlier ones.
        - `config_type` (type[`TConfig`]):
            The type of configuration class to parse and return. Defaults to `AppConfig`.

        ### Priority Order
        1. Config files (merged in order)
        2. Command-line arguments

        ### Returns
        - An instance of the parsed configuration (`TConfig`), or `None` if loading fails.

        ### Example
        ```python
        config = lhl_read_config("dev.env", "prod.env", config_type=MyAppConfig)
        ```

        ---
        """
        # TODO: read from environtment variable then file then cli args

        _app_config = _loader.load_config(
            *config_files,
            config_type=config_type,
            raise_on_not_found=raise_on_not_found,
        )
        return _app_config

    @overload
    def _get_config(config_type: type[TConfig]) -> TConfig: ...
    @overload
    def _get_config(config_type: None = None) -> IAppConfig: ...

    def _get_config(
        config_type: Ignore[type[TConfig] | None] = None,
    ) -> TConfig | IAppConfig:
        """
        ## Get Configuration

        Retrieves the current application configuration.

        ### Parameters
        - `config_type` (Optional[type[`TConfig`]]):
            Used for typing only. The actual stored config is cast to this type if provided.

        ### Returns
        - The current configuration instance (`TConfig` or `IAppConfig`).

        ### Example
        ```python
        config: IAppConfig = lhl_get_config()
        typed_config: MyAppConfig = lhl_get_config(MyAppConfig)
        ```

        ---
        """
        return cast(TConfig, _app_config)

    return _set_config, _read_config, _get_config


lhl_set_config, lhl_read_config, lhl_get_config = config_registry()
