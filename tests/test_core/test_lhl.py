import json
from contextlib import asynccontextmanager

import pytest

from lihil.config import AppConfig, ServerConfig, lhl_get_config
from lihil.constant.resp import ServiceUnavailableResp, lhlserver_static_resp
from lihil.errors import (
    DuplicatedRouteError,
    InvalidLifeSpanError,
    LihilError,
    NotSupportedError,
)
from lihil.interface import ASGIApp, Base
from lihil.lihil import Lihil, lhl_set_config, lifespan_wrapper
from lihil.local_client import LocalClient
from lihil.routing import Route


class CustomAppState(Base):
    counter: int = 0


async def test_lifespan_wrapper_with_none():
    # Test that lifespan_wrapper returns None when given None
    assert lifespan_wrapper(None) is None


async def test_lifespan_wrapper_with_asyncgen():
    # Test with an async generator function
    async def async_gen(app):
        yield "state"

    # Should return the function wrapped with asynccontextmanager
    wrapped = lifespan_wrapper(async_gen)
    assert wrapped is not None
    assert asynccontextmanager(async_gen).__wrapped__ == async_gen


async def test_lifespan_wrapper_with_already_wrapped():
    # Test with an already wrapped function
    @asynccontextmanager
    async def already_wrapped(app):
        yield "state"

    # Should return the same function
    wrapped = lifespan_wrapper(already_wrapped)
    assert wrapped is already_wrapped


async def test_lifespan_wrapper_with_invalid():
    # Test with an invalid function (not an async generator)
    def invalid_func(app):
        return "state"

    # Should raise InvalidLifeSpanError
    with pytest.raises(InvalidLifeSpanError):
        lifespan_wrapper(invalid_func)


async def test_read_config_with_app_config():
    # Test read_config with app_config
    app_config = AppConfig(VERSION="0.2.0")
    lhl_set_config(app_config)
    config = lhl_get_config()
    assert config is app_config
    assert config.VERSION == "0.2.0"


async def test_lihil_basic_routing():
    app = Lihil()

    # Add a route to the root
    async def root_handler():
        return {"message": "Root route"}

    app.get(root_handler)

    # Add a subroute
    users_route = app.sub("users")

    async def get_users():
        return {"message": "Users route"}

    users_route.get(get_users)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test root route
    root_response = await client.call_app(app, "GET", "/")
    assert (await root_response.json())["message"] == "Root route"

    # Test users route
    users_response = await client.call_app(app, "GET", "/users")
    assert (await users_response.json())["message"] == "Users route"

    # Test non-existent route
    not_found_response = await client.call_app(app, "GET", "/nonexistent")
    assert not_found_response.status_code == 404


async def test_lihil_include_routes():
    app = Lihil()

    # Create separate routes
    users_route = Route("/users")

    async def get_users():
        return {"message": "Users route"}

    users_route.get(get_users)

    posts_route = Route("/posts")

    async def get_posts():
        return {"message": "Posts route"}

    posts_route.get(get_posts)

    # Include routes in the app
    app.include_routes(users_route, posts_route)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test users route
    users_response = await client.call_app(app, "GET", "/users")
    assert (await users_response.json())["message"] == "Users route"

    # Test posts route
    posts_response = await client.call_app(app, "GET", "/posts")
    assert (await posts_response.json())["message"] == "Posts route"


async def test_lihil_include_routes_with_subroutes():
    app = Lihil()

    # Create a route with subroutes
    api_route = Route("/api")

    async def api_handler():
        return {"message": "API route"}

    api_route.get(api_handler)

    users_route = api_route.sub("users")

    async def users_handler():
        return {"message": "Users route"}

    users_route.get(users_handler)

    # Include the parent route
    app.include_routes(api_route)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test parent route
    api_response = await client.call_app(app, "GET", "/api")
    assert (await api_response.json())["message"] == "API route"

    # Test subroute
    users_response = await client.call_app(app, "GET", "/api/users")
    assert (await users_response.json())["message"] == "Users route"


