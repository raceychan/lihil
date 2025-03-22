from datetime import UTC, datetime

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
    assert utc_now().tzinfo is UTC


def test_evenlop_build_encoder():
    user_id = uuid4_str()
    event = UserCreated(user_id)
    enve = Envelope[UserCreated](event, sub=user_id, source="lihil")

    bytes_enve = encode(enve)

    decoder = Envelope.build_decoder()

    res = decoder.decode(bytes_enve)
    assert isinstance(res, Envelope)
    assert res.data == event
