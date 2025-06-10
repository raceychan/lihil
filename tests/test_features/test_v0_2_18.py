from lihil.problems import InvalidAuthError, InvalidRequestErrors
from lihil.routing import EndpointProps


def test_props_merge():
    p1 = EndpointProps(problems=[InvalidAuthError])
    p2 = EndpointProps(problems=[InvalidRequestErrors])

    p3 = p1.merge(p2, deduplicate=True)
    assert p3.problems == [InvalidAuthError, InvalidRequestErrors]


def test_props_merge2():
    p1 = EndpointProps()
    p2 = EndpointProps(in_schema=False)

    p3 = p1.merge(p2, deduplicate=True)
    assert p3.in_schema == False


def test_props_update():
    p1 = EndpointProps(problems=[InvalidAuthError])
    p2 = EndpointProps(problems=[InvalidRequestErrors])

    p3 = p1.update(p2)
    assert p3.problems == [InvalidRequestErrors]
