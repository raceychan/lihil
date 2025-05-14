from datetime import datetime, timezone
from typing import Annotated

from msgspec.json import encode

from lihil.ds.event import Envelope, Event, utc_now, uuid4_str


class UserCreated(Event):
    user_id: str


def test_uuid_factory():
    uuids = [uuid4_str() for _ in range(3)]

    assert isinstance(uuids[0], str)
    assert uuids[0] != uuids[1] != uuids[2]


def test_ts_factory():
    assert isinstance(utc_now(), datetime)
    assert utc_now().tzinfo is timezone.utc


def test_evenlop_build_encoder():
    user_id = uuid4_str()
    event = UserCreated(user_id)
    enve = Envelope[UserCreated](event, sub=user_id, source="lihil")

    bytes_enve = encode(enve)

    decoder = Envelope.build_decoder()

    res = decoder.decode(bytes_enve)
    assert isinstance(res, Envelope)
    assert res.data == event


import pytest
from ididi import Graph, Ignore, use
from msgspec import Struct


class User(Struct):
    name: str
    age: int


side_effect: list[int] = []


async def get_user() -> Ignore[User]:
    global side_effect
    side_effect.append(1)
    return User("test", 1)


class EP:
    def __init__(self, user: Annotated[User, use(get_user, reuse=False)]): ...


# @pytest.mark.debug
# async def test_resolve_func():
#     dg = Graph()

#     res = []


#     # dg.analyze(get_user, config=NodeConfig(reuse=False))

#     dg.analyze(EP)

#     breakpoint()


from starlette.datastructures import QueryParams


def test_query_param():
    from msgspec import convert

    qs = QueryParams("q=1&q=2")
    assert convert(qs.getlist("q"), list[int], strict=False) == [1, 2]
