![Lihil](assets/lhl_logo_ts.png)

# Lihil
**Lihil** &nbsp;*/ˈliːhaɪl/* — 一个**高性能**、**高生产力**和**专业级**的 Web 框架，其愿景是：

> **使 Python 成为 Web 开发的主流编程语言。**

**lihil 的测试覆盖率达到 *100%*，并且是*严格*类型化的。**

[![codecov](https://codecov.io/gh/raceychan/lihil/graph/badge.svg?token=KOK5S1IGVX)](https://codecov.io/gh/raceychan/lihil)
[![PyPI version](https://badge.fury.io/py/lihil.svg)](https://badge.fury.io/py/lihil)
[![License](https://img.shields.io/github/license/raceychan/lihil)](https://github.com/raceychan/lihil/blob/master/LICENSE)
[![Python Version](https://img.shields.io/pypi/pyversions/lihil.svg)](https://pypi.org/project/lihil/)

📚 文档: https://lihil.cc
---

Lihil 是：

- **高生产力**: 符合人体工程学的 API，具有强大的类型支持和针对常见问题的内置解决方案——以及诸如 OpenAPI 文档生成等受欢迎的功能——使用户能够快速构建应用程序，而不会牺牲可扩展性。
- **专业**: Lihil 附带了企业开发必不可少的中间件——例如身份验证、授权、事件发布等。确保从一开始就具有生产力。专为现代开发风格和架构量身定制，包括 TDD 和 DDD。
- **高性能**: 在各种任务和条件下都非常快速——Lihil 是最快的 Python Web 框架之一，性能比同类 ASGI 框架高出 50%–100%，请参阅 [lihil 基准测试](https://github.com/raceychan/lhl_bench)，[独立基准测试](https://web-frameworks-benchmark.netlify.app/result?l=python)。


## 功能特性

### **参数解析与验证**


Lihil 提供了一个高层次的抽象来解析请求，并使用极其高性能的 `msgspec` 库，根据端点类型提示对请求数据进行验证。`msgspec` 的性能非常出色，比 Pydantic v2 快 **12 倍**，内存效率高 **25 倍**。

参见 [基准测试](https://jcristharif.com/msgspec/benchmarks.html)，


- 参数解析: 自动从查询字符串、路径参数、请求头、Cookie 和请求体中解析参数。
- 验证: 参数会自动转换并根据其注解的类型和约束进行验证。
- 自定义解码器: 应用自定义解码器，以最大程度地控制参数的解析和验证方式。

```python
from lihil import Payload, Param, Route, Meta
from typing import Annotated # 类型注解
from .service import get_user_service, UserService

class UserPayload(Payload): # 内存优化的数据结构，不涉及垃圾回收
    user_name: Annotated[str, Param(min_length=1)] # 长度 >= 1 的非空字符串

all_users = Route("users")
all_users.factory(get_user_service)

# 所有参数都会被自动解析和验证
@all_users.sub("{user_id}").post # POST /users/{user_id}
async def create_user(
    user_id: str,                                           # 来自 URL 路径
    auth_token: Annotated[str, Param(alias="x-auth-token")],       # 来自请求头
    user_data: UserPayload,                                 # 来自请求体
    service: UserService
) -> Resp[str, 201]: ...
```


### **依赖注入**:

- **基于类型提示注入工厂函数、普通函数、同步/异步函数、作用域/单例，速度极快。**

```python
from lihil import Route, Ignore, Param, use
from typing import Annotated
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncConnection

# 定义一个异步函数，用于获取数据库连接
async def get_conn(engine: AsyncEngine) -> AsyncConnection:
    async with engine.connect() as conn:
        yield conn # 使用 yield 实现上下文管理，确保连接在使用后关闭

# 定义一个异步函数，用于获取用户列表
async def get_users(conn: AsyncConnection, nums: Annotated[int, Param(lt=100)]) -> Ignore[list[User]]:
    result = await conn.execute(text(f"SELECT * FROM users limit {nums}"))
    return result.fetchall() # 假设 User 是一个定义好的模型

all_users = Route("users")

# 定义一个 GET 请求的路由，路径为 /users
@all_users.get
async def list_users(users: Annotated[list[User], use(get_users)], is_active: bool=True) -> list[[User]]:
    # users 参数通过依赖注入获取 get_users 函数的返回值
    return [u for u in users if u.is_active == is_active]
```

### **WebSocket**

lihil 支持 WebSocket 的使用，你可以使用 `WebSocketRoute.ws_handler` 注册一个处理 WebSocket 连接的函数。

```python
from lihil import WebSocketRoute, WebSocket, Ignore, use
from typing import Annotated
from contextlib import AsyncExitStack, asynccontextmanager

ws_route = WebSocketRoute("web_socket/{session_id}")

# 定义一个异步上下文管理器工厂函数，用于处理 WebSocket 连接的生命周期
@asynccontextmanager
async def ws_factory(ws: WebSocket) -> Ignore[WebSocket]:
    await ws.accept() # 接受 WebSocket 连接
    try:
        yield ws # 将 WebSocket 对象提供给处理器函数
    finally:
        await ws.close() # 在处理器函数执行完毕后关闭 WebSocket 连接

# 注册 WebSocket 处理器函数
@ws_route.ws_handler
async def ws_handler(
    ws: Annotated[WebSocket, use(ws_factory, reuse=False)], # 通过依赖注入获取 WebSocket 对象
    session_id: str, # 从路径参数中获取 session_id
    max_users: int, # 从查询参数中获取 max_users
):
    assert session_id == "session123" and max_users == 5
    await ws.send_text("Hello, world!") # 向客户端发送文本消息

lhl = Lihil()
lhl.include_routes(ws_route)
```

测试

```python
from lihil.vendors import TestClient # 需要安装 httpx 库

client = TestClient(lhl)
with client:
    with client.websocket_connect(
        "/web_socket/session123?max_users=5"
    ) as websocket:
        data = websocket.receive_text() # 接收来自服务器的文本消息
        assert data == "Hello, world!"
```

### **OpenAPI 文档与错误响应生成器**

- Lihil 会根据你的 `Route`/`Endpoint` 自动生成智能且精确的 OpenAPI Schema，支持联合类型（union types）、`oneOf` 响应等特性。

- 你定义的异常类也会自动被转换为一个 `Problem`，并生成对应的详细响应。

```python
class OutOfStockError(HTTPException[str]):
    "无法下单，商品库存不足"
    __status__ = 422

    def __init__(self, order: Order):
        detail: str = f"{order} 无法下单，因为 {order.items} 库存不足"
        super().__init__(detail)
```

当在 `endpoint` 中抛出上述异常时，客户端将响应


### **问题页（Problems Page）**

通过 `Route` 装饰器声明异常类后，这些异常将自动出现在 OpenAPI 的响应结构和问题页面中：


### **内建认证功能（Auth Builtin）**

- Lihil 开箱即用地支持身份验证与权限控制插件。

```python
from lihil import Payload, Route
from lihil.auth.jwt import JWTAuth, JWTPayload
from lihil.auth.oauth import OAuth2PasswordFlow, OAuthLoginForm

class UserProfile(JWTPayload):
    # 借助类型提示（typehint），你可以获得可用声明（claims）的支持
    __jwt_claims__ = {"expires_in": 300}  # JWT 过期时间为 300 秒

    user_id: str = field(name="sub")
    role: Literal["admin", "user"] = "user"

@me.get(auth_scheme=OAuth2PasswordFlow(token_url="token"))
async def get_user(profile: JWTAuth[UserProfile]) -> User:
    assert profile.role == "user"
    return User(name="user", email="user@email.com")

@token.post
async def create_token(credentials: OAuthLoginForm) -> JWTAuth[UserProfile]:
    return UserProfile(user_id="user123")
```

> 当你从 `create_token` 的 endpoint 返回 `UserProfile` 时，它会自动被序列化为一个 JSON Web Token。

### **内建消息系统（Message System Builtin）**

- 可以在应用的任意位置发布命令（command）或事件（event），支持进程内和进程外的事件处理器。Lihil 优化了数据结构，能在几秒钟内处理数百万条来自外部服务的事件数据（包括序列化与反序列化）。

```python
from lihil import Route, EventBus, Empty, Resp, status

@Route("users").post
async def create_user(data: UserCreate, service: UserService, bus: EventBus) -> Resp[Empty, status.Created]:
    user_id = await service.create_user(data)
    await bus.publish(UserCreated(**data.asdict(), user_id=user_id))
```

### **极佳的可测试性（Great Testability）**

- 内建 `LocalClient`，便于对 `endpoint`、路由、中间件、应用进行独立测试。

### **低内存使用**

- lihil 深度优化了内存使用，大幅减少 GC 压力，使得你的服务在高负载下依然稳定可靠。

### **强大的 AI 功能支持**

- lihil 将 AI 作为主要应用场景，相关特性如 SSE、MCP、远程处理器（remote handler）将在 0.3.x 版本前陆续实现：

- [X] SSE
- [ ] MCP
- [ ] Remote Handler

我们还将提供教程，教你如何使用 lihil 开发自己的 AI Agent / 聊天机器人。

## ASGI 兼容性与 Starlette 类型支持

- Lihil 兼容 ASGI，且复用了 Starlette 中的 `Request`、`Response`、`WebSocket` 等接口。
> 这些接口的具体实现可能会有变动。

- 你可以在 `endpoint` 中声明 `Request` 参数，并返回 `Response`（或其子类）实例：

```python
from lihil import Request, Response

@users.post
async def create_user(req: Request):
    return Response(content=b"hello, world")
```

- 任何兼容 ASGIApp 的中间件也都可以用于 lihil，包括来自 Starlette 的中间件。


## 快速开始

```python
from lihil import Lihil

lhl = Lihil()

@lhl.get
async def hello():
    return {"hello": "world!"}
```

```python
from lihil import Lihil, Route, use, EventBus, Param

chat_route = Route("/chats/{chat_id}")
message_route = chat_route / "messages"
UserToken = NewType("UserToken", str)

chat_route.factory(UserService)
message_route.factory(get_chat_service)

@chat_route.factory
def parse_access_token(
    service: UserService, token: UserToken
) -> ParsedToken:
    return service.decrypt_access_token(token)

@message_route.post
async def stream(
   service: ChatService,  # get_chat_service 会被调用，并注入 ChatService 实例
   profile: JWTAuth[UserProfile],  # Auth Bearer: {jwt_token}` 头部会被验证并转换为 UserProfile
   bus: EventBus,
   chat_id: Annotated[str, Param[min_length=1]],  # 校验路径参数 `chat_id` 必须为长度大于 1 的字符串
   data: CreateMessage  # 请求体
) -> Annotated[Stream[GPTMessage], CustomEncoder(gpt_encoder)]:  # 返回服务器端事件
    chat = service.get_user_chat(profile.user_id)
    chat.add_message(data)
    answer = service.ask(chat, model=data.model)
    buffer = []
    async for word in answer:
        buffer.append(word)
        yield word
    await bus.publish(NewMessageCreated(chat, buffer))
```

## 安装

lihil（目前）要求 Python 版本不低于 3.10

### 使用 pip 安装

```bash
pip install lihil
```

### 使用 uv 安装

如果你想使用 uv 安装 lihil

[uv 安装指南](https://docs.astral.sh/uv/getting-started/installation/#installation-methods)

1. 使用 `project_name` 初始化你的 Web 项目

```bash
uv init project_name
```

2. 使用 uv 添加 lihil，这会在独立的虚拟环境中自动解决所有依赖

```bash
uv add lihil
```

## 启动你的应用

### 使用 lihil 启动

#### app.py

```python
from lihil import Lihil

# 你的应用代码

lhl = Lihil()

if __name__ == "__main__":
    lhl.run(__file__)
```

然后在命令行运行：

```bash
uv run python -m myproject.app --server.port=8080
```

你可以通过命令行参数覆盖默认配置。

如果你的应用部署在容器化环境（如 Kubernetes）中，以这种方式提供密钥通常比将其存储在文件中更安全。

使用 `--help` 查看所有可用配置项。

### 使用 uvicorn 启动

lihil 与 ASGI 兼容，你可以使用 ASGI 服务器（如 uvicorn）运行它。

以 `app.py` 为例，默认监听 8000 端口：

1. 在项目根目录下创建 `__main__.py`
2. 在 `__main__.py` 中使用 uvicorn 启动应用

```python
import uvicorn

uvicorn.run(app)
```

## 版本规范

lihil 遵循语义化版本规范，版本号 x.y.z 表示：

- x：主版本号，表示有破坏性更新
- y：次版本号，表示新增特性
- z：补丁号，表示修复 bug 或类型更新

技术上讲，**v1.0.0 将会是第一个稳定主版本**。但从 0.4.x 开始，出现破坏性更新的可能性已经极低。

## 教程

查看详细教程：https://lihil.cc/docs/，内容涵盖：

- 核心概念，如创建 endpoint、路由、middleware 等
- 通过 `pyproject.toml` 或命令行配置应用
- 依赖注入与插件机制
- 测试方法
- 基于类型的消息系统、事件监听器、原子事件处理等
- 错误处理机制
