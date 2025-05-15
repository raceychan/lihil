from datetime import datetime, timezone
from typing import ClassVar, Generic, TypeVar
from uuid import uuid4

from msgspec.json import Decoder
from typing_extensions import dataclass_transform

from lihil.interface import Record, field
from lihil.utils.typing import all_subclasses, union_types


def uuid4_str() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass_transform(frozen_default=True)
class Event(Record, tag_field="typeid", omit_defaults=True):

    # TODO: generate a event page to inspect source, perhaps asyncapi
    # https://www.asyncapi.com/
    """
    Description: Identifies the context in which an event happened. Often this will include information such as the type of the event source, the organization publishing the event or the process that produced the event. The exact syntax and semantics behind the data encoded in the URI is defined by the event producer.
    """
    version: ClassVar[str] = "1"


TBody = TypeVar("TBody", bound=Event)


class Envelope(Record, Generic[TBody], omit_defaults=True):
    """
    a lihil-managed event meta class

    take cloudevents spec as a reference
    https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md

    A container for event, can be used to deliver to kafka, save to pg, etc.
    """

    data: TBody

    sub: str = field(default="", name="entity_id")
    source: str = ""
    event_id: str = field(default_factory=uuid4_str)
    timestamp: datetime = field(default_factory=utc_now)

    @classmethod
    def build_decoder(cls) -> Decoder["Envelope[Event]"]:
        event_subs = all_subclasses(Event)
        sub_union = union_types(list(event_subs))
        return Decoder(type=cls[sub_union])  # type: ignoer

    @classmethod
    def from_event(cls, e: Event):
        "reuse metadata such as eventid, source, sub, from event"
