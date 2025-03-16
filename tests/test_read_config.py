from lihil import Lihil

# from lihil.config import AppConfig


def test_app_read_config():
    lhl = Lihil(config_file="pyproject.toml")
    assert lhl.app_config.oas.doc_path == "/docs"
