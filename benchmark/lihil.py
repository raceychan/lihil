from typing import ClassVar, Literal


class Payload:
    content_type: ClassVar[str] = "application/json"


class UserIn(Payload):
    uid: str
    email: str
    address: str
