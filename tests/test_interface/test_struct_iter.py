from lihil.interface import Record


class Demo(Record):
    a: int = 1
    b: int = 2


def test_struct_iter_and_mapping():
    d = Demo()
    # __iter__ returns iterator over field names
    assert list(iter(d)) == ["a", "b"]
    # keys/len/getitem basic mapping behaviors
    assert d.keys() == ("a", "b")
    assert len(d) == 2
    assert d["a"] == 1 and d["b"] == 2
