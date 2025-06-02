# from starlette.requests import Request


# class LHLRequest(Request):
#     """
#     a faster version of starlette.Request, sharing the same interface

#     improvement

#     - url
#     - body
#     - json
#     - form

#     """

#     ...

# async def _get_form(
#     self,
#     *,
#     max_files: int | float = 1000,
#     max_fields: int | float = 1000,
#     max_part_size: int = 1024 * 1024,
# ) -> FormData:
#     ...
