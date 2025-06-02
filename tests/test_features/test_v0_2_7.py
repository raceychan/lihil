from lihil import Lihil
from lihil.config import IAppConfig, lhl_get_config


def test_lhl_resolve_config():
    lhl = Lihil()
    config = lhl.graph.resolve(IAppConfig)
    assert config is lhl_get_config()
