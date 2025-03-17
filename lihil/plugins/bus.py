import inspect
from abc import ABC
from asyncio import Task, TaskGroup, create_task, to_thread
from collections import defaultdict
from dataclasses import dataclass
from functools import partial
from types import MappingProxyType, MethodType, UnionType
from typing import Annotated, Any, Union, cast, get_args, get_origin
from weakref import ref

from ididi import Graph, Resolver
from ididi.interfaces import GraphIgnore

from lihil.ds import Event
from lihil.interface import MISSING, Protocol
from lihil.utils.visitor import all_subclasses

UNION_META = (UnionType, Union)
CTX_MARKER = "__anywise_context__"

BusMaker = Any
Context = Any
FrozenContext = Any
IGNORE_TYPES = (Context, FrozenContext)


class IGuard(Protocol):

    @property
    def next_guard(self) -> Any: ...

    def chain_next(self, next_guard: Any, /) -> None:
        """
        self._next_guard = next_guard
        """

    async def __call__(self, command: Any, context: Any) -> Any: ...


class IEventSink(Protocol):

    async def sink(self, event: Any):
        """
        sink an event or a sequence of events to corresponding event sink
        """


class BaseGuard(ABC):
    _next_guard: Any

    def __init__(self, next_guard: Any = None):
        self._next_guard = next_guard

    @property
    def next_guard(self) -> Any:
        return self._next_guard

    def __repr__(self):
        base = f"{self.__class__.__name__}("
        if self._next_guard:
            base += f"next_guard={self._next_guard}"
        base += ")"
        return base

    def chain_next(self, next_guard: Any, /) -> None:
        self._next_guard = next_guard

    async def __call__(self, command: Any, context: Any) -> Any:
        if not self._next_guard:
            raise DunglingGuardError(self)
        return await self._next_guard(command, context)


class Guard(BaseGuard):
    def __init__(
        self,
        next_guard: Any = None,
        /,
        *,
        pre_handle: Any = None,
        post_handle: Any = None,
    ):
        super().__init__(next_guard)
        self.pre_handle = pre_handle
        self.post_handle = post_handle

    async def __call__(self, command: Any, context: Any) -> Any:
        if self.pre_handle:
            await self.pre_handle(command, context)

        if not self._next_guard:
            raise DunglingGuardError(self)

        response = await self._next_guard(command, context)
        if self.post_handle:
            return await self.post_handle(command, context, response)
        return response


class AnyWiseError(Exception): ...


class NotSupportedHandlerTypeError(AnyWiseError):
    def __init__(self, handler: Any):
        super().__init__(f"{handler} of type {type(handler)} is not supported")


class HandlerRegisterFailError(AnyWiseError): ...


class InvalidMessageTypeError(HandlerRegisterFailError):
    def __init__(self, msg_type: Any):
        super().__init__(f"{msg_type} is not a valid message type")


class MessageHandlerNotFoundError(HandlerRegisterFailError):
    def __init__(self, base_type: Any, handler: Any):
        super().__init__(f"can't find param of type `{base_type}` in {handler}")


class InvalidHandlerError(HandlerRegisterFailError):
    def __init__(self, basetype: Any, msg_type: Any, handler: Any):
        msg = f"{handler} is receiving {msg_type}, which is not a valid subclass of {basetype}"
        super().__init__(msg)


class UnregisteredMessageError(AnyWiseError):
    def __init__(self, msg: Any):
        super().__init__(f"Handler for message {msg} is not found")


class DunglingGuardError(AnyWiseError):
    def __init__(self, guard: Any):
        super().__init__(f"Dangling guard {guard}, most likely a bug")


class SinkUnsetError(AnyWiseError):
    def __init__(self):
        super().__init__("Sink is not set")


Result = Any
HandlerMapping = Any
ListenerMapping = Any


