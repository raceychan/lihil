import inspect
from re import Pattern
from typing import Any, Awaitable, Callable

from msgspec import ValidationError, convert

from .channel import ChannelBase
from .protocol import EVENT_NOT_FOUND, MessageEnvelope


class ChannelDispatcher:
    def validate(self, channel_type: type[ChannelBase]) -> None:
        self.validate_join_handler(channel_type, channel_type.topic)
        for name, handler in inspect.getmembers(channel_type, inspect.iscoroutinefunction):
            if not name.startswith("on_") or name in {"on_join", "on_exit", "on_update"}:
                continue
            self._validate_handler_signature(channel_type, name, handler)

    def join_kwargs(
        self, channel: ChannelBase, params: dict[str, str]
    ) -> dict[str, str]:
        accepted = self._handler_params(channel.on_join)
        if accepted is None:
            return params
        return {name: params[name] for name in accepted if name in params}

    def validate_join_handler(
        self, channel_type: type[ChannelBase], topic: Pattern[str]
    ) -> None:
        accepted = self._handler_params(channel_type.on_join)
        if accepted is None:
            return

        topic_params = set(topic.groupindex)
        unknown = accepted - topic_params
        if unknown:
            params = ", ".join(sorted(unknown))
            available = ", ".join(sorted(topic_params)) or "none"
            raise TypeError(
                f"{channel_type.__name__}.on_join declares unknown topic "
                f"parameter(s): {params}. Available topic parameters: {available}"
            )

    async def dispatch(self, channel: ChannelBase, msg: MessageEnvelope) -> Any:
        handler = getattr(channel, f"on_{msg.event}", None)
        if handler is not None:
            return await self._call_event_handler(handler, msg)

        if type(channel).on_message is ChannelBase.on_message:
            return EVENT_NOT_FOUND
        return await channel.on_message(msg)

    async def _call_event_handler(
        self, handler: Callable[..., Awaitable[Any]], msg: MessageEnvelope
    ) -> Any:
        params = inspect.signature(handler).parameters
        if not params:
            return await handler()
        ordered = list(params.values())
        if len(ordered) == 1:
            return await handler(self._bind_param(ordered[0], msg))
        return await handler(self._bind_param(ordered[0], msg), msg)

    def _bind_param(self, param: inspect.Parameter, msg: MessageEnvelope) -> Any:
        annotation = param.annotation
        if param.name == "env" or annotation is MessageEnvelope:
            return msg
        if annotation is inspect.Signature.empty or annotation is Any:
            return msg.payload
        try:
            return convert(msg.payload, annotation)
        except ValidationError:
            raise

    def _handler_params(
        self, handler: Callable[..., Awaitable[Any]]
    ) -> set[str] | None:
        params = list(inspect.signature(handler).parameters.values())
        if params and params[0].name == "self":
            params = params[1:]

        names: set[str] = set()
        for param in params:
            if param.kind is inspect.Parameter.VAR_KEYWORD:
                return None
            if param.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                raise TypeError(
                    f"{handler.__qualname__} does not support {param.kind.description} "
                    "parameters"
                )
            names.add(param.name)
        return names

    def _validate_handler_signature(
        self,
        channel_type: type[ChannelBase],
        name: str,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        params = list(inspect.signature(handler).parameters.values())
        if params and params[0].name == "self":
            params = params[1:]

        if len(params) > 2:
            raise TypeError(
                f"{channel_type.__name__}.{name} accepts at most payload and env"
            )

        for param in params:
            if param.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                raise TypeError(
                    f"{channel_type.__name__}.{name} only supports positional "
                    "payload/env parameters"
                )

        if len(params) == 2:
            env_param = params[1]
            if env_param.name != "env" and env_param.annotation is not MessageEnvelope:
                raise TypeError(
                    f"{channel_type.__name__}.{name}'s second parameter must be env"
                )
