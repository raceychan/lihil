from lihil.oas.model import OASB
from lihil.interface import UNSET


class DummyModel(OASB, kw_only=True):
    a: int | None = None
    b: str | None = None


def test_oasb_post_init_sets_unset():
    d = DummyModel()
    # None fields should be converted to UNSET by __post_init__
    assert d.a is UNSET
    assert d.b is UNSET
