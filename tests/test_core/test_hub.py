from typing import Any, Awaitable, Callable

import msgspec
import pytest

from lihil import (
    Annotated,
    ChannelBase,
    Graph,
    ISocket,
    Lihil,
    MessageEnvelope,
    Resolver,
    SocketHub,
    Topic,
    error_payload,
    use,
)
from lihil.errors import SockRejectedError
from lihil.socket.hub import (
    EVENT_NOT_FOUND,
    TOPIC_NOT_FOUND,
    ChannelFactory,
    InMemorySocketBus,
    SocketBus,
    SocketSession,
)
from lihil.socket.dispatcher import ChannelDispatcher
from lihil.vendors import WebSocketDisconnect, WebSocketState


def encode_env(
    topic: str,
    event: str,
    payload=None,
    *,
    ref: str | None = None,
    join_ref: str | None = None,
) -> bytes:
    return msgspec.json.encode(
        {
            "topic": topic,
            "event": event,
            "payload": payload,
            "ref": ref,
            "join_ref": join_ref,
        }
    )


def assert_reply(
    data: dict[str, Any],
    *,
    topic: str = "room:lobby",
    ref: str | None = None,
    join_ref: str | None = None,
) -> dict[str, Any]:
    assert data["topic"] == topic
    assert data["event"] == "reply"
    assert data["ref"] == ref
    assert data["join_ref"] == join_ref
    assert isinstance(data["seq"], int)
    return data["payload"]


class ChatChannel(ChannelBase):
    topic = Topic("room:{room_id}")

    async def on_join(self, room_id: str) -> None:
        self.room_id = room_id
        await super().on_join()

    async def on_message(self, env: MessageEnvelope) -> None:
        await self.publish(env.payload, event=env.event)


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


def test_hub_join_and_chat_roundtrip(test_client):
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join", ref="1"))
            ack = assert_reply(ws.receive_json(), ref="1", join_ref="1")
            assert ack == {
                "status": "ok",
                "response": {
                    "topic": "room:lobby",
                    "already_joined": False,
                    "replay_supported": False,
                },
            }

            payload = {"text": "hi"}
            ws.send_bytes(encode_env("room:lobby", "chat", payload, ref="2"))
            data = ws.receive_json()
            assert data["topic"] == "room:lobby"
            assert data["event"] == "chat"
            assert data["payload"] == payload
            assert data["join_ref"] == "1"
            assert data["seq"] == 2


def test_socket_session_injects_topic_params_with_message_scope():
    import anyio

    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)

    async def scenario(session, raw_ws, conn_scope, bus):
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(topic="room:lobby", event="join", ref="join-1"),
                msg_scope,
            )
        channel = session._subscriptions["room:lobby"]
        assert channel.room_id == "lobby"
        assert raw_ws.sent[-1][1]["payload"]["status"] == "ok"

    anyio.run(run_socket_session, hub, scenario)


def test_socket_session_only_injects_declared_join_params():
    import anyio

    class ScopedChannel(ChannelBase):
        topic = Topic("org:{org_id}/room:{room_id}")

        async def on_join(self, room_id: str) -> None:
            self.room_id = room_id
            await super().on_join()

    hub = SocketHub("/ws/chat")
    hub.channel(ScopedChannel)

    async def scenario(session, raw_ws, conn_scope, bus):
        async with conn_scope.ascope() as msg_scope:
            await session.handle_message(
                MessageEnvelope(
                    topic="org:acme/room:lobby",
                    event="join",
                    ref="join-1",
                ),
                msg_scope,
            )
        channel = session._subscriptions["org:acme/room:lobby"]
        assert channel.room_id == "lobby"
        assert raw_ws.sent[-1][1]["payload"]["status"] == "ok"

    anyio.run(run_socket_session, hub, scenario)


