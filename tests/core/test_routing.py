import pytest

from lihil import Text

# from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
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
    def middleware_factory(app):
        async def middleware(scope, receive, send):
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
