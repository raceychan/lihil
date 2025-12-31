from typing import Any, TypedDict


# from lihil.oas.model import OASResponse


class IOASContent(TypedDict, total=False):
    "A map containing descriptions of potential response payloads"

    schema: dict[str, Any]
    "The schema defining the type used for the response"
    example: Any
    "An example of the response"
    examples: dict[str, Any]
    "Examples of the response"


class IOASResponse(TypedDict, total=False):
    description: str
    "A short description of the response"
    content: dict[str, Any]
    "A map containing descriptions of potential response payloads"
