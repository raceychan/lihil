from types import UnionType

from lihil import HTTPException, Payload, Resp, Route, Text, status
from lihil.config import OASConfig
from lihil.oas.doc_ui import get_problem_ui_html
from lihil.oas.schema import generate_oas, generate_op_from_ep
from lihil.problems import collect_problems


class User(Payload, tag=True):
    name: str
    age: int


class Order(Payload, tag=True):
    id: str
    price: float


user_route = Route("/user/{user_id}/order/{order_id}")


class OrderNotFound(HTTPException[str]):
    "No Such Order!"


@user_route.post(errors=OrderNotFound)
async def get_order(
    user_id: str | int, order_id: str, q: int | str, l: str, u: User
) -> Order | User: ...


@user_route.get
async def get_hello(
    user_id: str, order_id: str, q: int, l: str, u: User
) -> Resp[Text, status.OK]: ...


oas_config = OASConfig()


def test_get_order_schema():
    current_ep = user_route.endpoints["POST"]
    ep_rt = current_ep.deps.return_param
    assert isinstance(ep_rt.type_, UnionType)
    components = {"schemas": {}}
    ep_oas = generate_op_from_ep(
        current_ep, components["schemas"], oas_config.problem_path
    )


def test_get_hello_return():
    current_ep = user_route.get_endpoint(get_hello)
    ep_rt = current_ep.deps.return_param
    assert ep_rt.type_ is bytes


def test_generate_oas():
    "https://editor.swagger.io/"
    oas = generate_oas([user_route], oas_config, "0.1.0")
    assert oas


def test_generate_problems():
    ui = get_problem_ui_html(title="API Problem Details", problems=collect_problems())
    assert ui
