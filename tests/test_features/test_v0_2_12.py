import pytest

from lihil import LocalClient

# These tests require pydantic; mark for selection in CI
pytestmark = pytest.mark.requires_pydantic


def _user_model():
    from pydantic import BaseModel

    class User(BaseModel):
        name: str
        age: int

    return User


async def test_route_with_pydantic_return():
    User = _user_model()
    async def create_user() -> User:
        return User(name="1", age=2)

    lc = LocalClient()
    ep = await lc.make_endpoint(create_user)

    resp = await lc(ep)
    data = await resp.json()
    assert data == {"name": "1", "age": 2}


async def test_route_with_pydantic_body():
    User = _user_model()
    async def create_user(user: User) -> User:
        return user

    lc = LocalClient()
    ep = await lc.make_endpoint(create_user)

    assert ep.sig.body_param

    resp = await lc(ep, body=User(name="1", age=2))
    data = await resp.json()
    assert data == {"name": "1", "age": 2}


async def test_route_with_generic_pydantic_body():
    User = _user_model()
    async def create_user(user: User) -> list[User]:
        return [user]

    lc = LocalClient()
    ep = await lc.make_endpoint(create_user)

    assert ep.sig.body_param

    resp = await lc(ep, body=User(name="1", age=2))
    data = await resp.json()
    assert data == [{"name": "1", "age": 2}]
