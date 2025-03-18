import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

import pytest

from lihil.config import AppConfig, OASConfig
from lihil.errors import AppConfiguringError, DuplicatedRouteError, InvalidLifeSpanError
from lihil.lihil import AppState, Lihil, lifespan_wrapper, read_config
from lihil.plugins.testclient import LocalClient
from lihil.routing import Route


class CustomAppState(AppState):
    counter: int = 0


async def initialize_app_lifespan(app: Lihil[Any]) -> None:
    """
    Helper function to initialize a Lihil app by sending lifespan events.
    This ensures the app's call_stack is properly set up before testing routes.
    """
    # Create lifespan scope
    scope = {"type": "lifespan"}

    # Define receive function that sends startup event
    receive_messages = [{"type": "lifespan.startup"}]
    receive_index = 0

    async def receive():
        nonlocal receive_index
        if receive_index < len(receive_messages):
            message = receive_messages[receive_index]
            receive_index += 1
            return message
        return {"type": "lifespan.shutdown"}

    # Define send function that captures responses
    sent_messages = []

    async def send(message):
        sent_messages.append(message)

    # Send lifespan event to initialize the app
    await app(scope, receive, send)

    return sent_messages


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
    app_config = AppConfig(max_thread_workers=8)
    result = read_config(None, app_config)
    assert result is app_config


async def test_read_config_with_both():
    # Test read_config with both config_file and app_config
    app_config = AppConfig()
    with pytest.raises(AppConfiguringError):
        read_config("config.json", app_config)


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
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test root route
    root_response = await client.request(app, "GET", "/")
    assert (await root_response.json())["message"] == "Root route"

    # Test users route
    users_response = await client.request(app, "GET", "/users")
    assert (await users_response.json())["message"] == "Users route"

    # Test non-existent route
    not_found_response = await client.request(app, "GET", "/nonexistent")
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
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test users route
    users_response = await client.request(app, "GET", "/users")
    assert (await users_response.json())["message"] == "Users route"

    # Test posts route
    posts_response = await client.request(app, "GET", "/posts")
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
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test parent route
    api_response = await client.request(app, "GET", "/api")
    assert (await api_response.json())["message"] == "API route"

    # Test subroute
    users_response = await client.request(app, "GET", "/api/users")
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
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test static route
    static_response = await client.request(app, "GET", "/static")
    assert await static_response.text() == "Static content"
    content_type = static_response.headers[b"content-type"]
    assert content_type == b"text/plain; charset=utf-8"


async def test_lihil_static_route_with_callable():
    app = Lihil()

    # Add a static route with a callable
    def get_content():
        return "Generated content"

    app.static("/generated", get_content)

    # Initialize app lifespan
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test static route
    response = await client.request(app, "GET", "/generated")

    text = await response.text()
    assert text == "Generated content"


async def test_lihil_static_route_with_json():
    app = Lihil()

    # Add a static route with JSON data
    data = {"message": "JSON data"}
    app.static("/json", data, content_type="application/json")

    # Initialize app lifespan
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test static route
    response = await client.request(app, "GET", "/json")
    assert (await response.json())["message"] == "JSON data"
    assert b"application/json" in response.headers.get(b"content-type", "")


async def test_lihil_static_route_with_invalid_path():
    app = Lihil()

    # Try to add a static route with a dynamic path
    with pytest.raises(NotImplementedError):
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
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()
    response = await client.request(app, "GET", "/")

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
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()
    response = await client.request(app, "GET", "/")

    result = await response.json()
    assert result["message"] == "Hello"
    assert result["mw1"] is True
    assert result["mw2"] is True


async def test_lihil_lifespan():
    # Define a lifespan function
    @asynccontextmanager
    async def lifespan(app):
        state = CustomAppState()
        state.counter = 1
        yield state
        state.counter = 0

    # Create app with lifespan
    app = Lihil(lifespan=lifespan)

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

    # Check that app state was set
    assert app.app_state is not None
    assert app.app_state.counter == 0  # Should be reset after shutdown


async def test_lihil_lifespan_startup_error():
    # Define a lifespan function that raises an error during startup
    @asynccontextmanager
    async def error_lifespan(app):
        raise ValueError("Startup error")
        yield None

    # Create app with lifespan
    app = Lihil(lifespan=error_lifespan)

    # Simulate lifespan events
    scope = {"type": "lifespan"}

    async def receive():
        return {"type": "lifespan.startup"}

    send_messages = []

    async def send(message):
        send_messages.append(message)

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
    assert "/test-callable" in app.static_cache
    header, body = app.static_cache["/test-callable"]
    assert body["body"] == b"hello world"


async def test_static_with_json_content():
    """Test line 90: static method with JSON content"""
    app = Lihil()
    data = {"message": "hello world"}

    app.static("/test-json", data, content_type="application/json")
    assert "/test-json" in app.static_cache
    header, body = app.static_cache["/test-json"]
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
    app = Lihil(routes=[users_route, posts_route])

    # Initialize app lifespan
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test users route
    users_response = await client.request(app, "GET", "/users")
    assert (await users_response.json())["message"] == "Users route"

    # Test posts route
    posts_response = await client.request(app, "GET", "/posts")
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

    with pytest.raises(DuplicatedRouteError):
        app.include_routes(users_route, users_route)


