from typing import Any, Literal

from lihil.interface import UNSET, Record, Unset


ERROR_MESSAGES = {
    "topic_not_found": "Topic not found",
    "event_not_found": "Event not found",
    "join_rejected": "Join rejected",
    "invalid_payload": "Invalid payload",
    "internal_error": "Internal error",
    "not_joined": "Topic not joined",
}


class MessageEnvelope(Record):
    topic: str
    event: str
    payload: Any = None
    ref: str | None = None
    join_ref: str | None = None
    event_id: str | None = None
    seq: int | None = None


class SocketError(Record, kw_only=True):
    code: str
    message: str
    detail: Any = None


class ReplyPayload(Record, kw_only=True):
    status: Literal["ok"] = "ok"
    response: Any = None


class ErrorPayload(Record, kw_only=True):
    status: Literal["error"] = "error"
    error: SocketError


def reply_payload(response: Any | None = None) -> ReplyPayload:
    return ReplyPayload(response=response if response is not None else {})


def error_payload(
    code: str,
    message: str | None = None,
    detail: Unset[Any] = UNSET,
) -> ErrorPayload:
    return ErrorPayload(
        error=SocketError(
            code=code,
            message=message or ERROR_MESSAGES.get(code, code),
            detail={} if detail is UNSET else detail,
        )
    )


def is_reply_payload(value: Any) -> bool:
    if isinstance(value, ReplyPayload | ErrorPayload):
        return True
    return isinstance(value, dict) and value.get("status") in {"ok", "error"}


TOPIC_NOT_FOUND = error_payload("topic_not_found")
EVENT_NOT_FOUND = error_payload("event_not_found")
