Lihil is ASGI-compatible, meaning that you can apply asgi middlewares to lihil, including those from third-party libraries, such as starlette.


```python
from lihil import Route
from lihil.interface import ASGIApp

type ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


route = Route()
route.add_middleware(lambda app: CORSMiddleware(app, allow_origin="*"))
```


Middleware is injectable, meaning that if your middleware factory requires dependencies, they will be injected dynamically
