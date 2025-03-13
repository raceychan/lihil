from msgspec import Struct
from msgspec.json import Decoder, Encoder


class User(Struct):
    id: int
    name: str
    email: str


encoder = Encoder()
decoder = Decoder(User)
encode = encoder.encode
decode = decoder.decode


def endpoint(data: bytes) -> bytes:
    received = decode(data)
    respond = User(id=received.id, name=received.name, email=received.email)
    user = encode(respond)
    return user