async def test_include_root_route_fail():
    app = Lihil()

    # Create a root route
    root_route = Route("/")

    async def root_handler():
        return {"message": "Root route"}

    root_route.get(root_handler)

    # Include the root route
    with pytest.raises(DuplicatedRouteError):
        app.include_routes(root_route)

    # Initialize app lifespan
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test root route
    response = await client.request(app, "GET", "/")
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
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test root route
    response = await client.request(app, "GET", "/")
    assert (await response.json())["message"] == "Root route"


async def test_include_middleware_fail():
    """raise exception in the middleware factory"""
    app = Lihil()

    # Define middleware factory that raises an exception
    def failing_middleware_factory(app):
        raise ValueError("Middleware factory error")

    # Adding the failing middleware should propagate the exception
    app.add_middleware(failing_middleware_factory)

    with pytest.raises(ValueError):
        await initialize_app_lifespan(app)


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
    await initialize_app_lifespan(app)

    # Test with client - should propagate the error
    client = LocalClient()
    with pytest.raises(ValueError):
        await client.request(app, "GET", "/")


async def test_root_put():
    """test a put endpoint registered using lihil.put"""
    app = Lihil()

    # Add a PUT endpoint to the root
    async def put_handler():
        return {"method": "PUT"}

    app.put(put_handler)

    # Initialize app lifespan
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test PUT endpoint
    response = await client.request(app, "PUT", "/")
    assert (await response.json())["method"] == "PUT"


async def test_root_post():
    """test a post endpoint registered using lihil.post"""
    app = Lihil()

    # Add a POST endpoint to the root
    async def post_handler():
        return {"method": "POST"}

    app.post(post_handler)

    # Initialize app lifespan
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test POST endpoint
    response = await client.request(app, "POST", "/")
    assert (await response.json())["method"] == "POST"


async def test_root_delete():
    """test a delete endpoint registered using lihil.delete"""
    app = Lihil()

    # Add a DELETE endpoint to the root
    async def delete_handler():
        return {"method": "DELETE"}

    app.delete(delete_handler)

    # Initialize app lifespan
    await initialize_app_lifespan(app)

    # Test with client
    client = LocalClient()

    # Test DELETE endpoint
    response = await client.request(app, "DELETE", "/")
    assert (await response.json())["method"] == "DELETE"


# async def test_add_middleware_sequence():
#     """Test lines 208-209: add_middleware with sequence"""
#     app = Lihil()

#     def middleware1(app: ASGIApp) -> ASGIApp:
#         return app

#     def middleware2(app: ASGIApp) -> ASGIApp:
#         return app

#     app.add_middleware([middleware1, middleware2])
#     assert len(app.middle_factories) == 2
#     assert app.middle_factories[0] == middleware1
#     assert app.middle_factories[1] == middleware2


# async def test_http_method_decorators():
#     """Test lines 233-236, 263, 268, 273: HTTP method decorators"""
#     app = Lihil()

#     # Test GET decorator
#     async def get_handler():
#         return {"message": "GET"}

#     app.get(get_handler)

#     # Test PUT decorator
#     async def put_handler():
#         return {"message": "PUT"}

#     app.put(put_handler)

#     # Test POST decorator
#     async def post_handler():
#         return {"message": "POST"}

#     app.post(post_handler)

#     # Test DELETE decorator
#     async def delete_handler():
#         return {"message": "DELETE"}

#     app.delete(delete_handler)

#     # Verify endpoints were added
#     assert len(app.root.endpoints) == 4


# async def test_include_routes_with_duplicate_root():
#     """Test for DuplicatedRouteError when including routes with duplicate root"""
#     app = Lihil()

#     # Add an endpoint to root to make it non-empty
#     async def root_handler():
#         return {"message": "root"}

#     app.get(root_handler)
#     # Create a new route with path "/"
#     new_root = Route("/")


#     # This should raise DuplicatedRouteError
#     with pytest.raises(DuplicatedRouteError):
#         app.include_routes(new_root)
async def test_a_problem_endpoint():
    "create a route and an endpoin that would raise HttpException Use LocalClient to test it"
    ...

    from starlette.requests import Request

    from lihil import Lihil
    from lihil.constant import status
    from lihil.plugins.testclient import LocalClient
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
    await initialize_app_lifespan(app)

    # Test the error endpoint
    response = await client.request(app, method="GET", path="/error")

    # Verify response status code
    assert response.status_code == 404

    # Verify response content
    data = await response.json()
    assert data["type_"] == "custom-error"
    assert data["title"] == "Custom Error Occurred"
    assert data["detail"] == "This is a custom error message"
    assert data["instance"] == "/error"
    assert data["status"] == 404
