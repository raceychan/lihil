import pytest

from lihil import Text
from lihil.interface import ASGIApp, IReceive, IScope, ISend

# from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
from lihil.plugins.bus import Event
from lihil.plugins.testclient import LocalClient
from lihil.routing import Route


async def test_route_flyweight_pattern():
    # Test flyweight pattern
    route1 = Route("/test")
    route2 = Route("/test")
    assert route1 is route2

    # Different paths create different instances
    route3 = Route("/other")
    assert route1 is not route3


async def test_route_truediv_operator():
    # Test the / operator for creating subroutes
    main_route = Route("/api")
    sub_route = main_route / "users"

    assert sub_route.path == "/api/users"
    assert sub_route in main_route.subroutes


async def test_route_is_direct_child_of():
    parent = Route("/api")
    direct_child = Route("/api/users")
    indirect_child = Route("/api/users/details")
    unrelated = Route("/other")

    assert direct_child.is_direct_child_of(parent)
    assert not indirect_child.is_direct_child_of(parent)
    assert not unrelated.is_direct_child_of(parent)


async def test_route_match():
    route = Route("/users/{user_id}")

    # Add an endpoint to ensure path_regex is created
    async def get_user(user_id: str):
        return {"id": user_id}

    route.get(get_user)

    # Now the path_regex should be created

    # Valid match
    scope = {"path": "/users/123"}
    matched_scope = route.match(scope)

    assert matched_scope is not None
    assert matched_scope["path_params"] == {"user_id": "123"}

    # No match
    scope = {"path": "/posts/123"}
    assert route.match(scope) is None


async def test_route_call_with_valid_method():
    route = Route("/test")

    # Create a proper endpoint function that returns a response
    async def test_handler() -> Text:
        return "Test response"

    # Add endpoint
    route.get(test_handler)

    # Test client
    client = LocalClient()
    response = await client.call_route(route, "GET")

    assert response.status_code == 200
    assert await response.text() == "Test response"


async def test_route_call_with_invalid_method():
    route = Route("/test")

    # Create a proper endpoint function
    async def test_handler():
        return "Test response"

    # Add endpoint for GET only
    route.get(test_handler)

    # Test client with POST (not supported)
    with pytest.raises(ValueError, match="Route does not support POST method"):
        client = LocalClient()
        await client.call_route(route, "POST")


async def test_route_call_method_not_allowed():
    route = Route("/test")

    # Create a proper endpoint function
    async def test_handler():
        return "Test response"

    # Add endpoint for GET only
    route.get(test_handler)

    # Use LocalClient to make a POST request directly to the route
    client = LocalClient()

    # We can't use call_route because it checks for method support before calling
    # So we'll use request directly
    response = await client.request(app=route, method="POST", path="/test")

    # Verify METHOD_NOT_ALLOWED response was received
    assert response.status_code == 405


async def test_route_add_endpoint():
    route = Route("/users/{user_id}")

    async def get_user(user_id: str):
        return {"id": user_id, "name": "Test User"}

    # Add endpoint
    route.add_endpoint("GET", func=get_user)

    assert "GET" in route.endpoints
    assert route.path_regex is not None

    # Test with client
    client = LocalClient()
    response = await client.call_route(route, "GET", path_params={"user_id": "123"})

    assert response.status_code == 200
    result = await response.json()
    assert result["id"] == "123"


async def test_route_http_method_decorators():
    route = Route("/api")

    async def get_handler():
        return {"message": "GET"}

    route.get(get_handler)

    async def post_handler():
        return {"message": "POST"}

    route.post(post_handler)

    async def put_handler():
        return {"message": "PUT"}

    route.put(put_handler)

    async def delete_handler():
        return {"message": "DELETE"}

    route.delete(delete_handler)

    assert "GET" in route.endpoints
    assert "POST" in route.endpoints
    assert "PUT" in route.endpoints
    assert "DELETE" in route.endpoints

    # Test with client
    client = LocalClient()

    get_response = await client.call_route(route, "GET")
    assert (await get_response.json())["message"] == "GET"

    post_response = await client.call_route(route, "POST")
    assert (await post_response.json())["message"] == "POST"

    put_response = await client.call_route(route, "PUT")
    assert (await put_response.json())["message"] == "PUT"

    delete_response = await client.call_route(route, "DELETE")
    assert (await delete_response.json())["message"] == "DELETE"


