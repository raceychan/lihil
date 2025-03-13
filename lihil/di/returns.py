from inspect import Parameter
from types import UnionType
from typing import Any, Callable, TypeAliasType, cast, get_args, get_origin

from lihil.constant.status import code as get_status_code
from lihil.interface import MISSING, Base, IEncoder, Maybe, is_provided
from lihil.interface.marks import HTML, Json, Resp, Stream, Text, is_resp_mark
from lihil.utils.phasing import encode_json, encode_text
from lihil.utils.typing import flatten_annotated


class CustomEncoder:
    encode: Callable[[Any], bytes]


class ReturnParam[T](Base):
    encoder: IEncoder[T]
    status: int
    type_: Maybe[type[T]] | UnionType = MISSING
    content_type: str = "application/json"
    origin: Any = MISSING

    def __repr__(self) -> str:
        return f"Return({self.origin}, {self.status})"


def parse_status(status: Any) -> int:
    status_type = type(status)
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


def analyze_markedret[R](annt: Any, origin: Any, status: Any):
    status = parse_status(status)
    if is_resp_mark(annt):
        origin = get_origin(annt) or annt
        if origin is Text:
            content_type = get_media(origin)
            rtp = ReturnParam(
                type_=bytes,
                encoder=encode_text,
                status=status,
                origin=annt,
                content_type=content_type,
            )
            return cast(ReturnParam[R], rtp)
        elif origin is HTML:
            raise NotImplementedError
        elif origin is Stream:
            raise NotImplementedError
        elif origin is Json:
            type_args = get_args(annt)
            retype, *_ = type_args
            content_type = get_media(origin)
            return ReturnParam(
                type_=retype,
                encoder=encode_json,
                status=status,
                origin=annt,
                content_type=content_type,
            )
        elif origin is Resp:
            resp = get_args(annt)
            if len(resp) > 1:
                retype, status = resp  # type: ignore
            else:
                retype = resp[0]  # type: ignore
            return analyze_markedret(retype, retype, status)
        else:
            raise NotImplementedError
    else:
        # TODO: this should be a recursive case
        """
        MP3 = Annotated[bytes, CustomEncoder(encode_mp3)]
        async def get_mp3() -> Resp[MP3, 200]: ...
        """
        type_args = get_args(annt)
        retype, *_ = type_args
        metas = flatten_annotated(annt)
        for m in metas:
            # CutsomReturnMark, include encoder, content_type
            if isinstance(m, CustomEncoder):
                return ReturnParam(
                    type_=retype,
                    encoder=m.encode,
                    origin=annt,
                    status=status,
                )
        else:
            return ReturnParam(
                type_=retype,
                encoder=encode_json,
                origin=annt,
                status=status,
            )


def analyze_return[R](
    annt: Maybe[type[R] | UnionType], status: int = 200
) -> ReturnParam[R]:
    annt = annt if annt is not Parameter.empty else MISSING

    if not is_provided(annt):
        return ReturnParam(encoder=encode_json, status=200)

    status = parse_status(status)

    if isinstance(annt, UnionType):
        annt_args = get_args(annt)
        if not any(is_resp_mark(arg) for arg in annt_args):
            ret = ReturnParam(
                type_=annt, origin=annt, encoder=encode_json, status=status
            )
        else:
            raise NotImplementedError
    elif origin := get_origin(annt):
        ret = analyze_markedret(annt, origin, status)
    elif is_resp_mark(annt):
        # mark without generic var, Text, HTML, etc
        ret = analyze_markedret(annt, annt, status)
    else:
        # default case, should be a single type, e.g. create_user() -> User: ...
        ret = ReturnParam(
            type_=annt,
            origin=annt,
            encoder=encode_json,
            status=status,
        )
    return ret
