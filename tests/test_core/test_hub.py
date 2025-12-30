from typing import Any

import msgspec
import pytest

from lihil import Annotated, ChannelBase, Lihil, MessageEnvelope, SocketHub, Topic, use
from lihil.errors import SockRejectedError
from lihil.hub import InMemorySocketBus, ISocket


def encode_env(topic: str, event: str, payload=None) -> bytes:
    return msgspec.json.encode({"topic": topic, "event": event, "payload": payload})


class ChatChannel(ChannelBase):
    topic = Topic("room:{room_id}")

    async def on_message(self, env: MessageEnvelope) -> None:
        # Fan out to the room via the bus.
        await self.publish(env.payload, event=env.event)


def test_hub_join_and_chat_roundtrip(test_client):
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join"))
            payload = {"text": "hi"}
            ws.send_bytes(encode_env("room:lobby", "chat", payload))
            data = ws.receive_json()
            assert data["topic"] == "room:lobby"
            assert data["event"] == "chat"
            assert data["payload"] == payload


def test_hub_leave_stops_delivery(test_client):
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join"))
            ws.send_bytes(encode_env("room:lobby", "leave"))
            ws.send_bytes(encode_env("room:lobby", "chat", {"text": "ignored"}))
            data = ws.receive_json()
            assert data["code"] == 4404
            assert data["reason"] == "Topic not found"


def test_hub_chat_without_join_returns_404(test_client):
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "chat", {"text": "hi"}))
            data = ws.receive_json()
            assert data == {"code": 4404, "reason": "Topic not found"}


def test_hub_hooks_run(test_client):
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)
    flags: dict[str, bool] = {"connect": False, "disconnect": False}

    @hub.on_connect
    async def _on_connect(sock):
        flags["connect"] = True

    @hub.on_disconnect
    async def _on_disconnect(sock):
        flags["disconnect"] = True

    app = Lihil(hub)
    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join"))
            ws.close()
    assert flags["connect"] is True
    assert flags["disconnect"] is True


def test_topic_invalid_pattern_raises():
    with pytest.raises(ValueError):
        Topic("room:{oops")


def test_bus_drops_bad_subscriber():
    bus = InMemorySocketBus()
    topic = "room:lobby"
    seen: list[MessageEnvelope] = []

    async def bad_callback(env: MessageEnvelope):
        raise RuntimeError("boom")

    async def good_callback(env: MessageEnvelope):
        seen.append(env)

    import anyio

    async def runner():
        await bus.subscribe(topic, bad_callback)
        await bus.subscribe(topic, good_callback)
        await bus.publish(topic, "chat", {"text": "hi"})
        await bus.publish(topic, "chat", {"text": "hi again"})

    anyio.run(runner)
    # bad callback removed after first failure; good_callback sees both messages
    assert len(seen) == 2
    assert seen[-1].payload == {"text": "hi again"}


def test_isocket_allow_if_rejects():
    class FakeWS:
        def __init__(self):
            self.closed = None

        async def close(self, code: int = 1000, reason: str | None = None):
            self.closed = (code, reason)

    sock = ISocket(FakeWS())  # type: ignore[arg-type]
    with pytest.raises(SockRejectedError):
        import anyio

        anyio.run(sock.allow_if, False)
    assert sock._ws.closed == (4403, "Forbidden")


def test_channelbase_requires_on_message():
    class IncompleteChannel(ChannelBase):
        topic = Topic("room:{room_id}")

    with pytest.raises(TypeError):
        IncompleteChannel(None, topic="room:lobby", params={}, bus=InMemorySocketBus())  # type: ignore[arg-type]


def test_hub_bus_factory_with_dependency(test_client):
    class FakeKafka:
        pass

    build_calls = {"kafka": 0, "bus": 0}

    def build_kafka() -> FakeKafka:
        build_calls["kafka"] += 1
        return FakeKafka()

    def build_bus(kafka: Annotated[FakeKafka, use(build_kafka)]) -> InMemorySocketBus:
        build_calls["bus"] += 1
        bus = InMemorySocketBus()
        bus.kafka = kafka  # type: ignore[attr-defined]
        return bus

    class ProbeChannel(ChannelBase):
        topic = Topic("room:{room_id}")
        seen_buses: list[InMemorySocketBus] = []

        async def on_join(self) -> None:
            ProbeChannel.seen_buses.append(self.bus)  # type: ignore[arg-type]
            await super().on_join()

        async def on_message(self, env: MessageEnvelope) -> None:
            await self.publish(env.payload, event=env.event)

    hub = SocketHub("/ws/chat", bus_factory=build_bus)
    hub.add_nodes(build_kafka, build_bus)
    hub.channel(ProbeChannel)
    ProbeChannel.seen_buses.clear()

    app = Lihil(hub)
    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join"))
            ws.send_bytes(encode_env("room:lobby", "chat", {"text": "hi"}))
            data = ws.receive_json()
            assert data["payload"] == {"text": "hi"}

    assert build_calls == {"kafka": 1, "bus": 1}
    assert len(ProbeChannel.seen_buses) == 1
    bus = ProbeChannel.seen_buses[0]
    assert isinstance(bus, InMemorySocketBus)
    assert hasattr(bus, "kafka") and isinstance(bus.kafka, FakeKafka)


def test_hub_unknown_event_rejected(test_client):
    class GuardedChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_message(self, env: MessageEnvelope) -> dict[str, Any] | None:
            if env.event != "chat":
                return {"code": 4404, "reason": "Event not found"}
            await self.publish(env.payload, event=env.event)

    hub = SocketHub("/ws/chat")
    hub.channel(GuardedChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join"))
            ws.send_bytes(encode_env("room:lobby", "unknown", {"x": 1}))
            data = msgspec.json.decode(ws.receive_bytes())
            assert data == {"code": 4404, "reason": "Event not found"}