def test_socket_session_allows_join_without_topic_params(test_client):
    class StaticJoinChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_join(self) -> None:
            self.joined = True
            await super().on_join()

    hub = SocketHub("/ws/chat")
    hub.channel(StaticJoinChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-1"))
            payload = assert_reply(ws.receive_json(), ref="join-1", join_ref="join-1")
            assert payload["status"] == "ok"


def test_sockethub_rejects_unknown_join_param_at_registration():
    class BadJoinChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_join(self, missing: str) -> None:
            await super().on_join()

    hub = SocketHub("/ws/chat")
    with pytest.raises(TypeError, match="unknown topic parameter"):
        hub.channel(BadJoinChannel)


def test_hub_exit_stops_delivery(test_client):
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join"))
            ws.receive_json()
            ws.send_bytes(encode_env("room:lobby", "exit"))
            exit_ack = assert_reply(ws.receive_json())
            assert exit_ack == {"status": "ok", "response": {"topic": "room:lobby"}}
            ws.send_bytes(encode_env("room:lobby", "chat", {"text": "ignored"}))
            payload = assert_reply(ws.receive_json())
            assert payload["status"] == "error"
            assert payload["error"]["code"] == "not_joined"


def test_hub_chat_without_join_returns_not_joined(test_client):
    hub = SocketHub("/ws/chat")
    hub.channel(ChatChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "chat", {"text": "hi"}))
            payload = assert_reply(ws.receive_json())
            assert payload["status"] == "error"
            assert payload["error"]["code"] == "not_joined"


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
        assert await sock.receive_bytes()

        env = await sock.receive_message()
        assert (
            env.topic == "room:lobby"
            and env.event == "chat"
            and env.payload == {"x": 1}
        )

        await sock.reply(env.topic, {"ok": True})
        await sock.reply(env.topic, {"items": (1, 2, ["x", ("y",)])})
        await sock.emit(env.topic, {"ok": False}, event="broadcast")
        await sock.close(1001, "bye")

        assert fake.accepted == "proto1"
        assert (
            "json",
            {
                "topic": "room:lobby",
                "event": "reply",
                "payload": {"ok": True},
                "ref": None,
                "join_ref": None,
                "event_id": None,
                "seq": 1,
            },
        ) in fake.sent
        assert (
            "json",
            {
                "topic": "room:lobby",
                "event": "broadcast",
                "payload": {"ok": False},
                "ref": None,
                "join_ref": None,
                "event_id": None,
                "seq": 3,
            },
        ) in fake.sent
        assert (
            "json",
            {
                "topic": "room:lobby",
                "event": "reply",
                "payload": {"items": [1, 2, ["x", ["y"]]]},
                "ref": None,
                "join_ref": None,
                "event_id": None,
                "seq": 2,
            },
        ) in fake.sent
        assert ("bytes", b"bin") in fake.sent
        assert ("text", "hi") in fake.sent
        assert fake.closed[-1] == (1001, "bye")

    anyio.run(runner)


def test_channelbase_allows_event_handler_without_on_message():
    class HandlerOnlyChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_chat(self, payload: Any) -> dict[str, Any]:
            return {"echo": payload}

    channel = HandlerOnlyChannel(
        None, topic="room:lobby", bus=InMemorySocketBus(), resolver=Graph()
    )  # type: ignore[arg-type]
    assert channel.resolved_topic == "room:lobby"


