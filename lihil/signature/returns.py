from inspect import Parameter
from types import GenericAlias, UnionType
from typing import Any, AsyncGenerator, Generator, Generic, Literal, TypeGuard, get_args

from typing_extensions import TypeAliasType

from lihil.constant.status import code as get_status_code
from lihil.constant.status import is_status
from lihil.errors import InvalidStatusError, NotSupportedError, StatusConflictError
from lihil.interface import (
    MISSING,
    Base,
    CustomEncoder,
    IEncoder,
    Maybe,
    RegularTypes,
    T,
    is_provided,
)
from lihil.interface.marks import ResponseMark, extract_resp_type
from lihil.utils.json import encoder_factory
from lihil.utils.typing import get_origin_pro, is_union_type

# from lihil.config import AppConfig


def parse_status(status: Any) -> int:
    status_type = type(status)

    try:
        if status_type is int:
            return status
        elif status_type is str:
            return int(status)
        else:
            return get_status_code(status)
    except Exception:
        raise InvalidStatusError(status)


async def agen_encode_wrapper(
    async_gen: AsyncGenerator[T, None], encoder: IEncoder
) -> AsyncGenerator[bytes, None]:
    async for res in async_gen:
        yield encoder(res)


def syncgen_encode_wrapper(
    sync_gen: Generator[T, None, None], encoder: IEncoder
) -> Generator[bytes, None, None]:
    for res in sync_gen:
        yield encoder(res)


def is_empty_return(t: Any):
    if t is None or t is Literal[None]:
        return True
    return False


def is_annotated(annt: Any) -> TypeGuard[RegularTypes]:
    return is_provided(annt) and annt is not Parameter.empty


class EndpointReturn(Base, Generic[T]):
    type_: Maybe[type[T] | UnionType | GenericAlias | TypeAliasType | None]
    status: int
    encoder: IEncoder
    mark_type: ResponseMark = "json"
    annotation: Any = MISSING
    content_type: str | None = "application/json"

    def __post_init__(self):
        if self.status < 200 or self.status in (204, 205, 304):
            if not is_empty_return(self.type_):
                raise StatusConflictError(self.status, self.type_)

    def __repr__(self) -> str:
        return f"Return<{self.annotation}, {self.status}>"


DEFAULT_RETURN = EndpointReturn(
    type_=MISSING, status=200, encoder=encoder_factory(), annotation=MISSING
)


def parse_return_pro(
    ret_type: Any, annotation: Any, metas: list[Any] | None
) -> EndpointReturn[Any]:
    if metas is None:
        return EndpointReturn(
            type_=ret_type,
            annotation=annotation,
            encoder=encoder_factory(ret_type),
            status=200,
        )

    encoder = None
    status = 200
    mark_type = "json"
    content_type = "application/json"
    for idx, meta in enumerate(metas):
        if isinstance(meta, CustomEncoder):
            encoder = meta.encode
        elif resp_type := extract_resp_type(meta):
            mark_type = resp_type
            if resp_type == "empty":
                content_type = None
            else:
                if resp_type == "stream":
                    ret_type = get_args(annotation)[0]
                content_type = metas[idx + 1]
        elif is_status(meta):
            status = get_status_code(meta)
        else:
            continue

    content, _ = content_type.split("/") if content_type else (None, None)
    if content == "text":
        if encoder is None:
            encoder = encoder_factory(content_type=content)
        ret_type = bytes
    else:
        if encoder is None:
            encoder = encoder_factory(ret_type)

    ret = EndpointReturn(
        type_=ret_type,
        encoder=encoder,
        status=status,
        mark_type=mark_type,
        annotation=annotation,
        content_type=content_type,
    )
    return ret


def parse_returns(
    annt: Maybe[type[Any] | UnionType | TypeAliasType | GenericAlias],
) -> dict[int, EndpointReturn[Any]]:
    if not is_annotated(annt):
        return {DEFAULT_RETURN.status: DEFAULT_RETURN}

    if not is_union_type(annt):
        rt_type, metas = get_origin_pro(annt)
        res = parse_return_pro(rt_type, annt, metas)
        return {res.status: res}
    else:
        unions = get_args(annt)
        temp_union = [get_origin_pro(utype) for utype in unions]

        resp_cnt = 0
        for _, ret_meta in temp_union:

            if not ret_meta:
                continue
            if any(is_status(meta) for meta in ret_meta):
                resp_cnt += 1

        if resp_cnt and resp_cnt != len(unions):
            raise NotSupportedError("union size and status dismatched")

        if resp_cnt == 0:  # Union[int, str]
            union_origin, union_meta = get_origin_pro(annt)
            resp = parse_return_pro(union_origin, annt, union_meta)
            return {resp.status: resp}
        else:
            resps = [
                parse_return_pro(uorigin, uorigin, umeta)
                for uorigin, umeta in temp_union
            ]
            # idea: number of unique status code should match with number of resp marks
            return {resp.status: resp for resp in resps}
