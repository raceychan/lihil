import re
from re import Pattern
from typing import Any, Literal, get_origin

from starlette.routing import compile_path

RE_PATH_KEYS = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
"Must be a valid python variable name?"

DYNAMIC_PATH = re.compile(r"^(?!.*\{.*\}).*$")


def to_kebab_case(string: str) -> str:
    """
    Convert a string to kebab-case, properly handling acronyms.

    Examples:
        HTTPException -> http-exception
        UserAPI -> user-api
        OAuth2PasswordBearer -> oauth2-password-bearer
    """
    if not string:
        return string

    result = ""
    in_acronym = False

    for i, char in enumerate(string):
        if char.isupper():
            if (i > 0 and not string[i - 1].isupper()) or i == 0:
                if i > 0:  # Don't add hyphen at the beginning
                    result += "-"
                result += char.lower()
                in_acronym = True

            elif in_acronym and (i == len(string) - 1 or not string[i + 1].isupper()):
                result += char.lower()
                in_acronym = False
            else:
                result += char.lower()
        else:
            if i > 0 and string[i - 1].isupper() and not in_acronym:
                result = result[:-1] + "-" + result[-1] + char
            else:
                result += char
            in_acronym = False

    result = re.sub(r"[\s_]+", "-", result)
    return result


def find_path_keys(path: str) -> tuple[str]:
    return tuple(RE_PATH_KEYS.findall(path))


def is_plain_path(path: str) -> bool:
    return bool(DYNAMIC_PATH.match(path))


def handle_path(path: str) -> str:
    path = path.replace(" ", "")

    if len(path) > 1 and path.endswith("/"):
        raise ValueError("Trailing slash is not allowed")

    if not path.startswith("/"):
        return f"/{path}"
    return path


def merge_path(parent_path: str, sub_path: str) -> str:
    """
    parent_path = "/users"
    sub_path = "/{user_id}"
    merge_path(parent_path, sub_path) == "uesrs/{user_id}"
    """

    current_path = (
        parent_path[:-1] + sub_path
        if parent_path[-1] == "/"
        else parent_path + sub_path
    )
    return current_path


def generate_route_tag(path: str) -> str:
    """
    Given a URL path, returns the first non-dynamic component of the path using regex.

    Dynamic components are defined as those enclosed in curly braces, like {user_id}.

    Examples:
      "/users/{user_id}/orders/{order_id}" returns "users"
      "/products/categories/{category_id}" returns "products"
      "/users" returns "users"
    """
    # Split the path into components
    components = path.strip("/").split("/")

    # Use regex to filter out dynamic components

    for comp in components:
        if re.match(r"^\{.*\}$", comp):
            continue
        tag = comp
        break
    else:
        tag = ""

    # Return the first non-dynamic component, or empty string if there are none
    return tag


def build_path_regex(path: str, path_params: None = None) -> Pattern[str]:
    # TODO: write our own compile function to support more complex type in path
    path_regex, _, _ = compile_path(path)
    return path_regex


def parse_header_key(name: str, metas: list[Any]) -> str:
    try:
        header_key = metas[0]
    except IndexError:
        return to_kebab_case(name)

    if isinstance(header_key, str):
        return header_key

    if get_origin(header_key) is Literal:
        return header_key.__args__[0]

    raise NotImplementedError("invalid header key")


def trimdoc(doc: str | None):
    """
    remove empty characters before and after doc
    """
    if not doc:
        return doc

    return doc.strip()
