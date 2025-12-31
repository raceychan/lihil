from typing import Any

import msgspec
import pytest

from lihil import Annotated, ChannelBase, Graph, ISocket, Lihil, MessageEnvelope, SocketHub, Topic, use
from lihil.errors import SockRejectedError
from lihil.socket.hub import ChannelRegistry, InMemorySocketBus, TOPIC_NOT_FOUND
from lihil.vendors import WebSocketDisconnect, WebSocketState


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


def test_bus_unsubscribe_cleanup_and_emit(monkeypatch):
    import anyio
    import asyncio

    bus = InMemorySocketBus()

    async def dummy_cb(env: MessageEnvelope):
        pass

    async def runner():
        await bus.unsubscribe("missing", dummy_cb)
        await bus.subscribe("room:lobby", dummy_cb)
        await bus.unsubscribe("room:lobby", dummy_cb)
        assert "room:lobby" not in bus._subs

        orig_create_task = asyncio.create_task
        tasks: list[Any] = []

        def fake_create_task(coro):
            tasks.append(coro)
            return orig_create_task(coro)

        monkeypatch.setattr(asyncio, "create_task", fake_create_task)

        await bus.emit("room:lobby", "chat", {"t": 1})
        assert tasks, "emit should schedule a publish task"

    anyio.run(runner)


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


def test_isocket_proxies_and_messages():
    from msgspec.json import encode
    import anyio

    class FakeWS:
        def __init__(self):
            self.application_state = WebSocketState.CONNECTED
            self.client_state = WebSocketState.CONNECTED
            self.scope = {"type": "websocket"}
            self.state = {"user": "abc"}
            self.headers = {"h": "v"}
            self.query_params = {"q": "1"}
            self.path_params = {"p": "1"}
            self.url = "ws://example.test/ws"
            self.accepted = None
            self.closed: list[tuple[int, str]] = []
            self.sent: list[tuple[str, Any]] = []

        async def accept(self, subprotocol=None):
            self.accepted = subprotocol

        async def close(self, code: int = 1000, reason: str | None = None):
            self.closed.append((code, reason or ""))

        async def send_json(self, data: Any):
            self.sent.append(("json", data))

        async def send_text(self, data: str):
            self.sent.append(("text", data))

        async def send_bytes(self, data: bytes):
            self.sent.append(("bytes", data))

        async def receive_json(self):
            return {"kind": "json"}

        async def receive_text(self):
            return "text"

        async def receive_bytes(self):
            return encode(MessageEnvelope(topic="room:lobby", event="chat", payload={"x": 1}))

    async def runner():
        fake = FakeWS()
        sock = ISocket(fake, topic="room:lobby")

        assert sock.websocket is fake
        assert sock.application_state == WebSocketState.CONNECTED
        assert sock.client_state == WebSocketState.CONNECTED
        assert sock.scope["type"] == "websocket"
        assert sock.state["user"] == "abc"
        assert sock.headers["h"] == "v"
        assert sock.query_params["q"] == "1"
        assert sock.path_params["p"] == "1"
        assert sock.url.endswith("/ws")

        await sock.accept("proto1")
        await sock.send_json({"hello": "world"})
        await sock.send_text("hi")
        await sock.send_bytes(b"bin")
        assert await sock.receive_json() == {"kind": "json"}
        assert await sock.receive_text() == "text"

        env = await sock.receive_message()
        assert env.topic == "room:lobby" and env.event == "chat" and env.payload == {"x": 1}

        await sock.reply({"ok": True})
        await sock.emit({"ok": False}, event="broadcast")
        await sock.close(1001, "bye")

        assert fake.accepted == "proto1"
        assert ("json", {"topic": "room:lobby", "event": "reply", "payload": {"ok": True}}) in fake.sent
        assert ("json", {"topic": "room:lobby", "event": "broadcast", "payload": {"ok": False}}) in fake.sent
        assert ("bytes", b"bin") in fake.sent
        assert ("text", "hi") in fake.sent
        assert fake.closed[-1] == (1001, "bye")

    anyio.run(runner)


def test_channelbase_requires_on_message():
    class IncompleteChannel(ChannelBase):
        topic = Topic("room:{room_id}")

    with pytest.raises(TypeError):
        IncompleteChannel(None, topic="room:lobby", params={}, bus=InMemorySocketBus())  # type: ignore[arg-type]


def test_channel_registry_no_match_and_emit():
    import anyio

    class DummyBus:
        def __init__(self):
            self.calls: list[tuple[str, str, str, Any]] = []

        async def publish(self, topic: str, event: str, payload: Any):
            self.calls.append(("publish", topic, event, payload))

        async def emit(self, topic: str, event: str, payload: Any):
            self.calls.append(("emit", topic, event, payload))

    class DummySocket:
        def __init__(self):
            self.sent: list[Any] = []

        async def send_json(self, data: Any):
            self.sent.append(data)

    class EchoChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_message(self, env: MessageEnvelope) -> Any:
            await self.publish({"echo": env.payload})

    bus = DummyBus()
    socket = DummySocket()
    channel = EchoChannel(socket, topic="room:lobby", params={"room_id": "lobby"}, bus=bus, graph=Graph())

    assert EchoChannel.match("nope") is None

    registry = ChannelRegistry()
    registry.add_channel(EchoChannel)
    result = registry.create("unknown", socket=socket, bus=bus, graph=Graph())
    assert result is None

    async def runner():
        await channel.emit({"ping": 1})
        await channel.on_update(MessageEnvelope(topic="room:lobby", event="chat", payload={"x": 2}))

    anyio.run(runner)
    assert ("emit", "room:lobby", "broadcast", {"ping": 1}) in bus.calls
    assert socket.sent[-1]["payload"] == {"x": 2}


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