async def test_lihil_duplicated_route_error():
    app = Lihil()

    # Add a route to the root
    async def root_handler():
        return {"message": "Root route"}

    app.get(root_handler)

    # Create another root route
    root_route = Route("/")

    async def another_root():
        return {"message": "Another root"}

    root_route.get(another_root)

    # Including the duplicate root should raise an error
    with pytest.raises(DuplicatedRouteError):
        app.include_routes(root_route)


async def test_lihil_static_route():
    app = Lihil()

    # Add a static route
    app.static("/static", "Static content")

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test static route
    static_response = await client.call_app(app, "GET", "/static")
    assert await static_response.text() == "Static content"
    content_type = static_response.headers["content-type"]
    assert content_type == "text/plain; charset=utf-8"


async def test_lihil_static_route_with_callable():
    app = Lihil()

    # Add a static route with a callable
    def get_content():
        return "Generated content"

    app.static("/generated", get_content)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test static route
    response = await client.call_app(app, "GET", "/generated")

    text = await response.text()
    assert text == "Generated content"


async def test_lihil_static_route_with_json():
    app = Lihil()

    # Add a static route with JSON data
    data = {"message": "JSON data"}
    app.static("/json", data, content_type="application/json")

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test static route
    response = await client.call_app(app, "GET", "/json")
    assert (await response.json())["message"] == "JSON data"
    assert "application/json" in response.headers.get("content-type", "")


async def test_lihil_static_route_with_invalid_path():
    app = Lihil()

    # Try to add a static route with a dynamic path
    with pytest.raises(NotSupportedError):
        app.static("/static/{param}", "Content")


async def test_lihil_middleware():
    app = Lihil()

    async def handler():
        return {"message": "Hello"}

    app.get(handler)

    # Define middleware
    def middleware_factory(app):
        async def middleware(scope, receive, send):
            # Modify response
            original_send = send

            async def custom_send(message):
                if message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    if body:
                        data = json.loads(body)
                        data["middleware"] = True
                        message["body"] = json.dumps(data).encode()

                await original_send(message)

            await app(scope, receive, custom_send)

        return middleware

    # Add middleware
    app.add_middleware(middleware_factory)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()
    response = await client.call_app(app, "GET", "/")

    result = await response.json()
    assert result["message"] == "Hello"
    assert result["middleware"] is True


async def test_lihil_middleware_sequence():
    app = Lihil()

    async def handler():
        return {"message": "Hello"}

    app.get(handler)

    # Define middlewares
    def middleware1(app):
        async def mw(scope, receive, send):
            # Add middleware1 flag
            original_send = send

            async def custom_send(message):
                if message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    if body:
                        data = json.loads(body)
                        data["mw1"] = True
                        message["body"] = json.dumps(data).encode()

                await original_send(message)

            await app(scope, receive, custom_send)

        return mw

    def middleware2(app):
        async def mw(scope, receive, send):
            # Add middleware2 flag
            original_send = send

            async def custom_send(message):
                if message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    if body:
                        data = json.loads(body)
                        data["mw2"] = True
                        message["body"] = json.dumps(data).encode()

                await original_send(message)

            await app(scope, receive, custom_send)

        return mw

    # Add middlewares as a sequence
    app.add_middleware([middleware1, middleware2])

    # Initialize app lifespan

    # Test with client
    client = LocalClient()
    response = await client.call_app(app, "GET", "/")

    result = await response.json()
    assert result["message"] == "Hello"
    assert result["mw1"] is True
    assert result["mw2"] is True


async def test_lihil_lifespan():
    # Define a lifespan function
    from typing import AsyncGenerator

    async def csls(app: Lihil) -> AsyncGenerator[None, None]:
        yield

    # Create app with lifespan
    app = Lihil(lifespan=csls)

    # Simulate lifespan events
    scope = {"type": "lifespan"}

    receive_messages = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    receive_index = 0

    async def receive():
        nonlocal receive_index
        message = receive_messages[receive_index]
        receive_index += 1
        return message

    send_messages = []

    async def send(message):
        send_messages.append(message)

    # Start lifespan
    await app(scope, receive, send)

    # Check that startup was completed
    assert any(msg["type"] == "lifespan.startup.complete" for msg in send_messages)

    # Check that shutdown was completed
    assert any(msg["type"] == "lifespan.shutdown.complete" for msg in send_messages)


