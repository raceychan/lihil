# Minibench

This is a benchmark shows the performance difference between lihil and other asgi frameworks.

Note thta This benchmark will be updated frequently and test results are subject to change.

## Context

### Hardware

AMD Ryzen 9 7950X 16-Core Processor  4.50 GHz

RAM 64.0 GB (63.1 GB usable)

internet ethernet controller i225v

### OS

- Ubuntu 20.04.6 LTS

### packages

- python == 3.12
- uvloop==0.21.0
- uvicorn==0.34.0
- lihil==0.1.3
- fastapi==0.115.8

## Parsing path, query, body and inject dependency

## lihil v0.1.3

```python
profile_route = Route("profile/{pid}")


class Engine: ...


def get_engine() -> Engine:
    return Engine()


profile_route.factory(get_engine)


@profile_route.post
async def profile(pid: str, q: int, user: User, engine: Engine) -> User:
    return User(id=user.id, name=user.name, email=user.email)

lhl = Lihil()
lhl.include_routes(profile_route)

if __name__ == "__main__":
    uvicorn.run(lhl, access_log=None, log_level="warning")
```

### result

```bash
wrk -t4 -c64 'http://localhost:8000/profile/p?q=5' -s scripts/post.lua
Running 10s test @ http://localhost:8000/profile/p?q=5
  4 threads and 64 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency     1.72ms  319.52us  21.22ms   95.77%
    Req/Sec     9.32k   474.64    14.12k    91.00%
  371254 requests in 10.05s, 54.52MB read
Requests/sec:  36955.88
Transfer/sec:      5.43MB
```

## FastAPI v0.115.8

```python
from fastapi import Fastapi

class Engine: ...

def get_engine() -> Engine:
    return Engine()

profile_route = APIRouter()

@profile_route.post("/profile/{pid}")
async def profile(
    pid: str, q: int, user: User, engine: Annotated[Engine, Depends(get_engine)]
) -> User:
    return User(id=user.id, name=user.name, email=user.email)


app = FastAPI()
app.include_router(profile_route)

if __name__ == "__main__":
    uvicorn.run(app, access_log=None, log_level="warning")
```

### result

```bash
Running 10s test @ http://localhost:8000/profile/p?q=5
  4 threads and 64 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency     4.98ms    1.11ms  62.49ms   93.44%
    Req/Sec     3.23k   243.30     5.96k    94.50%
  128792 requests in 10.07s, 21.13MB read
Requests/sec:  12783.44
Transfer/sec:      2.10MB
```