def test_sockethub_call_without_setup():
    import anyio

    hub = SocketHub("/ws/notsetup")

    async def receive():
        return {}

    async def send(msg):
        return None

    scope = {"type": "websocket", "path": "/ws/notsetup"}
    with pytest.raises(RuntimeError):
        anyio.run(hub, scope, receive, send)


def test_sockethub_connect_non_websocket_scope():
    import anyio

    hub = SocketHub("/ws/connect")
    hub.setup()

    async def receive():
        return {}

    async def send(msg):
        return None

    scope = {"type": "http", "path": "/ws/connect"}
    with pytest.raises(RuntimeError):
        anyio.run(hub.connect, scope, receive, send)


def test_sockethub_unknown_topic_and_leave(test_client):
    hub = SocketHub("/ws/chat")
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:missing", "join"))
            assert ws.receive_json() == TOPIC_NOT_FOUND
            ws.send_bytes(encode_env("room:missing", "leave"))
            assert ws.receive_json() == TOPIC_NOT_FOUND


def test_sockethub_duplicate_join_avoids_double_subscription(test_client):
    bus_holder: dict[str, InMemorySocketBus] = {}

    def bus_factory() -> InMemorySocketBus:
        bus = InMemorySocketBus()
        bus_holder["bus"] = bus
        return bus

    hub = SocketHub("/ws/chat", bus_factory=bus_factory)
    hub.channel(ChatChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join"))
            ws.send_bytes(encode_env("room:lobby", "join"))
            ws.send_bytes(encode_env("room:lobby", "chat", {"text": "hi"}))
            data = ws.receive_json()
            assert data["payload"] == {"text": "hi"}
            bus = bus_holder["bus"]
            assert len(bus._subs["room:lobby"]) == 1


def test_sockethub_reject_on_connect(test_client):
    hub = SocketHub("/ws/reject")

    @hub.on_connect
    async def reject(sock: ISocket):
        await sock.allow_if(False)

    app = Lihil(hub)
    client = test_client(app)
    with client:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/reject"):
                pass
        assert exc.value.code == 4403


def test_sockethub_closes_on_handler_exception(monkeypatch):
    import anyio
    from msgspec.json import encode
    from lihil.socket import hub as hub_module

    messages = [
        encode(MessageEnvelope(topic="boom:lobby", event="join", payload=None)),
        encode(MessageEnvelope(topic="boom:lobby", event="chat", payload="hi")),
    ]

    class FakeWebSocket:
        instances: list["FakeWebSocket"] = []

        def __init__(self, scope, receive, send):
            FakeWebSocket.instances.append(self)
            self.application_state = WebSocketState.CONNECTED
            self.client_state = WebSocketState.CONNECTED
            self.closed: list[tuple[int, str]] = []

        async def accept(self, subprotocol=None):
            return None

        async def receive_bytes(self):
            if not messages:
                raise WebSocketDisconnect()
            return messages.pop(0)

        async def send_bytes(self, data: bytes):
            return None

        async def send_json(self, data: Any):
            return None

        async def close(self, code: int = 1000, reason: str = ""):
            self.closed.append((code, reason))

    monkeypatch.setattr(hub_module, "WebSocket", FakeWebSocket)

    hub = SocketHub("/ws/error")

    class BoomChannel(ChannelBase):
        topic = Topic("boom:{room_id}")

        async def on_message(self, env: MessageEnvelope):
            raise ValueError("boom")

    hub.channel(BoomChannel)
    hub.setup()

    async def receive():
        return {}

    async def send(msg):
        return None

    scope = {"type": "websocket", "path": "/ws/error"}
    with pytest.raises(ValueError):
        anyio.run(hub.connect, scope, receive, send)

    fake = FakeWebSocket.instances[-1]
    assert (1011, "Internal Server Error") in fake.closed


def test_sockethub_close_on_disconnect(monkeypatch):
    import anyio
    from lihil.socket import hub as hub_module

    class FakeWebSocket:
        instances: list["FakeWebSocket"] = []

        def __init__(self, scope, receive, send):
            FakeWebSocket.instances.append(self)
            self.application_state = WebSocketState.CONNECTED
            self.client_state = WebSocketState.CONNECTED
            self.closed: list[tuple[int, str]] = []

        async def accept(self, subprotocol=None):
            return None

        async def receive_bytes(self):
            raise WebSocketDisconnect()

        async def send_bytes(self, data: bytes):
            return None

        async def send_json(self, data: Any):
            return None

        async def close(self, code: int = 1000, reason: str = ""):
            self.closed.append((code, reason))

    monkeypatch.setattr(hub_module, "WebSocket", FakeWebSocket)

    hub = SocketHub("/ws/disconnect")
    hub.setup()

    async def receive():
        return {}

    async def send(msg):
        return None

    scope = {"type": "websocket", "path": "/ws/disconnect"}
    anyio.run(hub.connect, scope, receive, send)

    fake = FakeWebSocket.instances[-1]
    assert (1000, "") in fake.closed
