from collections.abc import AsyncGenerator as ABCAsyncGen
from collections.abc import Generator as ABCGen
from inspect import Parameter
from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Callable,
    Generator,
    Literal,
    TypeAliasType,
    Union,
    get_args,
    get_origin,
)

from lihil.constant.status import code as get_status_code
from lihil.errors import InvalidStatusError, StatusConflictError
from lihil.interface import MISSING, IEncoder, Maybe, Record, is_provided
from lihil.interface.marks import HTML, Json, Resp, Stream, Text, is_resp_mark
from lihil.utils.phasing import encode_json, encode_text
from lihil.utils.typing import flatten_annotated


def parse_status(status: Any) -> int:
    status_type: type = type(status)

    try:
        if status_type is int:
            return status
        elif status_type is str:
            return int(status)
        else:
            return get_status_code(status)
    except Exception:
        raise InvalidStatusError(status)


def get_media(origin: Any):
    content_type = get_args(origin.__value__)[-1]
    return content_type


def get_encoder_from_metas(metas: list[Any]) -> IEncoder[Any] | None:
    for meta in metas:
        if isinstance(meta, CustomEncoder):
            return meta.encode


class CustomEncoder:
    encode: Callable[[Any], bytes]


async def agen_encode_wrapper[T](
    async_gen: AsyncGenerator[T, None], encoder: IEncoder[T]
) -> AsyncGenerator[bytes, None]:
    async for res in async_gen:
        yield encoder(res)


def syncgen_encode_wrapper[T](
    sync_gen: Generator[T, None, None], encoder: IEncoder[T]
) -> Generator[bytes, None, None]:
    for res in sync_gen:
        yield encoder(res)


class ReturnParam[T](Record):
    # TODO: generate response from this
    encoder: IEncoder[T]
    status: int
    type_: Maybe[type[T]] | UnionType | GenericAlias | TypeAliasType | None = MISSING
    content_type: str = "application/json"
    annotation: Any = MISSING

    def __post_init__(self):
        if self.status < 200 or self.status in (204, 205, 304):
            if is_provided(self.type_) and self.type_ is not None:
                raise StatusConflictError(self.status, self.type_)

    def __repr__(self) -> str:
        return f"Return({self.annotation}, {self.status})"

    @classmethod
    def from_mark(
        cls, annt: TypeAliasType | GenericAlias | UnionType, origin: Any, status: int
    ) -> "ReturnParam[Any]":
        origin = get_origin(annt) or annt
        if origin is Text:
            content_type = get_media(origin)
            rtp = ReturnParam(
                type_=bytes,
                encoder=encode_text,
                status=status,
                annotation=annt,
                content_type=content_type,
            )
            return rtp
        elif origin is HTML:
            content_type = get_media(origin)
            return ReturnParam(
                type_=str,
                encoder=encode_text,
                status=status,
                annotation=annt,
                content_type=content_type,
            )
        elif origin is Stream:
            content_type = get_media(origin)
            return ReturnParam(
                type_=bytes,
                encoder=encode_text,
                status=status,
                annotation=annt,
                content_type=content_type,
            )
        elif origin is Json:
            type_args = get_args(annt)
            retype, *_ = type_args
            content_type = get_media(origin)
            return ReturnParam(
                type_=retype,
                encoder=encode_json,
                status=status,
                annotation=annt,
                content_type=content_type,
            )
        elif origin is Resp:
            resp = get_args(annt)
            if len(resp) > 1:
                retype, status = resp  # type: ignore
            else:
                retype = resp[0]  # type: ignore
            return analyze_return(retype, status)
        elif origin is Annotated:
            return ReturnParam.from_annotated(annt, origin, status)
        else:
            raise NotImplementedError(f"Unexpected case {annt=}, {origin=} received")

    @classmethod
    def from_annotated(
        cls,
        annt: Annotated[Any, "Annotated"],
        origin: Maybe[Any] = MISSING,
        status: int = 200,
    ) -> "ReturnParam[Any]":
        if not is_provided(origin):
            origin = get_origin(annt)

        # encoder = encode_json
        custom_encoder = None
        ret_type, metas = flatten_annotated(annt)

        custom_encoder = get_encoder_from_metas(metas) if metas else None

        if is_resp_mark(ret_type):
            rp = ReturnParam.from_mark(ret_type, origin, status)
            if custom_encoder:
                return rp.replace(encoder=custom_encoder)
            return rp
        else:
            ret = ReturnParam(
                type_=ret_type,
                encoder=custom_encoder or encode_json,
                annotation=annt,
                status=status,
            )
            return ret

    @classmethod
    def from_generic(cls, annt: Any, origin: Any, status: int) -> "ReturnParam[Any]":
        # TODO: from generator
        if is_resp_mark(annt):
            return ReturnParam.from_mark(annt, origin, status)
        elif origin is Annotated or origin in (
            Generator,
            ABCGen,
            AsyncGenerator,
            ABCAsyncGen,
        ):
            return ReturnParam.from_annotated(annt, origin, status)
        else:  # vanilla case, dict[str, str], list[str], etc.
            assert isinstance(origin, type)
            ret = ReturnParam[Any](
                type_=origin, encoder=encode_json, annotation=annt, status=status
            )
            return ret


def is_py_singleton(t: Any) -> Literal[None, True, False]:
    return t in {True, False, None, ...}


def analyze_return[R](
    annt: Maybe[type[R] | UnionType | TypeAliasType | GenericAlias], status: int = 200
) -> ReturnParam[R]:
    if annt is Parameter.empty or not is_provided(annt):
        return ReturnParam(encoder=encode_json, status=200)
    status = parse_status(status)

    if isinstance(annt, UnionType) or get_origin(annt) is Union:
        """
        TODO:
        we need to handle case of multiple return e.g
        async def userfunc() -> Resp[User, 200] | Resp[Order, 201]
        """
        # TODO: analyze all if more than one raise excepiton
        annt_args = get_args(annt)
        rets: list[ReturnParam[Any]] = []

        for arg in annt_args:
            if not is_resp_mark(arg):
                continue
            rets.append(analyze_return(arg))

        if len(annt_args) > 1 and rets:
            raise NotImplementedError(f"Unexpected case {annt=} received")

        ret = ReturnParam(
            type_=annt, annotation=annt, encoder=encode_json, status=status
        )
    elif origin := get_origin(annt) or is_resp_mark(annt):
        # NOTE: we have to check both condition, since some resp marks are not generic
        ret = ReturnParam.from_generic(annt, origin, status)
    else:
        # default case, should be a single non-generic type,
        # e.g. User, str, bytes, etc.
        if not is_py_singleton(annt) and not isinstance(annt, type):
            raise NotImplementedError(f"Unexpected case {annt=}, {origin=} received")
        ret = ReturnParam(
            type_=annt,
            annotation=annt,
            encoder=encode_json,
            status=status,
        )
    return ret