async def test_lihil_lifespan_startup_error():
    # Define a lifespan function that raises an error during startup
    @asynccontextmanager
    async def error_lifespan(app):
        raise ValueError("Startup error")
        yield

    # Create app with lifespan
    app = Lihil(lifespan=error_lifespan)

    # Simulate lifespan events
    scope = {"type": "lifespan"}

    async def receive():
        return {"type": "lifespan.startup"}

    send_messages = []

    async def send(message):
        send_messages.append(message)

    with pytest.raises(ValueError):
        # Start lifespan
        await app(scope, receive, send)

    # Check that startup failed
    assert any(msg["type"] == "lifespan.startup.failed" for msg in send_messages)


async def test_lihil_lifespan_shutdown_error():
    # Define a lifespan function that raises an error during shutdown
    @asynccontextmanager
    async def error_lifespan(app):
        yield None
        raise ValueError("Shutdown error")

    # Create app with lifespan
    app = Lihil(lifespan=error_lifespan)

    # Simulate lifespan events
    scope = {"type": "lifespan"}

    receive_messages = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
    receive_index = 0

    async def receive():
        nonlocal receive_index
        message = receive_messages[receive_index]
        receive_index += 1
        return message

    send_messages: list[dict[str, str]] = []

    async def send(message):
        send_messages.append(message)

    # Start lifespan
    with pytest.raises(ValueError):
        await app(scope, receive, send)

    # Check that shutdown failed
    assert any(msg["type"] == "lifespan.shutdown.failed" for msg in send_messages)


async def test_static_with_callable():
    """Test line 78: static method with callable content"""
    app = Lihil()

    def get_content():
        return "hello world"

    app.static("/test-callable", get_content)
    assert "/test-callable" in app.static_route.static_cache
    header, body = app.static_route.static_cache["/test-callable"]
    assert body["body"] == b"hello world"


async def test_static_with_json_content():
    """Test line 90: static method with JSON content"""
    app = Lihil()
    data = {"message": "hello world"}

    app.static("/test-json", data, content_type="application/json")
    assert "/test-json" in app.static_route.static_cache
    header, body = app.static_route.static_cache["/test-json"]
    assert json.loads(body["body"].decode()) == data
    assert header["headers"][1][1].startswith(b"application/json")


async def test_init_app_with_routes():
    # Create separate routes
    users_route = Route("/users")

    async def get_users():
        return {"message": "Users route"}

    users_route.get(get_users)

    posts_route = Route("/posts")

    async def get_posts():
        return {"message": "Posts route"}

    posts_route.get(get_posts)

    # Initialize app with routes
    app = Lihil(users_route, posts_route)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test users route
    users_response = await client.call_app(app, "GET", "/users")
    assert (await users_response.json())["message"] == "Users route"

    # Test posts route
    posts_response = await client.call_app(app, "GET", "/posts")
    assert (await posts_response.json())["message"] == "Posts route"

    # Verify routes are in app.routes
    assert len(app.routes) >= 3  # root + users + posts (plus any doc routes)
    assert any(route.path == "/users" for route in app.routes)
    assert any(route.path == "/posts" for route in app.routes)


async def test_include_same_route():
    app = Lihil()

    # Create a route
    users_route = Route("/users")

    async def get_users():
        return {"message": "Users route"}

    users_route.get(get_users)

    # with pytest.raises(DuplicatedRouteError):
    # app.include_routes(users_route)
    app.include_routes(users_route)


async def test_include_root_route_fail():
    app = Lihil()

    # Create a root route
    root_route = Route("/")

    async def root_handler():
        return {"message": "Root route"}

    root_route.get(root_handler)
    app.get(root_handler)

    # Include the root route
    with pytest.raises(DuplicatedRouteError):
        app.include_routes(root_route)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test root route
    response = await client.call_app(app, "GET", "/")
    assert (await response.json())["message"] == "Root route"


