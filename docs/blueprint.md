# BluePirnt

| framework | RPS     | decay %   |
| --------- | ------- | --------- |
| asyncio   | 104,380 | (- 100%)  |
| Uvicorn   | 46,426  | (↓ 55.5%) |
| Starlette | 35,433  | (↓ 23.7%) |
| FastAPI   | 17,178  | (↓ 51.5%) |

we can see uvicorn is a big bottleneck

we can directly rewrite uvicorn using as much c as possible

let data validation chain goes almost entirely in c

socket -> -> uvloop -> asyncio -> http parser -> msgspec -> Request

leave DI to python using ididi


roughly 

asyncio -> ASGI in c -> lihil

our expectation is for simple benchmark, we can achieve 60K RPS.


### Idea
we might want to create a `licorne`(unicorn in french) before lihil that acts like a cython version of uvicorn


Layered Infrastructure for High-Performance Integration and Logging



