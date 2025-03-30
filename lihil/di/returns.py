from collections.abc import AsyncGenerator as ABCAsyncGen
from collections.abc import Generator as ABCGen
from inspect import Parameter
from types import GenericAlias, UnionType
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Generator,
    Literal,
    TypeAliasType,
    get_args,
    overload,
)

from lihil.constant.status import code as get_status_code
from lihil.errors import (
    InvalidParamTypeError,
    InvalidStatusError,
    NotSupportedError,
    StatusConflictError,
)
from lihil.interface import (
    MISSING,
    CustomEncoder,
    Empty,
    IEncoder,
    Maybe,
    Record,
    is_provided,
)
from lihil.interface.marks import (
    HTML,
    Json,
    Resp,
    Stream,
    Text,
    is_resp_mark,
    lhl_get_origin,
)
from lihil.utils.phasing import encode_json, encode_text
from lihil.utils.typing import (
    deannotate,
    get_origin_pro,
    is_py_singleton,
    is_union_type,
)


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


def is_empty_return(t: Any):
    if not is_provided(t):
        return False

    if t is None or t is Literal[None]:
        return True

    return False


class EndpointReturn[T](Record):
    # TODO: generate response from this
    encoder: IEncoder[T]
    status: int
    type_: Maybe[type[T]] | UnionType | GenericAlias | TypeAliasType | None = MISSING
    content_type: str = "application/json"
    annotation: Any = MISSING

    def __post_init__(self):
        if self.status < 200 or self.status in (204, 205, 304):
            if not is_empty_return(self.type_):
                raise StatusConflictError(self.status, self.type_)

    def __repr__(self) -> str:
        return f"Return({self.annotation}, {self.status})"


# ===


def _parse_marked(
    annt: TypeAliasType | GenericAlias | UnionType, origin: Any, status: int
) -> "EndpointReturn[Any]":
    origin = lhl_get_origin(annt) or annt
    if origin is Text:
        content_type = get_media(origin)
        rtp = EndpointReturn(
            type_=bytes,
            encoder=encode_text,
            status=status,
            annotation=annt,
            content_type=content_type,
        )
        return rtp
    elif origin is HTML:
        content_type = get_media(origin)
        return EndpointReturn(
            type_=str,
            encoder=encode_text,
            status=status,
            annotation=annt,
            content_type=content_type,
        )
    elif origin is Stream:
        content_type = get_media(origin)
        return EndpointReturn(
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
        return EndpointReturn(
            type_=retype,
            encoder=encode_json,
            status=status,
            annotation=annt,
            content_type=content_type,
        )
    elif origin is Empty:
        return _parse_annotated(origin.__value__, origin, status)
    elif origin is Resp:
        resp = get_args(annt)
        if len(resp) > 1:
            retype, status = resp  # type: ignore
        else:
            retype = resp[0]  # type: ignore
        return parse_single_return(retype, status)
    elif isinstance(origin, TypeAliasType):
        return parse_single_return(origin.__value__, status)
    else:
        raise InvalidParamTypeError(annt)


def _parse_annotated(
    annt: Annotated[Any, "Annotated"],
    origin: Maybe[Any] = MISSING,
    status: int = 200,
) -> "EndpointReturn[Any]":
    if not is_provided(origin):
        origin = lhl_get_origin(annt)
    # encoder = encode_json
    custom_encoder = None
    ret_type, metas = deannotate(annt)

    custom_encoder = get_encoder_from_metas(metas) if metas else None

    if is_resp_mark(ret_type):
        rp = _parse_marked(ret_type, origin, status)
        if custom_encoder:
            return rp.replace(encoder=custom_encoder)
        return rp
    else:
        ret = EndpointReturn(
            type_=ret_type,
            encoder=custom_encoder or encode_json,
            annotation=annt,
            status=status,
        )
        return ret


def _parse_generic(annt: Any, origin: Any, status: int) -> "EndpointReturn[Any]":
    if origin is Annotated or origin in (
        Generator,
        ABCGen,
        AsyncGenerator,
        ABCAsyncGen,
    ):
        return _parse_annotated(annt, origin, status)
    elif is_resp_mark(annt):  # Text,
        return _parse_marked(annt, origin, status)
    elif nested_origin := lhl_get_origin(origin):
        return _parse_generic(origin, nested_origin, status)
    else:  # vanilla case, dict[str, str], list[str], etc.
        if not isinstance(origin, type):
            raise InvalidParamTypeError(annt)
        ret = EndpointReturn[Any](
            type_=origin, encoder=encode_json, annotation=annt, status=status
        )
        return ret


@overload
def parse_single_return[R](
    annt: Maybe[type[R]],
    status: int = 200,
) -> "EndpointReturn[R]": ...


@overload
def parse_single_return(
    annt: Maybe[UnionType | TypeAliasType | GenericAlias],
    status: int = 200,
) -> "EndpointReturn[Any]": ...


# parse_single_return, exclude UnionType, TypeAliasType, GenericAlias


def parse_single_return[R](
    annt: Maybe[type[R] | UnionType | TypeAliasType | GenericAlias],
    status: int = 200,
) -> "EndpointReturn[R]":
    if annt is Parameter.empty or not is_provided(annt):
        return EndpointReturn(encoder=encode_json, status=200)

    # TODO: we need to handle multiple return first

    status = parse_status(status)
    ret_origin = lhl_get_origin(annt) or annt

    if is_union_type(annt):
        """
        TODO:
        we need to handle case of multiple return e.g
        async def userfunc() -> Resp[User, 200] | Resp[Order, 201]
        for decoder it is just User | Order
        but we can show at openapi schema
        """
        annt_args = get_args(annt)
        rets: list[EndpointReturn[Any]] = []

        for arg in annt_args:
            if not is_resp_mark(arg):
                continue
            rets.append(parse_single_return(arg))

        if len(annt_args) > 1 and rets:
            # int | Resp[str] is not valid

            # int | str,  valid
            # Resp[int] | Resp[str], valid
            # Resp[int | str], valid
            raise NotSupportedError("Multiple return param is currently not supported")

        ret = EndpointReturn(
            type_=annt, annotation=annt, encoder=encode_json, status=status
        )

    elif ret_origin or is_resp_mark(annt):
        ret = _parse_generic(annt, ret_origin, status)
    else:
        # default case, should be a single non-generic type,
        # e.g. User, str, bytes, etc.
        if not is_py_singleton(annt) and not isinstance(annt, type):
            raise InvalidParamTypeError(annt)
        ret = EndpointReturn(
            type_=annt,
            annotation=annt,
            encoder=encode_json,
            status=status,
        )
    return ret


# def parse_returns[R](
#     annt: Maybe[type[R] | UnionType | TypeAliasType | GenericAlias],
#     status: int = 200,
# ) -> dict[int, EndpointReturn[Any]]:
#     """
#     Resp[int] | Resp[str] -> Resp[int | str]
#     int | str -> Resp[int | str]

#     Resp[int] | str -> NotSupportedError

#     # Rule: if type is union type
#     # then either every type is Return[T]
#     # or none of them is Return[T]
#     """

#     if not is_union_type(annt):
#         res = parse_single_return(annt)
#         breakpoint()
#         return

#     # if not ty_get_origin is UnionType or Union
#     #      return parse_return

#     # assert count(ret_mark) in metas == len(ret_args) or == 0
#     rorigin, rmetas = get_origin_pro(annt)
#     breakpoint()
