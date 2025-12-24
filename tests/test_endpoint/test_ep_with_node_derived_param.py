from typing import Annotated

import pytest

from lihil import Ignore, Param, Route, use


async def get_user_id(
    token: Annotated[str, Param("header", alias="Authorization")],
) -> Ignore[str]:
    return token


# async def get_path


class OrderService: ...


async def get_order(
    service: OrderService, user_id: Annotated[str, use(get_user_id)]
): ...


@pytest.mark.debug
def test_parsing_derived_param():
    route = Route()

    route.get(get_order)
    route.setup()
    ep = route.get_endpoint(get_order)
    assert "token" in ep.sig.header_params
