from starlette.datastructures import URL


class Resource: ...


from dataclasses import dataclass, field
from typing import Hashable, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


# Entity - OrderItem using dataclass
@dataclass
class OrderItem:
    item_id: str
    quantity: int
    price: float

    def total_price(self) -> float:
        return self.quantity * self.price


# Aggregate Root - Order using dataclass
@dataclass
class Order:
    order_id: str
    customer_id: str
    items: List[OrderItem] = field(default_factory=list)

    def total_order_value(self) -> float:
        return sum(item.total_price() for item in self.items)

    def add_item(self, item: OrderItem) -> None:
        self.items.append(item)

    def remove_item(self, item_id: str) -> None:
        self.items = [item for item in self.items if item.item_id != item_id]

    def update_item(self, item_id: str, quantity: int, price: float) -> None:
        for item in self.items:
            if item.item_id == item_id:
                item.quantity = quantity
                item.price = price
                return
        raise ValueError(f"Item with ID {item_id} not found.")


# In-memory "database" to store orders
orders: dict[str, Order] = {}


# Pydantic models for request bodies and responses
class OrderItemCreate(BaseModel):
    item_id: str
    quantity: int
    price: float


class OrderCreate(BaseModel):
    order_id: str
    customer_id: str
    items: List[OrderItemCreate]


class OrderResponse(BaseModel):
    order_id: str
    customer_id: str
    items: List[OrderItemCreate]
    total_value: float


@app.post("/orders")
async def create_order(order: OrderCreate) -> OrderResponse:
    order_items = [
        OrderItem(item.item_id, item.quantity, item.price) for item in order.items
    ]
    new_order = Order(order.order_id, order.customer_id, order_items)
    orders[order.order_id] = new_order
    return OrderResponse(
        order_id=new_order.order_id,
        customer_id=new_order.customer_id,
        items=[
            OrderItemCreate(
                item_id=item.item_id, quantity=item.quantity, price=item.price
            )
            for item in new_order.items
        ],
        total_value=new_order.total_order_value(),
    )


@app.get("/orders/{order_id}")
async def get_order(order_id: str) -> OrderResponse:
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderResponse(
        order_id=order.order_id,
        customer_id=order.customer_id,
        items=[
            OrderItemCreate(
                item_id=item.item_id, quantity=item.quantity, price=item.price
            )
            for item in order.items
        ],
        total_value=order.total_order_value(),
    )


@app.put("/orders/{order_id}")
async def update_order(order_id: str, order: OrderCreate) -> OrderResponse:
    existing_order = orders.get(order_id)
    if not existing_order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Update the items of the order
    for item in order.items:
        try:
            existing_order.update_item(item.item_id, item.quantity, item.price)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return OrderResponse(
        order_id=existing_order.order_id,
        customer_id=existing_order.customer_id,
        items=[
            OrderItemCreate(
                item_id=item.item_id, quantity=item.quantity, price=item.price
            )
            for item in existing_order.items
        ],
        total_value=existing_order.total_order_value(),
    )


@app.delete("/orders/{order_id}")
async def delete_order(order_id: str):
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found")
    del orders[order_id]
    return {"message": "Order deleted successfully"}


@app.post("/orders/{order_id}/items", response_model=OrderResponse)
async def add_item_to_order(order_id: str, item: OrderItemCreate):
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.add_item(OrderItem(item.item_id, item.quantity, item.price))
    return OrderResponse(
        order_id=order.order_id,
        customer_id=order.customer_id,
        items=[
            OrderItemCreate(
                item_id=item.item_id, quantity=item.quantity, price=item.price
            )
            for item in order.items
        ],
        total_value=order.total_order_value(),
    )


@app.delete("/orders/{order_id}/items/{item_id}", response_model=OrderResponse)
async def remove_item_from_order(order_id: str, item_id: str):
    order = orders.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.remove_item(item_id)
    return OrderResponse(
        order_id=order.order_id,
        customer_id=order.customer_id,
        items=[
            OrderItemCreate(
                item_id=item.item_id, quantity=item.quantity, price=item.price
            )
            for item in order.items
        ],
        total_value=order.total_order_value(),
    )


from typing import Annotated, Callable

type State[T] = Annotated[T, "state"]


class UserDTO: ...


class Engine: ...


type JSON[T] = Annotated[T, "_json_serializer"]
type HTML[T] = Annotated[T, "_html_response"]

"""
we provide predefine render, 
and a mapper maps render_key to render function,

user can also register their Render function

def cserializer():
    ...
Customized[T] = Annotated[T, "_customized_serializer"]

render_registry[_customized_serializer] = cserializer
"""


def json_render(): ...


render_registry: dict[Hashable, Callable] = {"_json_serializer": json_render}


def get(path: str, render: Callable | None = None):
    def inner(func):
        return func

    return inner


@get("/user")
async def create_user(engine: State[Engine]) -> JSON[UserDTO]: ...




from fastapi.responses import FileResponse