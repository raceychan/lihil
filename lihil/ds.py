from datetime import datetime, timezone
from typing import ClassVar, Self, dataclass_transform
from uuid import uuid4

from msgspec.json import Decoder

from lihil.interface import Base, field
from lihil.utils.visitor import all_subclasses, union_types


def uuid_factory() -> str:
    return str(uuid4())


def ts_factory() -> datetime:
    return datetime.now(timezone.utc)


class Envelope[Body](Base):
    """
    a lihil-managed event meta class

    take cloudevents spec as a reference
    https://github.com/cloudevents/spec/blob/main/cloudevents/spec.md
    """

    entity_id: str
    data: Body

    source: str | None = None
    event_id: str = field(default_factory=uuid_factory)
    timestamp: datetime = field(default_factory=ts_factory)  # cloudevents name: time


    def build_decoder(self) -> Decoder["Self"]:
        "Build a decoder that decodes all subclsses of current class"
        subs = all_subclasses(self.__class__)
        sub_union = union_types(subs)
        return Decoder(sub_union)


@dataclass_transform(frozen_default=True)
class Event(
    Base,
    tag_field="typeid",
    frozen=True,
    cache_hash=True,
    gc=False,
    kw_only=True,
    omit_defaults=True,
):

    # TODO: generate a event page to inspect source
    """
    Description: Identifies the context in which an event happened. Often this will include information such as the type of the event source, the organization publishing the event or the process that produced the event. The exact syntax and semantics behind the data encoded in the URI is defined by the event producer.
    """
    version: ClassVar[str] = "1"


"""
async def publish(event: Event, subject: str, source: str | None = None):
    eve = Envelope(data=event, subject=subject, source=source)


async def create_user(user: User, bus: EventBus):
    await bus.publish(event = user_created, subject=user.user_id)
"""
