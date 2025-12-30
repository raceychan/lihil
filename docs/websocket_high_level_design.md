# WebSocket High-Level Route Redesign

Goal: cleanly split low-level and managed (channel-based) websocket APIs without requiring dummy handlers.

## Current Pain Points
- `WebSocketRoute` mixes low-level (user coroutine) and managed features (`on_connect/on_disconnect/channel`).
- Managed mode still demands a handler function, so users add no-op callbacks.
- `WSManagedEndpoint` inherits from `WebSocketEndpoint`, forcing a `func` that is unused.

## Proposed Shape
- **Low-level**: keep `WebSocketRoute` focused on direct socket handlers; requires an explicit endpoint func, no channels/hooks.
- **High-level**: introduce `SocketHub` inheriting `RouteBase`, with:
  - Hooks: `on_connect`, `on_disconnect`.
  - Channels: `channel(pattern).on_join/on_exit/on_receive`.
  - No user-supplied handler required; internal managed loop drives dispatch.
  - Middlewares/plugins supported as needed.
  - Composition: ability to merge/include other hubs (similar to route include), e.g. `hub.include(subhub, parent_prefix=...)` to reuse channel trees.

## Migration Plan (sketch)
1. Implement `SocketHub` with internal managed endpoint (no `func` required).
2. Refactor managed logic out of `WebSocketRoute` into the new class.
3. Update demo/tests to use the new high-level route; keep low-level tests on `WebSocketRoute`.
4. Consider shims/deprecations for existing managed APIs on `WebSocketRoute`.

## Minimal `SocketHub` sketch (for implementation)

```python
class SocketHub(RouteBase):
    def __init__(self, path: str = "", *, graph: Graph | None = None, middlewares=None):
        super().__init__(path, graph=graph, middlewares=middlewares)
        self._on_connect: IAsyncFunc[..., None] | None = None
        self._on_disconnect: IAsyncFunc[..., None] | None = None
        self._channels: list[Channel] = []
        self.call_stack: ASGIApp | None = None

    def channel(self, pattern: str) -> Channel:
        ch = Channel(pattern)
        self._channels.append(ch)
        self._channels.sort(key=lambda c: c.topic_pattern.count("{"), reverse=True)
        return ch

    def on_connect(self, func: IAsyncFunc[..., None]) -> IAsyncFunc[..., None]:
        self._on_connect = func
        return func

    def on_disconnect(self, func: IAsyncFunc[..., None]) -> IAsyncFunc[..., None]:
        self._on_disconnect = func
        return func

    def setup(self, graph: Graph | None = None, workers: ThreadPoolExecutor | None = None):
        super().setup(graph=graph, workers=workers)
        self.call_stack = self.chainup_middlewares(self._dispatch)
        self._is_setup = True

    async def _dispatch(self, scope: IScope, receive: IReceive, send: ISend) -> None:
        if scope["type"] != "websocket":
            raise RuntimeError("SocketHub only handles websocket scope")
        sock = ISocket(scope, receive, send)
        if self._on_connect:
            await self._on_connect(sock)
        await sock.accept()
        joined: set[Channel] = set()
        try:
            while True:
                env = MessageEnvelope.from_raw(await sock.receive_json())
                ch, params = self._match_channel(env.topic)
                if not ch or not params:
                    await sock.send_json(TOPIC_NOT_FOUND)
                    continue
                sock.topic, sock.params = env.topic, params
                env.topic_params.update(params)
                if env.event == "join":
                    await ch.on_join_callback(env.topic_params or {}, sock)
                    joined.add(ch)
                    continue
                if env.event == "leave":
                    await ch.on_exit_callback(sock)
                    joined.discard(ch)
                    continue
                if ch not in joined:
                    await sock.send_json(TOPIC_NOT_FOUND)
                    continue
                await ch.dispatch(env, sock)
        except WebSocketDisconnect:
            pass
        finally:
            for ch in joined:
                if ch.on_exit_callback:
                    await ch.on_exit_callback(sock)
            if self._on_disconnect:
                await self._on_disconnect(sock)

    def _match_channel(self, topic: str) -> tuple[Channel | None, dict[str, str] | None]:
        for ch in self._channels:
            if params := ch.match(topic):
                return ch, params
        return None, None
```

## PubSub / Message Bus (planned)
- Goal: decouple channel fanout from the old HTTP `BusPlugin`; provide a websocket-focused bus with a minimal API and in-memory backend, pluggable for Redis/PG later.
- Message shape stays the same envelope used by managed sockets: `{topic, event, payload}`.
- Lifecycle: joining a channel subscribes the socket to the topic; leaving/disconnect unsubscribes; `sock.publish(...)` broadcasts to all current subscribers of the topic (including caller by default).

### Bus API sketch
```python
class PubSubMessage(Protocol):
    topic: str
    event: str
    payload: Any


class SocketBus(Protocol):
    """
    Bus works with generic callbacks, not sockets. A callback just needs to accept a message and return awaitable.
    """
    async def subscribe(self, topic: str, callback: Callable[[PubSubMessage], Awaitable[None]]) -> None: ...
    async def unsubscribe(self, topic: str, callback: Callable[[PubSubMessage], Awaitable[None]]) -> None: ...
    async def publish(self, topic: str, event: str, payload: Any) -> None: ...


class InMemorySocketBus(SocketBus):
    """
    - topic -> set[weakref[callback]]
    - best-effort fanout; drop dead refs
    - sequential send (simple, predictable); can add limited parallelism later
    """
```

### Hub wiring
- `SocketHub` holds a `bus: SocketBus`; default to `InMemorySocketBus()`, allow override via ctor for custom backends.
- During `join`, after `on_join` succeeds, create a per-socket callback (e.g., `cb = partial(sock.send_json, {"topic": topic, "event": ..., "payload": ...})` or a thin wrapper) and call `bus.subscribe(env.topic, cb)`. Also set `sock._publish` so `sock.publish` delegates to the bus using the resolved topic.
- During `leave` or disconnect cleanup, call `bus.unsubscribe(env.topic, cb)` (ignore errors if already gone).
- `sock.publish(payload, event="broadcast")` simply calls `bus.publish(sock.topic, event, payload)`; `sock.emit/reply` remain direct-to-sender helpers.

### Fanout semantics
- Send envelope `{topic, event, payload}` to each subscriber via `sock.send_json`; drop subscribers that raise during send.
- No ordering guarantees across topics; within a topic, in-memory backend preserves send order of the publish call.
- Allow self-delivery by default; optional `exclude` param can be added later if needed.

### Error handling and backpressure
- If publish to a topic with no subscribers, it's a no-op.
- Exceptions during fanout do not crash the hub loop; failed sockets are removed and processing continues.
- Backpressure: keep simple (await each send). If needed later, add bounded task group with max concurrency.

### Extensibility (future)
- Redis/PG backends can implement the same `SocketBus` protocol; hub only depends on the interface.
- Support pattern subscriptions (e.g., prefix/wildcard) later; initial version uses exact topic string after pattern resolution.
- Metrics/hooks: expose optional callbacks for subscribe/unsubscribe/publish events to aid instrumentation.
