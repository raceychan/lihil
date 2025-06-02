from dataclasses import dataclass
from dataclasses import field as dfield
from typing import TypedDict

import pytest
from msgspec import field
from typing_extensions import NotRequired

from lihil import Annotated, LocalClient, Param, Struct
from lihil.errors import InvalidParamPackError


async def test_ep_with_dict():

    async def login(creds: Annotated[dict[str, str], Param("header")]): ...

    lc = LocalClient()

    with pytest.raises(InvalidParamPackError):
        await lc.make_endpoint(login)


async def test_ep_with_typedict_param_collection():
    class TDCred(TypedDict):
        name: str
        age: int
        email: str
        is_admin: NotRequired[bool]

    async def login(creds: Annotated[TDCred, Param("header")]): ...

    lc = LocalClient()

    ep = await lc.make_endpoint(login)

    sig = ep.sig

    assert len(sig.header_params) == 4
    assert sig.header_params["name"]
    assert sig.header_params["age"]
    assert sig.header_params["email"]
    assert sig.header_params["is_admin"]


async def test_ep_with_dataclass_param_collection():
    @dataclass
    class DSCred:
        name: str
        age: int
        email: str
        is_admin: bool | None = None

    async def login(creds: Annotated[DSCred, Param("header")]): ...

    lc = LocalClient()

    ep = await lc.make_endpoint(login)

    sig = ep.sig

    assert len(sig.header_params) == 4
    assert sig.header_params["name"]
    assert sig.header_params["age"]
    assert sig.header_params["email"]
    assert sig.header_params["is_admin"]


async def test_ep_with_dataclass_param_collection_and_factory():
    @dataclass
    class DSCred:
        name: str
        age: int
        email: str
        is_admin: bool | None = dfield(default_factory=lambda: True)

    async def login(creds: Annotated[DSCred, Param("header")]): ...

    lc = LocalClient()

    with pytest.raises(InvalidParamPackError):
        await lc.make_endpoint(login)


async def test_ep_with_struct_param_collection():
    class STCred(Struct):
        name: str
        age: int
        email: str
        is_admin: bool | None = None

    async def login(creds: Annotated[STCred, Param("header")]): ...

    lc = LocalClient()

    ep = await lc.make_endpoint(login)

    sig = ep.sig

    assert len(sig.header_params) == 4
    assert sig.header_params["name"]
    assert sig.header_params["age"]
    assert sig.header_params["email"]
    assert sig.header_params["is_admin"]


async def test_ep_with_struct_param_collection_and_factory():
    class STCred(Struct):
        name: str
        age: int
        email: str
        is_admin: bool | None = field(default_factory=lambda: True)

    async def login(creds: Annotated[STCred, Param("header")]): ...

    lc = LocalClient()

    with pytest.raises(InvalidParamPackError):
        await lc.make_endpoint(login)


async def test_ep_with_struct_param_collection_and_different_source():

    class STCred(Struct):
        name: str
        age: int
        email: Annotated[str, Param("query")]
        is_admin: Annotated[bool | None, Param(alias="is-admin")] = None

    async def login(creds: Annotated[STCred, Param("header")]): ...

    lc = LocalClient()

    ep = await lc.make_endpoint(login)

    sig = ep.sig

    assert len(sig.header_params) == 3
    assert sig.header_params["name"]
    assert sig.header_params["age"]
    assert sig.header_params["is_admin"]
    assert sig.header_params["is_admin"].alias == "is-admin"

    assert sig.query_params["email"]


async def test_ep_with_struct_param_collection_with_default():

    class STCred(Struct):
        name: str
        age: int
        email: Annotated[str, Param("query")]
        is_admin: Annotated[bool | None, Param(alias="is-admin")] = None

    async def login(creds: Annotated[STCred, Param("header")] = 1): ...

    lc = LocalClient()

    with pytest.raises(InvalidParamPackError):
        await lc.make_endpoint(login)


async def test_ep_with_struct_param_collection_with_union():

    class STCred(Struct):
        name: str
        age: int
        email: Annotated[str, Param("query")]
        is_admin: Annotated[bool | None, Param(alias="is-admin")] = None

    async def login(creds: Annotated[STCred | None, Param("header")] = None): ...

    lc = LocalClient()

    with pytest.raises(InvalidParamPackError):
        await lc.make_endpoint(login)
