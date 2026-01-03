from typing import Any, Awaitable, Callable

import msgspec
import pytest

from lihil import (
    Annotated,
    ChannelBase,
    Graph,
    ISocket,
    MessageEnvelope,
    Resolver,
    SocketHub,
    Topic,
    use,
)
from lihil.errors import SockRejectedError
from lihil.socket.hub import (
    ChannelFactory,
    InMemorySocketBus,
    SocketBus,
    SocketSession,
    TOPIC_NOT_FOUND,
)
from lihil.vendors import WebSocketDisconnect, WebSocketState


class RecordingWebSocket:
    def __init__(self):
        self.application_state = WebSocketState.CONNECTED
        self.client_state = WebSocketState.CONNECTED
        self.headers = {}
        self.state = {}
        self.query_params = {}
        self.path_params = {}
        self.url = "ws://test/"
        self.accepted: str | None = None
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


def make_recording_socket() -> tuple[ISocket, RecordingWebSocket]:
    ws = RecordingWebSocket()
    return ISocket(ws), ws


async def run_socket_session(
    hub: SocketHub,
    fn: Callable[[SocketSession, RecordingWebSocket, Resolver, SocketBus], Awaitable[None]],
) -> None:
    socket, raw_ws = make_recording_socket()
    async with hub.graph.ascope() as conn_scope:
        bus = await conn_scope.aresolve(SocketBus)
        session = SocketSession(
            socket=socket,
            bus=bus,
            resolver=conn_scope,
            channel_fractories=hub._channel_factories,
            connect_cb=hub._on_connect,
            disconnect_cb=hub._on_disconnect,
        )
        await session.__aenter__()
        try:
            await fn(session, raw_ws, conn_scope, bus)
        finally:
            await session.__aexit__(None, None, None)


class ChatChannel(ChannelBase):
    topic = Topic("room:{room_id}")

    async def on_join(self, room_id: str):
        self.room_id = room_id
        await super().on_join()

    async def on_message(self, env: MessageEnvelope) -> None:
        # Fan out to the room via the bus.
        await self.publish(env.payload, event=env.event)


def test_hub_join_and_chat_roundtrip():
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)
    payload = {"text": "hi"}

    async def scenario(session, raw_ws, conn_scope, bus):
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="join", payload=None),
                msg_scope,
            )
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="chat", payload=payload),
                msg_scope,
            )

        assert raw_ws.sent[-1] == (
            "json",
            {"topic": "room:lobby", "event": "chat", "payload": payload},
        )

    import anyio

    anyio.run(run_socket_session, hub, scenario)


def test_hub_leave_stops_delivery():
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)

    async def scenario(session, raw_ws, conn_scope, bus):
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="join", payload=None),
                msg_scope,
            )
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="exit", payload=None),
                msg_scope,
            )
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(
                    topic="room:lobby", event="chat", payload={"text": "ignored"}
                ),
                msg_scope,
            )

        assert not session._subscriptions
        assert not bus._subs
        assert raw_ws.sent[-1] == ("json", TOPIC_NOT_FOUND)

    import anyio

    anyio.run(run_socket_session, hub, scenario)


def test_hub_chat_without_join_returns_404():
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)

    async def scenario(session, raw_ws, conn_scope, bus):
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="chat", payload={"text": "hi"}),
                msg_scope,
            )
        assert raw_ws.sent[-1] == ("json", TOPIC_NOT_FOUND)

    import anyio

    anyio.run(run_socket_session, hub, scenario)


def test_hub_hooks_run():
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)
    flags: dict[str, bool] = {"connect": False, "disconnect": False}

    @hub.on_connect
    async def _on_connect(sock):
        flags["connect"] = True

    @hub.on_disconnect
    async def _on_disconnect(sock):
        flags["disconnect"] = True

    import anyio

    async def scenario(session, raw_ws, conn_scope, bus):
        assert flags["connect"] is True

    anyio.run(run_socket_session, hub, scenario)
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
    import asyncio

    import anyio

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
    import anyio
    from msgspec.json import encode

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
            return encode(
                MessageEnvelope(topic="room:lobby", event="chat", payload={"x": 1})
            )

    async def runner():
        fake = FakeWS()
        sock = ISocket(fake)

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
        assert (
            env.topic == "room:lobby"
            and env.event == "chat"
            and env.payload == {"x": 1}
        )

        await sock.reply(env.topic, {"ok": True})
        await sock.emit(env.topic, {"ok": False}, event="broadcast")
        await sock.close(1001, "bye")

        assert fake.accepted == "proto1"
        assert (
            "json",
            {"topic": "room:lobby", "event": "reply", "payload": {"ok": True}},
        ) in fake.sent
        assert (
            "json",
            {"topic": "room:lobby", "event": "broadcast", "payload": {"ok": False}},
        ) in fake.sent
        assert ("bytes", b"bin") in fake.sent
        assert ("text", "hi") in fake.sent
        assert fake.closed[-1] == (1001, "bye")

    anyio.run(runner)


