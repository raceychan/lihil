# from typing import Mapping

# from lihil.vendor_types import Response


# class LHLResponse(Response):
#     mediate_type: str = "application/json"
#     charset = "utf-8"

#     def __init__(
#         self,
#         content: bytes,
#         status_code: int = 200,
#         headers: Mapping[str, str] | None = None,
#         mediate_type: str | None = None,
#     ):
#         self.body = content
#         self.status_code = status_code
#         self.media_type = mediate_type or self.mediate_type
#         self.init_headers(headers)


# class StaticResponse(Response):
#     ...
