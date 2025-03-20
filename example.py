from contextlib import asynccontextmanager
from typing import Any

from lihil import HTTPException, Json, Lihil, Payload, Resp, Route, Stream, Text, status


class Item(Payload):
    name: str


class Order(Payload):
    id: str
    items: list[Item]
    quantity: int


class OutOfStockError(HTTPException[str]):
    "The order can't be placed because items are out of stock"

    __status__ = 422

    def __init__(self, order: Order):
        detail: str = (
            f"{order} can't be placed, because {order.items} is short in quantity"
        )
        super().__init__(detail)


order_route = Route("/users/{user_id}/orders/{order_id}")


@order_route.get(errors=OutOfStockError)
async def get_order(user_id: str, order_id: str):
    raise OutOfStockError(Order(order_id, [Item("messenger")], 0))


lhl = Lihil[Any](routes=[order_route])


if __name__ == "__main__":
    lhl.run(__file__)