async def test_route_middleware():
    route = Route("/test")

    async def handler():
        return {"message": "Hello"}

    route.get(handler)

    # Define middleware
    def middleware_factory(app: ASGIApp):
        async def middleware(scope: IScope, receive: IReceive, send: ISend):
            # Modify response
            original_send = send

            async def custom_send(message):
                if message["type"] == "http.response.body":
                    # Modify the response body
                    body = message.get("body", b"")
                    if body:
                        import json

                        data = json.loads(body)
                        data["middleware"] = True
                        message["body"] = json.dumps(data).encode()

                await original_send(message)

            await app(scope, receive, custom_send)

        return middleware

    # Add middleware
    route.add_middleware(middleware_factory)

    # Test with client
    client = LocalClient()
    response = await client.call_route(route, "GET")

    result = await response.json()
    assert result["message"] == "Hello"
    assert result["middleware"] is True


async def test_route_get_endpoint():
    route = Route("/test")

    async def handler():
        return {"message": "Hello"}

    route.get(handler)

    # Get by method string
    endpoint = route.get_endpoint("GET")
    assert endpoint.func is handler

    # Get by function reference
    endpoint = route.get_endpoint(handler)
    assert endpoint.method == "GET"

    # Non-existent endpoint
    with pytest.raises(KeyError):
        route.get_endpoint("POST")


async def test_route_sub():
    main_route = Route("/api")

    # Create subroute
    users_route = main_route.sub("users")

    assert users_route.path == "/api/users"
    assert users_route in main_route.subroutes

    # Test nested routes
    async def main_handler():
        return {"route": "main"}

    main_route.get(main_handler)

    async def users_handler():
        return {"route": "users"}

    users_route.get(users_handler)

    # Test with client
    client = LocalClient()

    main_response = await client.call_route(main_route, "GET")
    assert (await main_response.json())["route"] == "main"

    users_response = await client.call_route(users_route, "GET")
    assert (await users_response.json())["route"] == "users"


async def test_route_build_stack():
    route = Route("/test")

    async def handler():
        return "Test response"

    route.get(handler)

    # Initially call_stacks should be empty
    assert not route.call_stacks

    # Build the stack
    route.build_stack()

    # Now call_stacks should have the GET method
    assert "GET" in route.call_stacks


async def test_route_add_nodes():
    route = Route("/test")

    # Create a simple node
    class TestNode:
        def __call__(self, value: str):
            return f"Processed: {value}"

    # Add the node to the route
    route.add_nodes(TestNode)

    # Verify the node was added to the graph
    assert len(route.graph._nodes) > 0


async def test_route_factory():
    route = Route("/test")

    # Create a simple node
    class TestNode:
        def __call__(self, value: str):
            return f"Processed: {value}"

    # Use factory to create a node
    node_factory = route.factory(TestNode)

    # Verify the factory works
    assert callable(node_factory)


async def test_route_listen():
    route = Route("/test")

    # Create a simple listener
    def test_listener(event: Event):
        pass

    # Register the listener
    route.listen(test_listener)

    assert route.has_listener(test_listener)

    # Verify the listener was registered


async def test_route_with_listeners_param():
    # Create a simple listener
    def test_listener(event: Event):
        pass

    # Create route with listeners
    route = Route("/test", listeners=[test_listener])

    # Verify the listener was registered
    assert route.has_listener(test_listener)