def test_channelbase_requires_on_message():
    class IncompleteChannel(ChannelBase):
        topic = Topic("room:{room_id}")

    with pytest.raises(TypeError):
        sock, _ = make_recording_socket()
        IncompleteChannel(  # type: ignore[arg-type]
            sock, topic="room:lobby", bus=InMemorySocketBus(), resolver=Graph()
        )


def test_socket_session_no_match_and_emit():
    import anyio

    class DummySocket:
        def __init__(self):
            self.sent: list[Any] = []

        async def send_json(self, data: Any):
            self.sent.append(data)

    class EchoChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_join(self, **kwargs):
            await super().on_join()

        async def on_message(self, env: MessageEnvelope) -> Any:
            await self.publish({"echo": env.payload})

    bus = InMemorySocketBus()
    socket = DummySocket()
    resolver = Graph()
    faq = ChannelFactory(
        topic_pattern=EchoChannel.topic,
        channel_type=EchoChannel,
        channel_factory=EchoChannel,
    )
    session = SocketSession(
        socket=socket,
        bus=bus,
        resolver=resolver,
        channel_fractories=[faq],
        connect_cb=None,
        disconnect_cb=None,
    )

    assert faq.extract_topic_params("nope") is None
    assert faq.extract_topic_params("room:lobby") == {"room_id": "lobby"}

    async def runner():
        async with resolver.ascope() as scope:
            await session.handle_message(
                MessageEnvelope(topic="nope", event="chat", payload={"x": 0}),
                scope,
            )
        async with resolver.ascope() as scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="join", payload=None),
                scope,
            )
        async with resolver.ascope() as scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="chat", payload={"x": 2}),
                scope,
            )
        async with resolver.ascope() as scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="exit", payload=None),
                scope,
            )

    anyio.run(runner)
    assert socket.sent[0] == TOPIC_NOT_FOUND
    assert socket.sent[-1]["payload"] == {"echo": {"x": 2}}
    assert "room:lobby" not in bus._subs


def test_hub_bus_factory_with_dependency():
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

        async def on_join(self, room_id: str) -> None:
            ProbeChannel.seen_buses.append(self.bus)  # type: ignore[arg-type]
            await super().on_join()

        async def on_message(self, env: MessageEnvelope) -> None:
            await self.publish(env.payload, event=env.event)

    hub = SocketHub("/ws/chat", bus_factory=build_bus)
    hub.add_nodes(build_kafka, build_bus)
    hub.channel(ProbeChannel)
    ProbeChannel.seen_buses.clear()

    import anyio

    async def scenario(session, raw_ws, conn_scope, bus):
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="join", payload=None),
                msg_scope,
            )
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(
                    topic="room:lobby", event="chat", payload={"text": "hi"}
                ),
                msg_scope,
            )
        assert raw_ws.sent[-1][1]["payload"] == {"text": "hi"}

    anyio.run(run_socket_session, hub, scenario)

    assert build_calls == {"kafka": 1, "bus": 1}
    assert len(ProbeChannel.seen_buses) == 1
    bus = ProbeChannel.seen_buses[0]
    assert isinstance(bus, InMemorySocketBus)
    assert hasattr(bus, "kafka") and isinstance(bus.kafka, FakeKafka)


