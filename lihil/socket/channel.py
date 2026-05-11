from __future__ import annotations

import asyncio
import inspect
import logging
import re
from typing import TYPE_CHECKING, Any, Awaitable, Literal

from ididi import Resolver

from .protocol import EVENT_NOT_FOUND, MessageEnvelope, error_payload

logger = logging.getLogger(__name__)
TaskExceptionPolicy = Literal["error", "close", "ignore"]

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from .bus import SocketBus
    from .hub import ISocket


class ChannelBase:
    """
    Class-based channel. Subclasses define `topic = Topic("...")` and override hooks.
    """

    topic: re.Pattern[str]
    task_exception_policy: TaskExceptionPolicy = "error"
    task_exception_close_code = 1011
    task_exception_close_reason = "Internal Server Error"

    def __init__(
        self,
        socket: ISocket,
        *,
        topic: str,
        bus: SocketBus,
        resolver: Resolver,
    ):
        self.socket = socket
        self.bus = bus
        self.resolver = resolver
        self._resolved_topic = topic
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._join_ref: str | None = None

    @property
    def resolved_topic(self) -> str:
        return self._resolved_topic

    @classmethod
    def match(cls, topic: str) -> dict[str, str] | None:
        if m := cls.topic.match(topic):
            return m.groupdict()
        return None

    async def publish(self, payload: Any, *, event: str = "broadcast") -> None:
        await self.bus.publish(self._resolved_topic, event=event, payload=payload)

    async def emit(self, payload: Any, *, event: str = "broadcast") -> None:
        await self.bus.emit(self._resolved_topic, event=event, payload=payload)

    async def on_update(self, env: MessageEnvelope) -> None:
        """
        Default bus subscriber callback: echoes envelope to the socket.
        """
        await self.socket.send_envelope(
            env.topic,
            env.event,
            env.payload,
            ref=env.ref,
            join_ref=env.join_ref or self._join_ref,
            event_id=env.event_id,
        )

    async def on_join(self, **params: str) -> None:
        await self.bus.subscribe(self.resolved_topic, self.on_update)

    async def on_message(self, env: MessageEnvelope) -> Any:
        return EVENT_NOT_FOUND

    async def on_exit(self) -> None:
        await self.bus.unsubscribe(self.resolved_topic, self.on_update)

    @property
    def join_ref(self) -> str | None:
        return self._join_ref

    def set_join_ref(self, join_ref: str | None) -> None:
        self._join_ref = join_ref

    async def replay_after(self, event_id: str | None) -> list[MessageEnvelope]:
        return []

    def start_task(self, name: str, coro: Awaitable[Any]) -> asyncio.Task[Any]:
        if name in self._tasks:
            if inspect.iscoroutine(coro):
                coro.close()
            raise ValueError(f"channel task {name!r} already exists")

        task = asyncio.create_task(coro)
        self._tasks[name] = task
        task.add_done_callback(lambda done: self._finalize_task(name, done))
        return task

    async def cancel_task(self, name: str) -> None:
        task = self._tasks.pop(name, None)
        if task is None:
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def cancel_tasks(self) -> None:
        task_names = list(self._tasks)
        await asyncio.gather(
            *(self.cancel_task(name) for name in task_names),
            return_exceptions=True,
        )

    async def aclose(self) -> None:
        await self.cancel_tasks()
        await self.on_exit()

    def _finalize_task(self, name: str, task: asyncio.Task[Any]) -> None:
        self._tasks.pop(name, None)
        if task.cancelled():
            return

        exc = task.exception()
        if exc is None or not self.socket.dual_connected:
            return

        detail = {
            "task": name,
            "error": str(exc),
        }
        logger.error(
            "channel task %r failed on %s",
            name,
            self.resolved_topic,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

        match self.task_exception_policy:
            case "error":
                asyncio.create_task(
                    self.socket.send_envelope(
                        self.resolved_topic,
                        "error",
                        error_payload("internal_error", detail=detail),
                    )
                )
            case "close":
                asyncio.create_task(
                    self.socket.close(
                        code=self.task_exception_close_code,
                        reason=self.task_exception_close_reason,
                    )
                )
            case "ignore":
                return
