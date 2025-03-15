from inspect import Parameter
from types import UnionType
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Callable,
    Generator,
    Literal,
    TypeAliasType,
    get_args,
    get_origin,
)

from lihil.constant.status import code as get_status_code
from lihil.errors import StatusConflictError
from lihil.interface import MISSING, Base, IEncoder, Maybe, is_provided
from lihil.interface.marks import HTML, Json, Resp, Stream, Text, is_resp_mark
from lihil.utils.phasing import encode_json, encode_text
from lihil.utils.typing import flatten_annotated


def parse_status(status: Any) -> int:
    status_type: type = type(status)
    if status_type is int:
        return status
    elif status_type is str:
        return int(status)
    elif isinstance(status, TypeAliasType):
        try:
            return get_status_code(status)
        except KeyError:
            raise ValueError("Invalid status code")
    else:
        raise ValueError("Invalid status code")


def get_media(origin: Any):
    content_type = get_args(origin.__value__)[-1]
    return content_type


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


class ReturnParam[T](Base):
    # TODO: generate response from this
    encoder: IEncoder[T]
    status: int
    type_: Maybe[type[T]] | UnionType | None = MISSING
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
        cls, annt: TypeAliasType, origin: Any, status: int
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
        cls, annt: Annotated[Any, "Annotated"], origin: Any, status: int
    ) -> "ReturnParam[Any]":
        metas = flatten_annotated(annt)
        encoder = encode_json
        if len(metas) > 1:
            ret_type, *rest = metas
            for m in rest:
                if isinstance(m, CustomEncoder):
                    encoder = m.encode
                    break
        else:
            ret_type = annt

        if is_resp_mark(ret_type):
            # e.g.: Annotated[Resp[MyType, status.OK], CustomEncoder(encode_mytype)]
            rp = ReturnParam.from_mark(ret_type, origin, status)
            rp.replace(encoder=encoder)
            return rp
        else:
            ret = ReturnParam(
                type_=ret_type, encoder=encoder, annotation=annt, status=status
            )
            return ret

    @classmethod
    def from_generic(cls, annt: Any, origin: Any, status: int) -> "ReturnParam[Any]":
        if is_resp_mark(annt):
            return ReturnParam.from_mark(annt, origin, status)
        elif origin is Annotated:
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
    annt: Maybe[type[R] | UnionType | TypeAliasType], status: int = 200
) -> ReturnParam[R]:
    if annt is Parameter.empty:
        return ReturnParam(encoder=encode_json, status=200)

    status = parse_status(status)
    if isinstance(annt, UnionType):
        """
        TODO:
        we need to handle case of multiple return e.g
        async def userfunc() -> Resp[User, 200] | Resp[Order, 201]
        """
        annt_args = get_args(annt)
        if not any(is_resp_mark(arg) for arg in annt_args):
            ret = ReturnParam(
                type_=annt, annotation=annt, encoder=encode_json, status=status
            )
        else:
            raise NotImplementedError(f"Unexpected case {annt=} received")
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