def gather_types(annotation: Any) -> set[Any]:
    """
    Recursively gather all types from a type annotation, handling:
    - Union types (|)
    - Annotated types
    - Direct types
    """
    types: set[Any] = set()

    # Handle None case
    if annotation is inspect.Signature.empty:
        # raise Exception?
        return types

    origin = get_origin(annotation)
    if not origin:
        types.add(annotation)
        types |= all_subclasses(annotation)
    else:
        # Union types (including X | Y syntax)
        if origin is Annotated:
            # For Annotated[Type, ...], we only care about the first argument
            param_type = get_args(annotation)[0]
            types.update(gather_types(param_type))
        elif origin in UNION_META:  # Union[X, Y] and X | Y
            for arg in get_args(annotation):
                types.update(gather_types(arg))
        else:
            # Generic type, e.g. List, Dict, etc.
            raise InvalidMessageTypeError(origin)
    return types


async def default_send(message: Any, context: Any, handler: Any) -> Any:
    if context is None:
        context = dict()
    return await handler(message, context)


async def default_publish(message: Any, context: Any, listeners: Any) -> None:
    if context is None:
        context = MappingProxyType({})

    for listener in listeners:
        await listener(message, context)


async def concurrent_publish(msg: Any, context: Any, subscribers: Any) -> None:
    if not context:
        context = {}
    async with TaskGroup() as tg:
        for sub in subscribers:
            tg.create_task(sub(msg, context))


@dataclass(frozen=True, slots=True, kw_only=True)
class FuncMeta:
    """
    is_async: bool
    is_contexted:
    whether the handler receives a context param
    """

    message_type: Any
    handler: Any
    is_async: bool
    is_contexted: bool
    ignore: GraphIgnore


@dataclass(frozen=True, slots=True, kw_only=True)
class MethodMeta(FuncMeta):
    owner_type: Any


@dataclass(frozen=True, slots=True, kw_only=True)
class GuardMeta:
    guard_target: Any
    guard: Any


def context_wrapper(origin: Any):
    async def inner(message: Any, _: Any):
        return await origin(message)

    return inner


class ManagerBase:
    def __init__(self, dg: Graph):
        self._dg = dg

    async def _resolve_meta(self, meta: Any, *, resolver: Resolver):
        handler = meta.handler

        if not meta.is_async:
            # TODO: manage ThreadExecutor ourselves to allow config max worker
            # by default is min(32, cpu_cores + 4)
            handler = partial(to_thread, handler)

        if isinstance(meta, MethodMeta):
            instance = await resolver.resolve(meta.owner_type)
            handler = MethodType(handler, instance)
        else:
            # TODO: EntryFunc
            handler = self._dg.entry(ignore=meta.ignore)(handler)

        if not meta.is_contexted:
            handler = context_wrapper(handler)
        return handler


class HandlerManager(ManagerBase):
    def __init__(self, dg: Graph):
        super().__init__(dg)
        self._handler_metas: dict[Any, Any] = {}
        self._guard_mapping: Any = defaultdict(list)
        self._global_guards: list[Any] = []

    @property
    def global_guards(self):
        return self._global_guards[:]

    def include_handlers(self, command_mapping: Any):
        handler_mapping = {msg_type: meta for msg_type, meta in command_mapping.items()}
        self._handler_metas.update(handler_mapping)

    def include_guards(self, guard_mapping: Any):
        for origin_target, guard_meta in guard_mapping.items():
            if origin_target is Any or origin_target is object:
                self._global_guards.extend(guard_meta)
            else:
                self._guard_mapping[origin_target].extend(guard_meta)

    async def _chain_guards(
        self, msg_type: Any, handler: Any, *, resolver: Resolver
    ) -> Any:
        command_guards = self._global_guards + self._guard_mapping[msg_type]
        if not command_guards:
            return handler

        guards: list[Any] = [
            (
                await resolver.aresolve(meta.guard)
                if isinstance(meta.guard, type)
                else meta.guard
            )
            for meta in command_guards
        ]

        head, *rest = guards
        ptr = head

        for nxt in rest:
            ptr.chain_next(nxt)
            ptr = nxt

        ptr.chain_next(handler)
        return head

    def get_handler(self, msg_type: Any) -> Any:
        try:
            meta = self._handler_metas[msg_type]
        except KeyError:
            return None
        else:
            return meta.handler

    def get_guards(self, msg_type: Any) -> list[Any]:
        return [meta.guard for meta in self._guard_mapping[msg_type]]

    async def resolve_handler(self, msg_type: Any, resovler: Resolver):
        try:
            meta = self._handler_metas[msg_type]
        except KeyError:
            raise UnregisteredMessageError(msg_type)

        resolved_handler = await self._resolve_meta(meta, resolver=resovler)
        guarded_handler = await self._chain_guards(
            msg_type, resolved_handler, resolver=resovler
        )
        return guarded_handler


