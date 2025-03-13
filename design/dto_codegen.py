from dataclasses import dataclass
from typing import Any, Callable

from starlette.requests import Request
from starlette.routing import Route

type MatchCondition = Callable[[str], bool]

type FieldMapper = Callable[[str], str] | Callable[[str, Any], tuple[str, Any]]


def DTOMaker(generate_code: bool = False):
    """
    generate dto based on domain model, create a default mapper

    PublicUser = DTOMaker(User, excludes=lambda x: x.starts_with("_"))

    # in endpoint
    public_user = PublicUser.from_user(user)
    return public_user
    """

    ...


def mapper_maker(
    source_type: type | None = None,
    target_type: type | None = None,
    includes: set[str] | MatchCondition | None = None,
    excludes: set[str] | MatchCondition | None = None,
    partial: bool = True,
    name_mapping: dict[str, str] | None = None,
    match_strategy: Callable[[str], str] | None = None,
) -> Callable[[Any], Any]:
    """
    create a mapper and converts a domain object to a dto

    user_mapper = mapper_maker()
    user = User()
    public_user = user_mapper(user)
    """

    if isinstance(includes, set) and isinstance(excludes, set):
        overlap = includes.intersection(excludes)
        if overlap:
            raise Exception(f"{includes} and {excludes} conflicts, {overlap=}")

    def mapper(source: Any): ...

    return mapper


@dataclass
class User:
    user_id: str
    name: str
    email: str
    password_hash: bytes

    __mapper__ = mapper_maker(
        excludes={"password_hash"},
        match_strategy=lambda x: x if x.startswith("user_") else f"user_{x}",
    )


@dataclass
class PublicUser:
    user_id: str
    user_name: str
    user_email: str