async def test_include_root_route_ok():
    app = Lihil()

    # Create a root route
    root_route = Route("/")

    # Include the root route
    app.include_routes(root_route)

    async def root_handler():
        return {"message": "Root route"}

    root_route.get(root_handler)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test root route
    response = await client.call_app(app, "GET", "/")
    assert (await response.json())["message"] == "Root route"


async def test_include_middleware_fail():
    """raise exception in the middleware factory"""
    app = Lihil()

    # Define middleware factory that raises an exception
    def failing_middleware_factory(app):
        raise ValueError("Middleware factory error")

    # Adding the failing middleware should propagate the exception
    app.add_middleware(failing_middleware_factory)

    lc = LocalClient()

    with pytest.raises(LihilError):
        await lc.call_app(app, "GET", "test")

    # with pytest.raises(MiddlewareBuildError):
    #     async with app._on_lifespan(1,2,3):
    #         ...

    print(app)


async def test_a_fail_middleware():
    """a middleware that would raise exception when called"""
    app = Lihil()

    async def handler():
        return {"message": "Hello"}

    app.get(handler)

    # Define middleware that raises an exception when called
    def error_middleware(app):
        async def middleware(scope, receive, send):
            raise ValueError("Middleware execution error")

        return middleware

    # Add the middleware
    app.add_middleware(error_middleware)

    # Initialize app lifespan

    # Test with client - should propagate the error
    client = LocalClient()
    with pytest.raises(ValueError):
        await client.call_app(app, "GET", "/")


async def test_root_put():
    """test a put endpoint registered using lihil.put"""
    app = Lihil()

    # Add a PUT endpoint to the root
    async def put_handler():
        return {"method": "PUT"}

    app.put(put_handler)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test PUT endpoint
    response = await client.call_app(app, "PUT", "/")
    assert (await response.json())["method"] == "PUT"


async def test_root_post():
    """test a post endpoint registered using lihil.post"""
    app = Lihil()

    # Add a POST endpoint to the root
    async def post_handler():
        return {"method": "POST"}

    app.post(post_handler)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test POST endpoint
    response = await client.call_app(app, "POST", "/")
    assert (await response.json())["method"] == "POST"


async def test_root_delete():
    """test a delete endpoint registered using lihil.delete"""
    app = Lihil()

    # Add a DELETE endpoint to the root
    async def delete_handler():
        return {"method": "DELETE"}

    app.delete(delete_handler)

    # Initialize app lifespan

    # Test with client
    client = LocalClient()

    # Test DELETE endpoint
    response = await client.call_app(app, "DELETE", "/")
    assert (await response.json())["method"] == "DELETE"


async def test_add_middleware_sequence():
    """Test lines 208-209: add_middleware with sequence"""
    app = Lihil()

    def middleware1(app: ASGIApp) -> ASGIApp:
        return app

    def middleware2(app: ASGIApp) -> ASGIApp:
        return app

    app.add_middleware([middleware1, middleware2])
    assert len(app.middle_factories) == 2
    assert app.middle_factories[0] == middleware1
    assert app.middle_factories[1] == middleware2


async def test_http_method_decorators():
    """Test lines 233-236, 263, 268, 273: HTTP method decorators"""
    app = Lihil()

    # Test GET decorator
    async def get_handler():
        return {"message": "GET"}

    app.get(get_handler)

    # Test PUT decorator
    async def put_handler():
        return {"message": "PUT"}

    app.put(put_handler)

    # Test POST decorator
    async def post_handler():
        return {"message": "POST"}

    app.post(post_handler)

    # Test DELETE decorator
    async def delete_handler():
        return {"message": "DELETE"}

    app.delete(delete_handler)

    @app.patch
    @app.head
    @app.options
    async def multiple_handler(): ...

    assert len(app.root.endpoints) == 7


async def test_include_routes_with_duplicate_root():
    """Test for DuplicatedRouteError when including routes with duplicate root"""
    app = Lihil()

    # Add an endpoint to root to make it non-empty
    async def root_handler():
        return {"message": "root"}

    new_root = Route("/")
    app.root.add_endpoint("GET", func=root_handler)

    # This should raise DuplicatedRouteError
    with pytest.raises(DuplicatedRouteError):
        app.include_routes(new_root)