class ListenerManager(ManagerBase):
    def __init__(self, dg: Graph):
        super().__init__(dg)
        self._listener_metas: dict[Any, list[Any]] = dict()

    def include_listeners(self, event_mapping: Any):
        listener_mapping = {
            msg_type: [meta for meta in metas]
            for msg_type, metas in event_mapping.items()
        }

        for msg_type, metas in listener_mapping.items():
            if msg_type not in self._listener_metas:
                self._listener_metas[msg_type] = metas
            else:
                self._listener_metas[msg_type].extend(metas)

    def get_listeners(self, msg_type: Any) -> Any:
        try:
            listener_metas = self._listener_metas[msg_type]
        except KeyError:
            return []
        else:
            return [meta.handler for meta in listener_metas]

    # def replace_listener(self, msg_type: type, old, new):
    #    idx = self._listener_metas[msg_type].index(old)
    #    self._listener_metas[msg_type][idx] = FuncMeta.from_handler(msg_type, new)

    async def resolve_listeners(self, msg_type: Any, *, resolver: Resolver) -> Any:
        try:
            listener_metas = self._listener_metas[msg_type]
        except KeyError:
            raise UnregisteredMessageError(msg_type)
        else:
            resolved_listeners = [
                await self._resolve_meta(meta, resolver=resolver)
                for meta in listener_metas
            ]
            return resolved_listeners


class Inspect:
    """
    a util class for inspecting anywise
    """

    def __init__(
        self, handler_manager: HandlerManager, listener_manager: ListenerManager
    ):
        self._hm = ref(handler_manager)
        self._lm = ref(listener_manager)

    def listeners(self, key: Any) -> Any:
        if (lm := self._lm()) and (listeners := lm.get_listeners(key)):
            return listeners

    def handler(self, key: Any) -> Any:
        if (hm := self._hm()) and (handler := hm.get_handler(key)):
            return handler

    def guards(self, key: Any) -> Any:
        hm = self._hm()

        if hm is None:
            return []

        global_guards = [meta.guard for meta in hm.global_guards]
        command_guards = hm.get_guards(msg_type=key)
        return global_guards + command_guards


def is_contextparam(param: list[inspect.Parameter]) -> bool:
    if not param:
        return False

    param_type = param[0].annotation

    v = getattr(param_type, "__value__", None)
    if not v:
        return False

    metas = getattr(v, "__metadata__", [])
    return CTX_MARKER in metas


def get_funcmetas(msg_base: Any, func: Any) -> list[Any]:
    params = inspect.Signature.from_callable(func).parameters.values()
    if not params:
        raise MessageHandlerNotFoundError(msg_base, func)

    msg, *rest = params
    is_async: bool = inspect.iscoroutinefunction(func)
    is_contexted: bool = is_contextparam(rest)
    derived_msgtypes = gather_types(msg.annotation)

    if not derived_msgtypes:
        raise MessageHandlerNotFoundError(msg_base, func)

    for msg_type in derived_msgtypes:
        if not issubclass(msg_type, msg_base):
            raise InvalidHandlerError(msg_base, msg_type, func)

    ignore = tuple(derived_msgtypes) + IGNORE_TYPES

    metas = [
        FuncMeta(
            message_type=t,
            handler=func,
            is_async=is_async,
            is_contexted=is_contexted,
            ignore=ignore,
        )
        for t in derived_msgtypes
    ]
    return metas


