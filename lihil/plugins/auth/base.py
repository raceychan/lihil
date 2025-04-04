from typing import Any

from lihil.oas.model import AuthBase
from lihil.plugins.registry import PluginBase


class AuthPlugin(PluginBase[Any]):
    # security base

    def __init__(self, model: AuthBase, scheme_name: str):
        self.model = model  # security base model
        self.scheme_name = scheme_name
