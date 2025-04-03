from typing import Any

from lihil.oas.model import AuthBase
from lihil.plugins.provider import ProviderMixin


class AuthProvider[Model: AuthBase](ProviderMixin[Any]):
    # security base

    def __init__(self, model: Model, scheme_name: str):
        self.model = model  # security base model
        self.scheme_name = scheme_name