def get_methodmetas(msg_base: type, cls: type) -> list[MethodMeta]:
    cls_members = inspect.getmembers(cls, predicate=inspect.isfunction)
    method_metas: list[MethodMeta] = []
    for name, func in cls_members:
        if name.startswith("_"):
            continue
        params = inspect.Signature.from_callable(func).parameters.values()
        if len(params) == 1:
            continue

        _, msg, *rest = params  # ignore `self`
        is_async: bool = inspect.iscoroutinefunction(func)
        is_contexted: bool = is_contextparam(rest)
        derived_msgtypes = gather_types(msg.annotation)

        if not all(issubclass(msg_type, msg_base) for msg_type in derived_msgtypes):
            continue

        ignore = tuple(derived_msgtypes) + IGNORE_TYPES

        metas = [
            MethodMeta(
                message_type=t,
                handler=func,
                is_async=is_async,
                is_contexted=is_contexted,
                ignore=ignore,  # type: ignore
                owner_type=cls,
            )
            for t in derived_msgtypes
        ]
        method_metas.extend(metas)

    if not method_metas:
        raise MessageHandlerNotFoundError(msg_base, cls)

    return method_metas


# TODO: separate EventRegistry and CommandRegistry
class MessageRegistry:
    def __init__(
        self,
        *,
        command_base: Any = MISSING,
        event_base: Any = MISSING,
        graph: Any = MISSING,
    ):
        self._command_base = command_base
        self._event_base = event_base
        self._graph = graph or Graph()

        self.command_mapping: Any = {}
        self.event_mapping: Any = {}
        self.guard_mapping: Any = defaultdict(list)

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def command_base(self) -> Any:
        return self._command_base

    @property
    def event_base(self) -> Any:
        return self._event_base

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(command_base={self._command_base}, event_base={self._event_base})"

    def __call__(self, handler: Any) -> Any:
        return self._register(handler)

    def factory(self, factory: Any = None, **config: Any) -> Any:
        if factory is None:
            return cast(Any, partial(self.factory, **config))

        self._graph.node(**config)(factory)
        return factory

    def _register_commandhanlders(self, handler: Any) -> None:
        if not self._command_base:
            return

        if inspect.isfunction(handler):
            metas = get_funcmetas(self._command_base, handler)
        elif inspect.isclass(handler):
            metas = get_methodmetas(self._command_base, handler)
        else:
            raise NotSupportedHandlerTypeError(handler)

        mapping = {meta.message_type: meta for meta in metas}
        self.command_mapping.update(mapping)

    def _register_eventlisteners(self, listener: Any) -> None:
        if not self._event_base:
            return

        if inspect.isfunction(listener):
            metas = get_funcmetas(self._event_base, listener)
        elif inspect.isclass(listener):
            metas = get_methodmetas(self._event_base, listener)
        else:
            raise NotSupportedHandlerTypeError(listener)

        for meta in metas:
            msg_type = meta.message_type
            if msg_type not in self.event_mapping:
                self.event_mapping[msg_type] = [meta]
            else:
                self.event_mapping[msg_type].append(meta)

    def _register(self, handler: Any):
        if self.command_base:
            try:
                self._register_commandhanlders(handler)
            except HandlerRegisterFailError:
                if not self.event_base:
                    raise
                self._register_eventlisteners(handler)
            return handler
        elif self.event_base:
            self._register_eventlisteners(handler)
            return handler
        else:
            raise HandlerRegisterFailError

    def register(
        self,
        *handlers: Any,
        pre_hanldes: Any = None,
        post_handles: Any = None,
    ) -> None:

        for handler in handlers:
            if inspect.isclass(handler):
                if issubclass(handler, BaseGuard):
                    self.add_guards(handler)
                    continue
            self._register(handler)

        if pre_hanldes:
            for pre_handle in pre_hanldes:
                self.pre_handle(pre_handle)

        if post_handles:
            for post_handle in post_handles:
                self.post_handle(post_handle)

    def get_guardtarget(self, func: Any) -> set[Any]:

        if inspect.isclass(func):
            func_params = list(inspect.signature(func.__call__).parameters.values())[1:]
        elif inspect.isfunction(func):
            func_params = list(inspect.signature(func).parameters.values())
        else:
            raise MessageHandlerNotFoundError(self._command_base, func)

        if not func_params:
            raise MessageHandlerNotFoundError(self._command_base, func)

        cmd_type = func_params[0].annotation

        return gather_types(cmd_type)

    def pre_handle(self, func: Any) -> Any:
        targets = self.get_guardtarget(func)
        for target in targets:
            meta = GuardMeta(guard_target=target, guard=Guard(pre_handle=func))
            self.guard_mapping[target].append(meta)
        return func

    def post_handle(self, func: Any) -> Any:
        targets = self.get_guardtarget(func)
        for target in targets:
            meta = GuardMeta(guard_target=target, guard=Guard(post_handle=func))
            self.guard_mapping[target].append(meta)
        return func

    def add_guards(self, *guards: Any) -> None:
        for guard in guards:
            targets = self.get_guardtarget(guard)
            for target in targets:
                meta = GuardMeta(guard_target=target, guard=guard)
                self.guard_mapping[target].append(meta)


