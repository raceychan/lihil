from typing import Annotated, AsyncGenerator

from msgspec.json import encode

from lihil import Lihil, Route, Stream, Struct, Param
from lihil.signature.parser import EndpointParser


class Event(Struct):
    id: int
    name: str


async def test_ep_with_async_gen_struct(ep_parser: EndpointParser):

    async def struct_gen() -> AsyncGenerator[Event, None]:
        yield Event(id=1, name="event1")
        yield Event(id=2, name="event2")

    def event_decoder(event: Event) -> bytes:
        return encode(event)

    async def ep_with_async_gen_struct() -> Stream[Event]:
        return struct_gen()

    async def post_with_event_resp() -> Event:
        return Event(id=1, name="event1")

    st = Route("/stream")
    st.get(ep_with_async_gen_struct)
    st.post(post_with_event_resp)
    lhl = Lihil(st)
    oas = lhl.genereate_oas()

    stream_oas = oas["paths"]["/stream"]

    stream_resp_content = stream_oas.get.responses["200"].content
    event_resp_content = stream_oas.post.responses["200"].content
    assert stream_resp_content
    assert event_resp_content