async def test_a_problem_endpoint():
    "create a route and an endpoin that would raise HttpException Use LocalClient to test it"
    ...

    from starlette.requests import Request

    from lihil import Lihil
    from lihil.constant import status
    from lihil.local_client import LocalClient
    from lihil.problems import HTTPException, problem_solver

    app = Lihil()

    class CustomError(HTTPException[str]):
        __status__ = status.code(status.NOT_FOUND)
        __problem_type__ = "custom-error"
        __problem_title__ = "Custom Error Occurred"

    async def error_endpoint():
        raise CustomError("This is a custom error message")

    app.sub("/error").get(error_endpoint)

    def custom_error_handler(request: Request, exc: CustomError):
        from lihil.problems import ErrorResponse

        detail = exc.__problem_detail__(request.url.path)
        return ErrorResponse(detail, status_code=detail.status)

    problem_solver(custom_error_handler)

    client = LocalClient()

    # Test the error endpoint
    response = await client.call_app(app, method="GET", path="/error")

    # Verify response status code
    assert response.status_code == 404

    # Verify response content
    data = await response.json()
    assert data["type_"] == "custom-error"
    assert data["title"] == "Custom Error Occurred"
    assert data["detail"] == "This is a custom error message"
    assert data["instance"] == "/error"
    assert data["status"] == 404


async def test_lihil_run():
    lhl = Lihil()

    def mock_run(server_str: str, **others):
        assert server_str == lhl

    lhl.run(__file__, runner=mock_run)


async def test_lihil_run_with_workers():

    config = AppConfig(server=ServerConfig(WORKERS=2))

    lhl = Lihil(app_config=config)

    def mock_run(str_app: str, workers: int, **others):
        assert workers == 2
        assert str_app == "test_lhl:lhl"

    lhl.run(__file__, runner=mock_run)


async def test_service_unavailble():
    msgs: list[dict] = []

    async def _send(msg):
        nonlocal msgs
        msgs.append(msg)

    await ServiceUnavailableResp(_send)


def test_static_resp():
    resp = lhlserver_static_resp(b"hello, world")
    assert (
        resp
        == b"HTTP/1.1 200 OK\r\ncontent-length: 12\r\ncontent-type: text/plain; charset='utf-8'\r\n\r\nhello, world"
    )


async def test_init_lihil_add_middleware_error():

    def m1(app: ASGIApp) -> ASGIApp:
        async def m11(a, b, c):
            pass

    lhl = Lihil(middlewares=[m1])

    lc = LocalClient()
    with pytest.raises(LihilError):
        await lc.call_app(lhl, "GET", "/")


async def test_init_lihil_with_middlewares():

    se = []

    def m1(app: ASGIApp) -> ASGIApp:
        async def m11(a, b, c):
            nonlocal se
            se.append(1)
            await app(a, b, c)

        return m11

    def m2(app: ASGIApp) -> ASGIApp:
        async def m22(a, b, c):
            nonlocal se
            se.append(2)
            await app(a, b, c)

        return m22

    lhl = Lihil(middlewares=[m1, m2])

    lc = LocalClient()
    await lc.call_app(lhl, "GET", "/")
    assert se == [1, 2]


async def test_lhl_http_methods():
    lhl = Lihil()

    @lhl.trace
    @lhl.connect
    async def root():
        return "hello"


async def test_lhl_add_sub_route_before_route():
    parent_route = Route()

    sub_route = parent_route / "sub"

    lhl = Lihil()

    lhl.include_routes(sub_route, parent_route)


async def test_lhl_rerpr():
    config = AppConfig(server=ServerConfig(HOST="127.0.0.1", PORT=8000))
    lhl = Lihil(app_config=config)
    lhl_repr = repr(lhl)
    assert lhl_repr


async def test_lhl_add_seen_subroute():
    parent_route = Route()

    sub_route = parent_route / "sub"
    ssub = parent_route / "second"

    lhl = Lihil()

    lhl.include_routes(parent_route, sub_route, ssub)
