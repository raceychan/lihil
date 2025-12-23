from lihil.utils.json import _compose_hooks, _default_schema_hook


def test_default_schema_hook_handles_object_type():
    assert _default_schema_hook(object) == {"type": "object"}


def test_default_schema_hook_returns_none_for_other_types():
    assert _default_schema_hook(int) is None


def test_compose_hooks_without_user_hook_returns_default_hook():
    composed = _compose_hooks(None)
    assert composed is _default_schema_hook


def test_compose_hooks_prefers_user_hook_when_schema_provided():
    def user_hook(t: type):  # pragma: no cover - simple test helper
        if t is str:
            return {"type": "string"}
        return None

    composed = _compose_hooks(user_hook)

    assert composed(str) == {"type": "string"}


def test_compose_hooks_falls_back_to_default_when_user_returns_none():
    def user_hook(_: type):  # pragma: no cover - simple test helper
        return None

    composed = _compose_hooks(user_hook)

    assert composed(object) == {"type": "object"}
