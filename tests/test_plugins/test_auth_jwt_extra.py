import pytest
from pytest import importorskip

importorskip("jwt")
pytestmark = pytest.mark.requires_auth

from types import SimpleNamespace

from jwt.exceptions import InvalidTokenError

from lihil.plugins.auth import jwt as jwt_module
from lihil.problems import InvalidAuthError


def _dummy_ep_info(header_params):
    sig = SimpleNamespace(header_params=header_params, default_return=SimpleNamespace(encoder=None, type_=None))
    return SimpleNamespace(sig=sig, func=lambda *_, **__: "ok")


def test_decode_plugin_returns_original_when_no_auth():
    plugin = jwt_module.JWTAuthPlugin("secret", "HS256")
    ep_info = _dummy_ep_info({})

    wrapped = plugin.decode_plugin()(ep_info)

    assert wrapped is ep_info.func


def test_decode_plugin_errors_on_multiple_headers(monkeypatch):
    plugin = jwt_module.JWTAuthPlugin("secret", "HS256")
    param = SimpleNamespace(
        name="auth", alias="Authorization", type_=str, source="header", decoder=None
    )
    ep_info = _dummy_ep_info({"auth": param})
    plugin.decode_plugin()(ep_info)

    with pytest.raises(InvalidAuthError):
        param.decoder(["a", "b"])  # type: ignore[arg-type]


def test_decode_plugin_decodes_and_handles_invalid_token(monkeypatch):
    plugin = jwt_module.JWTAuthPlugin("secret", "HS256")
    param = SimpleNamespace(
        name="auth", alias="Authorization", type_=str, source="header", decoder=None
    )
    ep_info = _dummy_ep_info({"auth": param})
    plugin.decode_plugin()(ep_info)

    monkeypatch.setattr(
        plugin.jwt,
        "decode",
        lambda token, key, algorithms, audience, issuer: {"sub": "alice"},
    )
    assert param.decoder("Bearer token") == "alice"

    def raise_invalid(*_, **__):
        raise InvalidTokenError("bad")

    monkeypatch.setattr(plugin.jwt, "decode", raise_invalid)
    with pytest.raises(InvalidAuthError):
        param.decoder("Bearer bad")


def test_encode_plugin_sets_encoder_and_rejects_negative_exp(monkeypatch):
    plugin = jwt_module.JWTAuthPlugin("secret", "HS256")
    with pytest.raises(ValueError):
        plugin.encode_plugin(-1)

    encoded_payloads = []

    class DummyJWS:
        def encode(self, payload_bytes, key):
            encoded_payloads.append(payload_bytes)
            return "jwt-token"

    monkeypatch.setattr(plugin, "jws", DummyJWS())

    ep_info = _dummy_ep_info({})
    plugin.encode_plugin(1, iss="issuer", nbf=2, aud="aud")(ep_info)

    token_bytes = ep_info.sig.default_return.encoder("subject")
    assert b"jwt-token" in token_bytes
    assert encoded_payloads  # ensure encoder invoked