async def test_route_decorator_style():
    route = Route("/test")

    # Test decorator style for GET
    async def get_handler() -> Text:
        return "GET response"

    # Test decorator style for POST
    async def post_handler():
        return "POST response"

    route.get(get_handler)
    route.post(post_handler)

    # Test decorator style for PUT
    async def put_handler():
        return "PUT response"

    route.put(put_handler)

    # Test decorator style for DELETE
    async def delete_handler():
        return "DELETE response"

    route.delete(delete_handler)

    # Verify all endpoints were registered
    assert "GET" in route.endpoints
    assert "POST" in route.endpoints
    assert "PUT" in route.endpoints
    assert "DELETE" in route.endpoints

    # Test with client
    client = LocalClient()

    get_response = await client.call_route(route, "GET")
    assert await get_response.text() == "GET response"


async def test_route_redirect_not_implemented():
    route = Route("/test")

    # Test the redirect method which is not implemented
    with pytest.raises(NotImplementedError):
        route.redirect(route.__call__, id="123")


async def test_route_repr():
    route = Route("/test")

    # Test repr without endpoints
    assert repr(route) == "Route('/test')"

    # Add an endpoint
    async def handler():
        return "Test"

    route.get(handler)

    # Test repr with endpoints
    assert "Route('/test', GET:" in repr(route)
    assert handler.__name__ in repr(route)


async def test_route_call_with_existing_call_stack():
    route = Route("/test")

    async def handler():
        return "Test response"

    route.get(handler)

    # Make first request to build call stack
    client = LocalClient()
    response1 = await client.call_route(route, "GET")
    assert response1.status_code == 200

    # Make second request which should use existing call stack
    response2 = await client.call_route(route, "GET")
    assert response2.status_code == 200

    # Verify call_stacks has the GET method
    assert "GET" in route.call_stacks


async def test_route_get_endpoint_not_found():
    route = Route("/test")

    async def handler():
        return "Test"

    route.get(handler)

    # Try to get a non-existent endpoint by method
    with pytest.raises(KeyError):
        route.get_endpoint("POST")

    # Try to get a non-existent endpoint by function
    async def another_handler():
        return "Another"

    with pytest.raises(KeyError):
        route.get_endpoint(another_handler)


async def test_route_add_endpoint_with_existing_path_regex():
    route = Route("/users/{user_id}")

    # Add first endpoint to create path_regex
    async def get_user(user_id: str):
        return {"id": user_id, "method": "GET"}

    route.get(get_user)

    # Add second endpoint when path_regex already exists
    async def update_user(user_id: str):
        return {"id": user_id, "method": "PUT"}

    route.put(update_user)

    # Test both endpoints
    client = LocalClient()

    get_response = await client.call_route(route, "GET", path_params={"user_id": "123"})
    get_result = await get_response.json()
    assert get_result["method"] == "GET"

    put_response = await client.call_route(route, "PUT", path_params={"user_id": "123"})
    put_result = await put_response.json()
    assert put_result["method"] == "PUT"


async def test_route_add_middleware_sequence():
    route = Route("/test")

    async def handler():
        return {"message": "Hello"}

    route.get(handler)

    # Define middleware factories
    def middleware1(app):
        async def mw(scope, receive, send):
            # Modify response
            original_send = send

            async def custom_send(message):
                if message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    if body:
                        import json

                        data = json.loads(body)
                        data["mw1"] = True
                        message["body"] = json.dumps(data).encode()

                await original_send(message)

            await app(scope, receive, custom_send)

        return mw

    def middleware2(app):
        async def mw(scope, receive, send):
            # Modify response
            original_send = send

            async def custom_send(message):
                if message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    if body:
                        import json

                        data = json.loads(body)
                        data["mw2"] = True
                        message["body"] = json.dumps(data).encode()

                await original_send(message)

            await app(scope, receive, custom_send)

        return mw

    # Add middlewares as a sequence
    route.add_middleware([middleware1, middleware2])

    # Test with client
    client = LocalClient()
    response = await client.call_route(route, "GET")

    result = await response.json()
    assert result["message"] == "Hello"
    assert result["mw1"] is True
    assert result["mw2"] is True


async def test_route_has_listener():
    route = Route("/test")

    # Create listeners
    def listener1(event: Event):
        pass

    def listener2(event: Event):
        pass

    # Register only one listener
    route.listen(listener1)

    # Test has_listener
    assert route.has_listener(listener1) is True
    assert route.has_listener(listener2) is False
