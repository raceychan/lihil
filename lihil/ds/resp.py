from lihil.interface import IReceive, IScope, ISend
from lihil.vendors import Response


class StaticResponse(Response):
    def __init__(
        self,
        content: bytes,
        media_type: str,
        status_code: int = 200,
    ) -> None:
        self.status_code = status_code
        self.media_type = media_type
        self.body = content
        content_length_header = (
            b"content-length",
            str(len(self.body)).encode("latin-1"),
        )
        content_type_header = (
            b"content-type",
            (
                f"{self.media_type}; charset=utf-8"
                if self.media_type.startswith("text/")
                else f"{self.media_type}"
            ).encode("latin-1"),
        )
        self.raw_headers = [content_length_header, content_type_header]

    async def __call__(self, scope: IScope, receive: IReceive, send: ISend):
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.raw_headers,
            }
        )
        await send({"type": "http.response.body", "body": self.body})
