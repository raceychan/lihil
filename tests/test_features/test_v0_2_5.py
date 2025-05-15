# from typing import TypedDict

# import pytest

# from lihil import Graph, Lihil, LocalClient, Route
# from lihil.interface import Record
# from lihil.interface.marks import AppState
# from lihil.signature import EndpointParser
# from lihil.signature.params import StateParam

# app_state = {}


# def test_app_state():
#     parser = EndpointParser(Graph(), "test")

#     async def create_user(name: AppState[str]): ...

#     res = parser.parse(create_user)
#     param = res.states["name"]
#     assert isinstance(param, StateParam)


# class MyState(TypedDict):
#     name: str


# async def test_ep_with_app_state():

#     route = Route("/test")

#     async def f(name: AppState[str]):
#         assert name == "lihil"

#     route.get(f)

#     async def ls(app: Lihil[None]):
#         yield MyState(name="lihil")

#     lhl = Lihil[MyState](routes=[route], lifespan=ls)
#     lc = LocalClient()
#     res = await lc.call_app(lhl, "GET", "/test")
#     assert res.status_code == 200


# async def test_ep_requires_app_state_but_not_set():

#     route = Route("/test")

#     async def f(name: AppState[str]):
#         assert name == "lihil"

#     route.get(f)

#     lhl = Lihil[None](routes=[route])

#     lc = LocalClient()
#     with pytest.raises(ValueError):
#         await lc.call_app(lhl, "GET", "/test")


# async def test_ep_with_record_state():
#     route = Route("/test")

#     class Engine:
#         def __init__(self, name: str):
#             self.name = name

#     class State(Record):
#         engine: Engine

#     async def ls(app: Lihil[None]):
#         yield State(engine=Engine("lihil"))

#     async def f(engine: AppState[Engine]):
#         assert engine.name == "lihil"

#     route.get(f)
#     lhl = Lihil[None](routes=[route], lifespan=ls)

#     lc = LocalClient()
#     await lc.call_app(lhl, "GET", "/test")


# async def test_ep_ls_resolver():
#     from lihil import AppState, Ignore, Use

#     route = Route("/test")

#     class Engine:
#         def __init__(self, name: str):
#             self.name = name

#     class State(Record):
#         engine: Engine

#     async def ls(app: Lihil[None]):
#         engine = app.graph.resolve(Engine, name="resolved")
#         yield State(engine=engine)

#     async def f(engine: AppState[Engine]):
#         assert engine.name == "resolved"

#     route.get(f)

#     lhl = Lihil[None](routes=[route], lifespan=ls)
#     lc = LocalClient()
#     await lc.send_app_lifespan(lhl)
#     # ep = route.get_endpoint(f)
#     # assert "engine" in ep.sig.dependencies

#     resp = await lc.call_app(lhl, "GET", "/test")
#     assert resp.status_code == 200


# async def test_ep_skip_intermediate_params():
#     from lihil import Use

#     route = Route("/test")

#     class Engine:
#         def __init__(self, name: str):
#             self.name = name

#     @route.get
#     async def f(engine: Use[Engine]):
#         assert engine.name == "resolved"

#     route.setup()
#     ep = route.get_endpoint(f)

#     lc = LocalClient()
#     resp = await lc.call_endpoint(ep, query_params={"name": "resolved"})
#     assert resp.status_code == 200