def test_hub_unknown_event_rejected():
    class GuardedChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_join(self, **kwargs):
            await super().on_join()

        async def on_message(self, env: MessageEnvelope) -> dict[str, Any] | None:
            if env.event != "chat":
                return {"code": 4404, "reason": "Event not found"}
            await self.publish(env.payload, event=env.event)

    hub = SocketHub("/ws/chat")
    hub.channel(GuardedChannel)

    import anyio

    async def scenario(session, raw_ws, conn_scope, bus):
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="join", payload=None),
                msg_scope,
            )
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="unknown", payload={"x": 1}),
                msg_scope,
            )
        decoded = msgspec.json.decode(raw_ws.sent[-1][1])
        assert decoded == {"code": 4404, "reason": "Event not found"}

    anyio.run(run_socket_session, hub, scenario)


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
        anyio.run(hub, scope, receive, send)


def test_sockethub_unknown_topic_and_leave():
    hub = SocketHub("/ws/chat")

    import anyio

    async def scenario(session, raw_ws, conn_scope, bus):
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:missing", event="join", payload=None),
                msg_scope,
            )
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:missing", event="exit", payload=None),
                msg_scope,
            )
        assert raw_ws.sent[0] == ("json", TOPIC_NOT_FOUND)
        assert raw_ws.sent[-1] == ("json", TOPIC_NOT_FOUND)

    anyio.run(run_socket_session, hub, scenario)


def test_sockethub_duplicate_join_avoids_double_subscription():
    def bus_factory() -> InMemorySocketBus:
        return InMemorySocketBus()

    hub = SocketHub("/ws/chat", bus_factory=bus_factory)
    hub.channel(ChatChannel)
    import anyio

    async def scenario(session, raw_ws, conn_scope, bus):
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="join", payload=None),
                msg_scope,
            )
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="join", payload=None),
                msg_scope,
            )
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="chat", payload={"text": "hi"}),
                msg_scope,
            )
        assert raw_ws.sent[-1][1]["payload"] == {"text": "hi"}
        assert len(bus._subs["room:lobby"]) == 1

    anyio.run(run_socket_session, hub, scenario)


def test_sockethub_reject_on_connect():
    hub = SocketHub("/ws/reject")

    @hub.on_connect
    async def reject(sock: ISocket):
        await sock.allow_if(False)

    socket, raw_ws = make_recording_socket()
    session = SocketSession(
        socket=socket,
        bus=InMemorySocketBus(),
        resolver=Graph(),
        channel_fractories=hub._channel_factories,
        connect_cb=hub._on_connect,
        disconnect_cb=hub._on_disconnect,
    )

    import anyio

    with pytest.raises(SockRejectedError):
        anyio.run(session.__aenter__)
    assert raw_ws.closed[-1][0] == 4403


def test_sockethub_closes_on_handler_exception():
    hub = SocketHub("/ws/error")

    class BoomChannel(ChannelBase):
        topic = Topic("boom:{room_id}")

        async def on_join(self, **kwargs):
            await super().on_join()

        async def on_message(self, env: MessageEnvelope):
            raise ValueError("boom")

    hub.channel(BoomChannel)

    socket, raw_ws = make_recording_socket()
    resolver = Graph()
    session = SocketSession(
        socket=socket,
        bus=InMemorySocketBus(),
        resolver=resolver,
        channel_fractories=hub._channel_factories,
        connect_cb=None,
        disconnect_cb=None,
    )

    import anyio

    async def runner():
        await session.__aenter__()
        async with resolver.ascope() as scope:
            await session.handle_message(
                MessageEnvelope(topic="boom:lobby", event="join", payload=None),
                scope,
            )
        with pytest.raises(ValueError) as excinfo:
            async with resolver.ascope() as scope:
                await session.handle_message(
                    MessageEnvelope(topic="boom:lobby", event="chat", payload="hi"),
                    scope,
                )
        await session.__aexit__(ValueError, excinfo.value, excinfo.value.__traceback__)
        assert (1011, "Internal Server Error") in raw_ws.closed

    anyio.run(runner)


def test_sockethub_close_on_disconnect():
    socket, raw_ws = make_recording_socket()
    session = SocketSession(
        socket=socket,
        bus=InMemorySocketBus(),
        resolver=Graph(),
        channel_fractories=[],
        connect_cb=None,
        disconnect_cb=None,
    )

    import anyio

    async def runner():
        await session.__aenter__()
        exc = WebSocketDisconnect()
        await session.__aexit__(WebSocketDisconnect, exc, exc.__traceback__)
        assert (1000, "") in raw_ws.closed

    anyio.run(runner)
