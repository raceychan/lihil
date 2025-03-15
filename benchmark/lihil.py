from typing import ClassVar


class Payload:
    content_type: ClassVar[str] = "application/json"


class UserIn(Payload):
    uid: str
    email: str
    address: str
