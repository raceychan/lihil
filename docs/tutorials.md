
## Tutorials

### Config

You can alter app behavior by `lihil.config.AppConfig`

#### via config file

```python
lhl = Lihil(config_file="pyproject.toml")
```

This will look for `tool.lihil` table in the `pyproject.toml` file
extra/unkown keys will be forbidden to help prevent misconfiging

Note: currently only toml file is supported

#### build `lihil.config.AppConfig` instance menually

```python
lhl = Lihil(app_config=AppConfig(version="0.1.1"))
```

this is particularly useful if you want to inherit from AppConfig and extend it.

```python
from lihil.config import AppConfig

class MyConfig(AppConfig):
    app_name: str

config = MyConfig.from_file("myconfig.toml")
```

You can override config with command line arguments:

```example
python app.py --oas.title "New Title" --is_prod true
```

use `.` to express nested fields