def test_socket_session_no_match_and_emit():
    import anyio

    class DummySocket:
        def __init__(self):
            self.sent: list[Any] = []
            self._seq = 0

        async def send_envelope(
            self,
            topic: str,
            event: str,
            payload: Any = None,
            *,
            ref: str | None = None,
            join_ref: str | None = None,
            event_id: str | None = None,
        ):
            self._seq += 1
            self.sent.append(
                {
                    "topic": topic,
                    "event": event,
                    "payload": payload,
                    "ref": ref,
                    "join_ref": join_ref,
                    "event_id": event_id,
                    "seq": self._seq,
                }
            )

        async def reply(
            self,
            topic: str,
            payload: Any,
            event: str = "reply",
            *,
            ref: str | None = None,
            join_ref: str | None = None,
        ):
            await self.send_envelope(topic, event, payload, ref=ref, join_ref=join_ref)

        async def send_reply(
            self,
            topic: str,
            response: Any | None = None,
            *,
            ref: str | None = None,
            join_ref: str | None = None,
        ):
            await self.reply(
                topic,
                {"status": "ok", "response": response or {}},
                ref=ref,
                join_ref=join_ref,
            )

        async def send_error(
            self,
            topic: str,
            code: str,
            *,
            message: str | None = None,
            detail: Any | None = None,
            ref: str | None = None,
            join_ref: str | None = None,
        ):
            await self.reply(
                topic,
                {
                    "status": "error",
                    "error": {
                        "code": code,
                        "message": message or code,
                        "detail": {} if detail is None else detail,
                    },
                },
                ref=ref,
                join_ref=join_ref,
            )

        @property
        def dual_connected(self) -> bool:
            return True

    class EchoChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_message(self, env: MessageEnvelope) -> Any:
            await self.publish({"echo": env.payload})

    bus = InMemorySocketBus()
    socket = DummySocket()
    factory = ChannelFactory(
        topic_pattern=EchoChannel.topic,
        channel_type=EchoChannel,
    )
    session = SocketSession(
        socket=socket,
        bus=bus,
        resolver=Graph(),
        channel_fractories=[factory],
        connect_cb=None,
        disconnect_cb=None,
    )

    assert factory.extra_topic_params("nope") is None
    assert factory.extra_topic_params("room:lobby") == {"room_id": "lobby"}

    async def runner():
        await session.handle_message(
            MessageEnvelope(topic="nope", event="chat", payload={"x": 0}),
            session._resolver,
        )
        await session.handle_message(
            MessageEnvelope(topic="room:lobby", event="join", payload=None),
            session._resolver,
        )
        await session.handle_message(
            MessageEnvelope(topic="room:lobby", event="chat", payload={"x": 2}),
            session._resolver,
        )
        await session.handle_message(
            MessageEnvelope(topic="room:lobby", event="exit", payload=None),
            session._resolver,
        )

    anyio.run(runner)
    assert socket.sent[0]["payload"]["error"]["code"] == "topic_not_found"
    assert socket.sent[-2]["payload"] == {"echo": {"x": 2}}
    assert "room:lobby" not in bus._subs


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

        async def on_join(self, **params: str) -> None:
            ProbeChannel.seen_buses.append(self.bus)  # type: ignore[arg-type]
            await super().on_join(**params)

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
            ws.receive_json()
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
                return EVENT_NOT_FOUND
            await self.publish(env.payload, event=env.event)

    hub = SocketHub("/ws/chat")
    hub.channel(GuardedChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join"))
            ws.receive_json()
            ws.send_bytes(encode_env("room:lobby", "unknown", {"x": 1}))
            payload = assert_reply(ws.receive_json())
            assert payload["status"] == "error"
            assert payload["error"]["code"] == "event_not_found"


def test_hub_dispatches_on_event_handler(test_client):
    class CommandChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_ping(self, payload: dict[str, Any], env: MessageEnvelope):
            return {"payload": payload, "ref": env.ref}

    hub = SocketHub("/ws/chat")
    hub.channel(CommandChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-1"))
            ws.receive_json()

            ws.send_bytes(
                encode_env("room:lobby", "ping", {"ok": True}, ref="cmd-1")
            )
            payload = assert_reply(ws.receive_json(), ref="cmd-1", join_ref="join-1")
            assert payload == {
                "status": "ok",
                "response": {"payload": {"ok": True}, "ref": "cmd-1"},
            }


def test_hub_dispatch_converts_typed_payload_and_struct_response(test_client):
    class PingPayload(msgspec.Struct):
        ok: bool

    class PingResponse(msgspec.Struct):
        accepted: bool

    class CommandChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_ping(self, payload: PingPayload) -> PingResponse:
            return PingResponse(accepted=payload.ok)

    hub = SocketHub("/ws/chat")
    hub.channel(CommandChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-1"))
            ws.receive_json()

            ws.send_bytes(
                encode_env("room:lobby", "ping", {"ok": True}, ref="cmd-1")
            )
            payload = assert_reply(ws.receive_json(), ref="cmd-1", join_ref="join-1")
            assert payload == {"status": "ok", "response": {"accepted": True}}


def test_hub_dispatch_invalid_payload_returns_error(test_client):
    class PingPayload(msgspec.Struct):
        ok: bool

    class CommandChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_ping(self, payload: PingPayload) -> None:
            return None

    hub = SocketHub("/ws/chat")
    hub.channel(CommandChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-1"))
            ws.receive_json()

            ws.send_bytes(encode_env("room:lobby", "ping", {"ok": "yes"}, ref="cmd-1"))
            payload = assert_reply(ws.receive_json(), ref="cmd-1", join_ref="join-1")
            assert payload["status"] == "error"
            assert payload["error"]["code"] == "invalid_payload"


def test_hub_rejects_unsupported_event_handler_signature():
    class CommandChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_ping(
            self,
            payload: dict[str, Any],
            env: MessageEnvelope,
            extra: str,
        ) -> None:
            return None

    hub = SocketHub("/ws/chat")
    with pytest.raises(TypeError, match="accepts at most payload and env"):
        hub.channel(CommandChannel)


def test_error_payload_preserves_explicit_falsy_detail():
    assert error_payload("internal_error").error.detail == {}
    assert error_payload("internal_error", detail=None).error.detail is None
    assert error_payload("internal_error", detail=False).error.detail is False
    assert error_payload("internal_error", detail=0).error.detail == 0


def test_channelbase_default_helpers_and_callbacks():
    import anyio

    class FakeSocket:
        def __init__(self):
            self.sent: list[dict[str, Any]] = []

        @property
        def dual_connected(self) -> bool:
            return True

        async def send_envelope(
            self,
            topic: str,
            event: str,
            payload: Any = None,
            **kwargs: Any,
        ):
            self.sent.append(
                {"topic": topic, "event": event, "payload": payload, **kwargs}
            )

    class HelperChannel(ChannelBase):
        topic = Topic("room:{room_id}")

    async def runner():
        socket = FakeSocket()
        bus = InMemorySocketBus()
        channel = HelperChannel(
            socket,  # type: ignore[arg-type]
            topic="room:lobby",
            bus=bus,
            resolver=Graph(),
        )

        assert HelperChannel.match("room:lobby") == {"room_id": "lobby"}
        assert HelperChannel.match("other:lobby") is None
        assert await channel.on_message(MessageEnvelope(topic="room:lobby", event="x")) is EVENT_NOT_FOUND
        assert await channel.replay_after("evt-1") == []

        channel.set_join_ref("join-1")
        await channel.on_update(
            MessageEnvelope(topic="room:lobby", event="chat", payload={"ok": True})
        )
        assert socket.sent[-1]["join_ref"] == "join-1"

        await channel.publish({"via": "publish"}, event="chat")
        await channel.emit({"via": "emit"}, event="chat")
        await anyio.sleep(0)

    anyio.run(runner)


def test_channelbase_task_edges():
    import anyio

    class FakeSocket:
        def __init__(self, connected: bool = True):
            self.connected = connected
            self.sent: list[dict[str, Any]] = []

        @property
        def dual_connected(self) -> bool:
            return self.connected

        async def send_envelope(self, *args, **kwargs):
            self.sent.append({"args": args, "kwargs": kwargs})

    class TaskChannel(ChannelBase):
        topic = Topic("room:{room_id}")

    async def runner():
        channel = TaskChannel(
            FakeSocket(),  # type: ignore[arg-type]
            topic="room:lobby",
            bus=InMemorySocketBus(),
            resolver=Graph(),
        )

        await channel.cancel_task("missing")

        async def pending():
            await anyio.sleep_forever()

        first = channel.start_task("work", pending())
        with pytest.raises(ValueError, match="already exists"):
            channel.start_task("work", pending())
        await channel.cancel_task("work")
        assert first.cancelled()

        async def fail():
            raise RuntimeError("boom")

        disconnected_socket = FakeSocket(connected=False)
        disconnected = TaskChannel(
            disconnected_socket,  # type: ignore[arg-type]
            topic="room:lobby",
            bus=InMemorySocketBus(),
            resolver=Graph(),
        )
        disconnected.start_task("fail", fail())
        await anyio.sleep(0.01)
        assert disconnected_socket.sent == []

    anyio.run(runner)


def test_dispatcher_join_and_handler_signature_edges():
    import anyio

    dispatcher = ChannelDispatcher()

    class AnyJoinChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_join(self, **params: str) -> None:
            return None

    any_join = AnyJoinChannel(
        None,  # type: ignore[arg-type]
        topic="room:lobby",
        bus=InMemorySocketBus(),
        resolver=Graph(),
    )
    assert dispatcher.join_kwargs(any_join, {"room_id": "lobby"}) == {
        "room_id": "lobby"
    }

    class BadJoinChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_join(self, *params: str) -> None:
            return None

    with pytest.raises(TypeError, match="variadic positional"):
        dispatcher.validate(BadJoinChannel)

    class KeywordEventChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_ping(self, *, payload: dict[str, Any]) -> None:
            return None

    with pytest.raises(TypeError, match="only supports positional"):
        dispatcher.validate(KeywordEventChannel)

    class BadEnvChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_ping(self, payload: dict[str, Any], other: dict[str, Any]) -> None:
            return None

    with pytest.raises(TypeError, match="second parameter must be env"):
        dispatcher.validate(BadEnvChannel)

    class DefaultChannel(ChannelBase):
        topic = Topic("room:{room_id}")

    default_channel = DefaultChannel(
        None,  # type: ignore[arg-type]
        topic="room:lobby",
        bus=InMemorySocketBus(),
        resolver=Graph(),
    )
    assert (
        anyio.run(
            dispatcher.dispatch,
            default_channel,
            MessageEnvelope(topic="room:lobby", event="missing"),
        )
        is EVENT_NOT_FOUND
    )

    class BindingChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_env(self, env) -> None:
            self.seen_env = env

        async def on_any(self, payload: Any) -> None:
            self.seen_payload = payload

    binding_channel = BindingChannel(
        None,  # type: ignore[arg-type]
        topic="room:lobby",
        bus=InMemorySocketBus(),
        resolver=Graph(),
    )
    env_msg = MessageEnvelope(topic="room:lobby", event="env", payload={"ok": True})
    anyio.run(dispatcher.dispatch, binding_channel, env_msg)
    assert binding_channel.seen_env is env_msg

    any_msg = MessageEnvelope(topic="room:lobby", event="any", payload={"ok": True})
    anyio.run(dispatcher.dispatch, binding_channel, any_msg)
    assert binding_channel.seen_payload == {"ok": True}


def test_in_memory_bus_removes_topic_when_only_callback_dies():
    import anyio

    async def runner():
        bus = InMemorySocketBus()

        async def dead(_env):
            raise RuntimeError("dead")

        await bus.subscribe("room:lobby", dead)
        await bus.publish("room:lobby", "event", {})
        assert "room:lobby" not in bus._subs

    anyio.run(runner)


def test_socket_session_closes_with_1011_on_unexpected_exit():
    import anyio

    class FakeSocket:
        def __init__(self):
            self.closed: list[tuple[int, str]] = []

        @property
        def dual_connected(self) -> bool:
            return True

        async def accept(self):
            return None

        async def close(self, code: int = 1000, reason: str = ""):
            self.closed.append((code, reason))

    async def runner():
        socket = FakeSocket()
        session = SocketSession(
            socket=socket,  # type: ignore[arg-type]
            bus=InMemorySocketBus(),
            resolver=Graph(),
            channel_fractories=[],
            connect_cb=None,
            disconnect_cb=None,
        )

        handled = await session.__aexit__(RuntimeError, RuntimeError("boom"), None)

        assert handled is False
        assert socket.closed == [(1011, "Internal Server Error")]

    anyio.run(runner)


def test_sockethub_create_socket_session_reraises_base_exception():
    import anyio

    async def runner():
        hub = SocketHub("/ws")
        sent = []
        received_connect = False

        async def receive():
            nonlocal received_connect
            if not received_connect:
                received_connect = True
                return {"type": "websocket.connect"}
            return {"type": "websocket.disconnect", "code": 1000}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "websocket",
            "path": "/ws",
            "headers": [],
            "query_string": b"",
            "path_params": {},
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "scheme": "ws",
            "subprotocols": [],
        }

        with pytest.raises(RuntimeError, match="boom"):
            async with hub.create_socket_session(scope, receive, send):
                raise RuntimeError("boom")

        assert {"type": "websocket.close", "code": 1011, "reason": "Internal Server Error"} in sent

    anyio.run(runner)


def test_hub_channel_constructor_uses_graph_dependencies(test_client):
    class Service:
        pass

    class InjectedChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        def __init__(
            self,
            service: Service,
            socket: ISocket,
            *,
            topic: str,
            bus: InMemorySocketBus,
            resolver: Resolver,
        ):
            super().__init__(socket, topic=topic, bus=bus, resolver=resolver)
            self.service = service

        async def on_ping(self) -> dict[str, bool]:
            return {"injected": isinstance(self.service, Service)}

    hub = SocketHub("/ws/chat")
    hub.add_nodes(Service)
    hub.channel(InjectedChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-1"))
            ws.receive_json()
            ws.send_bytes(encode_env("room:lobby", "ping", ref="cmd-1"))
            payload = assert_reply(ws.receive_json(), ref="cmd-1", join_ref="join-1")
            assert payload == {"status": "ok", "response": {"injected": True}}


def test_hub_replays_after_join_ack(test_client):
    class ReplayChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def replay_after(self, event_id: str | None) -> list[MessageEnvelope]:
            return [
                MessageEnvelope(
                    topic=self.resolved_topic,
                    event="message",
                    payload={"after": event_id},
                    event_id="evt-2",
                )
            ]

    hub = SocketHub("/ws/chat")
    hub.channel(ReplayChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(
                encode_env(
                    "room:lobby",
                    "join",
                    {"last_event_id": "evt-1"},
                    ref="join-1",
                )
            )
            ack = assert_reply(ws.receive_json(), ref="join-1", join_ref="join-1")
            assert ack["response"]["replay_supported"] is True

            replayed = ws.receive_json()
            assert replayed["topic"] == "room:lobby"
            assert replayed["event"] == "message"
            assert replayed["payload"] == {"after": "evt-1"}
            assert replayed["join_ref"] == "join-1"
            assert replayed["event_id"] == "evt-2"


def test_channel_tasks_cancel_on_close():
    import anyio

    class FakeSocket:
        @property
        def dual_connected(self) -> bool:
            return True

        async def send_envelope(self, *args, **kwargs):
            return None

    class TaskChannel(ChannelBase):
        topic = Topic("room:{room_id}")

    async def runner():
        cancelled = False

        async def work():
            nonlocal cancelled
            try:
                await anyio.sleep_forever()
            except BaseException:
                cancelled = True
                raise

        channel = TaskChannel(
            FakeSocket(),  # type: ignore[arg-type]
            topic="room:lobby",
            bus=InMemorySocketBus(),
            resolver=Graph(),
        )
        channel.start_task("work", work())
        await channel.aclose()

        assert cancelled is True
        assert channel._tasks == {}

    anyio.run(runner)


def test_channel_task_exception_sends_error_envelope():
    import anyio

    class FakeSocket:
        def __init__(self):
            self.sent: list[dict[str, Any]] = []

        @property
        def dual_connected(self) -> bool:
            return True

        async def send_envelope(
            self,
            topic: str,
            event: str,
            payload: Any = None,
            **kwargs,
        ):
            self.sent.append({"topic": topic, "event": event, "payload": payload})

    class TaskChannel(ChannelBase):
        topic = Topic("room:{room_id}")

    async def runner():
        async def fail():
            raise RuntimeError("boom")

        socket = FakeSocket()
        channel = TaskChannel(
            socket,  # type: ignore[arg-type]
            topic="room:lobby",
            bus=InMemorySocketBus(),
            resolver=Graph(),
        )
        channel.start_task("work", fail())
        await anyio.sleep(0.01)

        assert channel._tasks == {}
        assert socket.sent[-1]["event"] == "error"
        assert socket.sent[-1]["payload"]["error"]["code"] == "internal_error"
        assert socket.sent[-1]["payload"]["error"]["detail"]["task"] == "work"

    anyio.run(runner)


def test_channel_task_exception_can_close_socket():
    import anyio

    class FakeSocket:
        def __init__(self):
            self.closed: list[tuple[int, str]] = []
            self.sent: list[dict[str, Any]] = []

        @property
        def dual_connected(self) -> bool:
            return True

        async def close(self, code: int = 1000, reason: str = ""):
            self.closed.append((code, reason))

        async def send_envelope(self, *args, **kwargs):
            self.sent.append({"args": args, "kwargs": kwargs})

    class TaskChannel(ChannelBase):
        topic = Topic("room:{room_id}")
        task_exception_policy = "close"
        task_exception_close_code = 4500
        task_exception_close_reason = "Task failed"

    async def runner():
        async def fail():
            raise RuntimeError("boom")

        socket = FakeSocket()
        channel = TaskChannel(
            socket,  # type: ignore[arg-type]
            topic="room:lobby",
            bus=InMemorySocketBus(),
            resolver=Graph(),
        )
        channel.start_task("work", fail())
        await anyio.sleep(0.01)

        assert socket.closed == [(4500, "Task failed")]
        assert socket.sent == []

    anyio.run(runner)


def test_channel_task_exception_can_ignore_after_logging(caplog):
    import anyio
    import logging

    class FakeSocket:
        def __init__(self):
            self.closed: list[tuple[int, str]] = []
            self.sent: list[dict[str, Any]] = []

        @property
        def dual_connected(self) -> bool:
            return True

        async def close(self, code: int = 1000, reason: str = ""):
            self.closed.append((code, reason))

        async def send_envelope(self, *args, **kwargs):
            self.sent.append({"args": args, "kwargs": kwargs})

    class TaskChannel(ChannelBase):
        topic = Topic("room:{room_id}")
        task_exception_policy = "ignore"

    async def runner():
        async def fail():
            raise RuntimeError("boom")

        socket = FakeSocket()
        channel = TaskChannel(
            socket,  # type: ignore[arg-type]
            topic="room:lobby",
            bus=InMemorySocketBus(),
            resolver=Graph(),
        )
        with caplog.at_level(logging.ERROR, logger="lihil.socket.channel"):
            channel.start_task("work", fail())
            await anyio.sleep(0.01)

        assert socket.closed == []
        assert socket.sent == []
        assert "channel task 'work' failed on room:lobby" in caplog.text

    anyio.run(runner)


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


def test_sockethub_unknown_topic_and_exit(test_client):
    hub = SocketHub("/ws/chat")
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:missing", "join"))
            data = ws.receive_json()
            assert data["payload"]["error"]["code"] == TOPIC_NOT_FOUND.error.code
            ws.send_bytes(encode_env("room:missing", "exit"))
            data = ws.receive_json()
            assert data["payload"]["error"]["code"] == TOPIC_NOT_FOUND.error.code


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
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-1"))
            first_ack = assert_reply(ws.receive_json(), ref="join-1", join_ref="join-1")
            assert first_ack["response"]["already_joined"] is False
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-2"))
            second_ack = assert_reply(ws.receive_json(), ref="join-2", join_ref="join-1")
            assert second_ack["response"]["already_joined"] is True
            ws.send_bytes(encode_env("room:lobby", "chat", {"text": "hi"}))
            data = ws.receive_json()
            assert data["payload"] == {"text": "hi"}
            bus = bus_holder["bus"]
            assert len(bus._subs["room:lobby"]) == 1


def test_sockethub_skips_non_matching_channel_factories(test_client):
    class OtherChannel(ChannelBase):
        topic = Topic("other:{room_id}")

    hub = SocketHub("/ws/chat")
    hub.channel(OtherChannel)
    hub.channel(ChatChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-1"))
            payload = assert_reply(ws.receive_json(), ref="join-1", join_ref="join-1")
            assert payload["status"] == "ok"


def test_sockethub_join_rejection_cleans_partial_subscription(test_client):
    bus_holder: dict[str, InMemorySocketBus] = {}

    def bus_factory() -> InMemorySocketBus:
        bus = InMemorySocketBus()
        bus_holder["bus"] = bus
        return bus

    class RejectingChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_join(self, **params: str) -> None:
            await super().on_join(**params)
            raise SockRejectedError("nope")

    hub = SocketHub("/ws/chat", bus_factory=bus_factory)
    hub.channel(RejectingChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-1"))
            payload = assert_reply(ws.receive_json(), ref="join-1")
            assert payload["status"] == "error"
            assert payload["error"]["code"] == "join_rejected"
            assert "room:lobby" not in bus_holder["bus"]._subs


def test_sockethub_join_exception_cleans_partial_subscription(test_client):
    bus_holder: dict[str, InMemorySocketBus] = {}

    def bus_factory() -> InMemorySocketBus:
        bus = InMemorySocketBus()
        bus_holder["bus"] = bus
        return bus

    class BrokenJoinChannel(ChannelBase):
        topic = Topic("room:{room_id}")

        async def on_join(self, **params: str) -> None:
            await super().on_join(**params)
            raise RuntimeError("join exploded")

    hub = SocketHub("/ws/chat", bus_factory=bus_factory)
    hub.channel(BrokenJoinChannel)
    app = Lihil(hub)

    client = test_client(app)
    with client:
        with client.websocket_connect("/ws/chat") as ws:
            ws.send_bytes(encode_env("room:lobby", "join", ref="join-1"))
            payload = assert_reply(ws.receive_json(), ref="join-1")
            assert payload["status"] == "error"
            assert payload["error"]["code"] == "internal_error"
            assert payload["error"]["detail"]["error"] == "join exploded"
            assert "room:lobby" not in bus_holder["bus"]._subs


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


def test_sockethub_handler_exception_returns_error(monkeypatch):
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
            self.sent: list[Any] = []

        async def accept(self, subprotocol=None):
            return None

        async def receive_bytes(self):
            if not messages:
                raise WebSocketDisconnect()
            return messages.pop(0)

        async def send_bytes(self, data: bytes):
            return None

        async def send_json(self, data: Any):
            self.sent.append(data)

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
    anyio.run(hub, scope, receive, send)

    fake = FakeWebSocket.instances[-1]
    assert (1011, "Internal Server Error") not in fake.closed
    assert fake.sent[-1]["payload"]["status"] == "error"
    assert fake.sent[-1]["payload"]["error"]["code"] == "internal_error"


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
    anyio.run(hub, scope, receive, send)

    fake = FakeWebSocket.instances[-1]
    assert (1000, "") in fake.closed