class EventBus:
    def __init__(
        self,
        listener: ListenerManager,
        strategy: Any,
        resolver: Resolver,
        tasks: set[Task[Any]],
    ):
        self.listeners = listener
        self.strategy = strategy
        self.resolver = resolver
        self.tasks = tasks

    async def publish(
        self,
        event: Event,
        *,
        context: Any = None,
    ) -> None:
        # share same scope as request
        resolved_listeners = await self.listeners.resolve_listeners(
            type(event), resolver=self.resolver
        )
        return await self.strategy(event, context, resolved_listeners)

    def emit(
        self,
        event: Event,
        context: Any = None,
        callback: Any = None,
    ) -> None:
        async def event_task(event: Event, context: Any):
            async with self.resolver.ascope() as asc:
                listener = await self.listeners.resolve_listeners(
                    type(event), resolver=asc
                )
                await self.strategy(event, context, listener)

        def callback_wrapper(task: Task[Any]):
            self.tasks.discard(task)
            if callback:
                callback(task)

        task = create_task(event_task(event, context or {}))
        task.add_done_callback(callback_wrapper)
        self.tasks.add(task)
        # perserve a strong ref to prevent task from being gc


class Collector:
    def __init__(
        self,
        *registries: Any,
        graph: Any = None,
        sink: Any = None,
        sender: Any = default_send,
        publisher: Any = default_publish,
    ):
        self._dg = graph or Graph()
        self._handler_manager = HandlerManager(self._dg)
        self._listener_manager = ListenerManager(self._dg)

        self._sender = sender
        self._publisher = publisher
        self._sink = sink

        self._tasks: set[Task[Any]] = set()

        self.include(*registries)

    def create_event_bus(self, resolver: Resolver):
        return EventBus(self._listener_manager, self._publisher, resolver, self._tasks)

    @property
    def sender(self) -> Any:
        return self._sender

    @property
    def publisher(self) -> Any:
        return self._publisher

    @property
    def graph(self) -> Graph:
        return self._dg

    def reset_graph(self) -> None:
        self._dg.reset(clear_nodes=True)

    @property
    def inspect(self) -> Inspect:
        return Inspect(
            handler_manager=self._handler_manager,
            listener_manager=self._listener_manager,
        )

    def include(self, *registries: Any) -> None:
        for msg_registry in registries:
            self._dg.merge(msg_registry.graph)
            self._handler_manager.include_handlers(msg_registry.command_mapping)
            self._handler_manager.include_guards(msg_registry.guard_mapping)
            self._listener_manager.include_listeners(msg_registry.event_mapping)
        self._dg.analyze_nodes()

    def scope(self, name: Any = None):
        return self._dg.scope(name)

    async def send(
        self,
        msg: object,
        *,
        resolver: Resolver,
        context: Any = None,
    ) -> Any:

        handler = await self._handler_manager.resolve_handler(type(msg), resolver)
        return await self._sender(msg, context, handler)

    async def sink(self, event: Any):
        try:
            await self._sink.sink(event)
        except AttributeError:
            raise SinkUnsetError()
