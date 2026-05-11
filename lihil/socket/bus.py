import asyncio
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

from .protocol import MessageEnvelope


class SocketBus(ABC):  # TODO: rename, this is a general message bus
    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        callback: Callable[[MessageEnvelope], Awaitable[None]],
    ) -> None: ...

    @abstractmethod
    async def unsubscribe(
        self,
        topic: str,
        callback: Callable[[MessageEnvelope], Awaitable[None]],
    ) -> None: ...

    @abstractmethod
    async def publish(self, topic: str, event: str, payload: Any) -> None:
        """
        Blocking fanout: await delivery to subscribers.
        """

    @abstractmethod
    async def emit(self, topic: str, event: str, payload: Any) -> None:
        """
        Fire-and-forget fanout.
        """


class InMemorySocketBus(SocketBus):
    """
    Simple in-memory bus for topic fanout.
    """

    def __init__(self) -> None:
        self._subs: dict[str, set[Callable[[MessageEnvelope], Awaitable[None]]]] = {}

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[MessageEnvelope], Awaitable[None]],
    ) -> None:
        self._subs.setdefault(topic, set()).add(callback)

    async def unsubscribe(
        self,
        topic: str,
        callback: Callable[[MessageEnvelope], Awaitable[None]],
    ) -> None:
        callbacks = self._subs.get(topic)
        if not callbacks:
            return
        callbacks.discard(callback)
        if not callbacks:
            self._subs.pop(topic, None)

    async def publish(self, topic: str, event: str, payload: Any) -> None:
        envelope = MessageEnvelope(topic=topic, event=event, payload=payload)
        callbacks = list(self._subs.get(topic, set()))
        dead: list[Callable[[MessageEnvelope], Awaitable[None]]] = []
        for cb in callbacks:
            try:
                await cb(envelope)
            except Exception:
                dead.append(cb)
        if dead:
            callbacks_set = self._subs.get(topic)
            if callbacks_set:
                for cb in dead:
                    callbacks_set.discard(cb)
                if not callbacks_set:
                    self._subs.pop(topic, None)

    async def emit(self, topic: str, event: str, payload: Any) -> None:
        asyncio.create_task(self.publish(topic, event, payload))
