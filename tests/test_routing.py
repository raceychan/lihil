import re
from typing import Any, Callable

import pytest

from lihil.constant.resp import METHOD_NOT_ALLOWED_RESP
from lihil.endpoint import Endpoint
from lihil.interface import HTTP_METHODS, ASGIApp, IReceive, IScope, ISend
from lihil.routing import Route
from lihil.utils.parse import build_path_regex


async def dummy_endpoint(scope, receive, send):
    """Dummy ASGI endpoint for testing"""
    await send({"type": "http.response.start", "status": 200})
    await send({"type": "http.response.body", "body": b"Test"})


async def dummy_middleware(app: ASGIApp):
    """Dummy middleware for testing"""

    async def middleware(scope: IScope, receive: IReceive, send: ISend):
        await app(scope, receive, send)

    return middleware


class TestRoute:
    def test_route_creation(self):
        """Test route creation and flyweight pattern"""
        # Create a route
        route1 = Route("/test")
        assert route1.path == "/test"

        # Create another route with the same path
        route2 = Route("/test")
        # Should be the same object (flyweight pattern)
        assert route1 is route2

        # Create a route with a different path
        route3 = Route("/other")
        assert route1 is not route3

    def test_route_repr(self):
        """Test route representation"""
        route = Route("/test")

        # Test repr without endpoints
        assert repr(route) == "Route('/test')"

        # Add an endpoint and test repr
        async def test_func():
            return "test"

        route.add_endpoint("GET", func=test_func)
        assert "Route('/test', GET:" in repr(route)
        assert "test_func" in repr(route)

    def test_route_division(self):
        """Test route division operator for creating subroutes"""
        route = Route("/api")
        subroute = route / "users"

        assert subroute.path == "/api/users"
        assert subroute in route.subroutes

    @pytest.mark.asyncio
    async def test_route_call(self):
        """Test route call method"""
        route = Route("/test")

        # Add a GET endpoint
        async def get_handler(scope: IScope, receive: IReceive, send: ISend):
            await send({"type": "http.response.start", "status": 200})
            await send({"type": "http.response.body", "body": b"GET"})

        route.add_endpoint("GET", func=get_handler)

        # Test calling with GET method
        scope = {"method": "GET", "path": "/test"}
        receive = lambda: None
        send_results = []

        async def send(message):
            send_results.append(message)

        await route(scope, receive, send)
        assert len(send_results) == 2
        assert send_results[0]["status"] == 200
        assert send_results[1]["body"] == b"GET"

        # Test calling with unsupported method
        scope = {"method": "POST", "path": "/test"}
        send_results = []

        await route(scope, receive, send)
        assert send_results[0]["status"] == 405  # Method Not Allowed

    def test_is_direct_child_of(self):
        """Test is_direct_child_of method"""
        parent = Route("/api")
        child = Route("/api/users")
        grandchild = Route("/api/users/1")
        unrelated = Route("/other")

        assert child.is_direct_child_of(parent)
        assert not grandchild.is_direct_child_of(parent)
        assert not parent.is_direct_child_of(child)
        assert not unrelated.is_direct_child_of(parent)

    def test_build_stack(self):
        """Test build_stack method"""
        route = Route("/test")

        # Add endpoints
        async def get_handler():
            return "GET"

        async def post_handler():
            return "POST"

        route.add_endpoint("GET", func=get_handler)
        route.add_endpoint("POST", func=post_handler)

        # Build stack
        route.build_stack()

        # Check that call stacks were created
        assert "GET" in route.call_stacks
        assert "POST" in route.call_stacks

    def test_chainup_middlewares(self):
        """Test chainup_middlewares method"""
        route = Route("/test")

        # Add middleware factories
        middleware1 = lambda app: app
        middleware2 = lambda app: app

        route.add_middleware([middleware1, middleware2])

        # Test chainup_middlewares
        result = route.chainup_middlewares(dummy_endpoint)
        assert result is not None

    def test_get_endpoint(self):
        """Test get_endpoint method"""
        route = Route("/test")

        # Add an endpoint
        async def test_func():
            return "test"

        route.add_endpoint("GET", func=test_func)

        # Get endpoint by method
        endpoint = route.get_endpoint("GET")
        assert isinstance(endpoint, Endpoint)
        assert endpoint.func is test_func

        # Get endpoint by function
        endpoint = route.get_endpoint(test_func)
        assert isinstance(endpoint, Endpoint)
        assert endpoint.method == "GET"

        # Test getting non-existent endpoint
        with pytest.raises(KeyError):
            route.get_endpoint("POST")

        with pytest.raises(KeyError):

            async def other_func():
                pass

            route.get_endpoint(other_func)

    def test_sub(self):
        """Test sub method"""
        route = Route("/api")

        # Create subroute
        subroute = route.sub("users")

        assert subroute.path == "/api/users"
        assert subroute in route.subroutes

    def test_match(self):
        """Test match method"""
        # Route with path parameters
        route = Route("/users/{user_id}")

        # Test matching path
        scope = {"path": "/users/123"}
        result = route.match(scope)

        assert result is not None
        assert result["path_params"]["user_id"] == "123"

        # Test non-matching path
        scope = {"path": "/posts/123"}
        result = route.match(scope)

        assert result is None

    def test_add_nodes(self):
        """Test add_nodes method"""
        route = Route("/test")

        # Create a simple node
        class TestNode:
            def __call__(self, *args, **kwargs):
                return "test"

            def resolve_dependencies(self):
                return []

        node = TestNode()

        # Add node
        route.add_nodes(node)

        # Check that node was added to graph
        assert node in route.graph.nodes

    @pytest.mark.asyncio
    async def test_add_endpoint(self):
        """Test add_endpoint method"""
        route = Route("/test")

        # Add endpoint
        async def test_func():
            return "test"

        result = route.add_endpoint("GET", "POST", func=test_func)

        # Check that endpoint was added
        assert "GET" in route.endpoints
        assert "POST" in route.endpoints
        assert route.endpoints["GET"].func is test_func
        assert route.endpoints["POST"].func is test_func
        assert route.path_regex is not None
        assert isinstance(route.path_regex, re.Pattern)

        # Check that function was returned
        assert result is test_func

    def test_add_middleware(self):
        """Test add_middleware method"""
        route = Route("/test")

        # Add single middleware
        middleware1 = lambda app: app
        route.add_middleware(middleware1)

        assert middleware1 in route.middle_factories

        # Add multiple middlewares
        middleware2 = lambda app: app
        middleware3 = lambda app: app
        route.add_middleware([middleware2, middleware3])

        assert middleware2 in route.middle_factories
        assert middleware3 in route.middle_factories

        # Check order (should be middleware2, middleware3, middleware1)
        assert route.middle_factories[0] == middleware2
        assert route.middle_factories[1] == middleware3
        assert route.middle_factories[2] == middleware1

    def test_factory(self):
        """Test factory method"""
        route = Route("/test")

        # Create a simple node
        class TestNode:
            def __call__(self, *args, **kwargs):
                return "test"

            def resolve_dependencies(self):
                return []

        node = TestNode()

        # Create factory
        factory = route.factory(node)

        # Check that factory was created
        assert callable(factory)

    def test_listen(self):
        """Test listen method"""
        route = Route("/test")

        # Create a simple listener
        def test_listener(event):
            pass

        # Register listener
        route.listen(test_listener)

        # Check that listener was registered
        assert test_listener in route.registry.event_mapping

    def test_http_method_decorators(self):
        """Test HTTP method decorators (get, put, post, delete)"""
        route = Route("/test")

        # Test GET decorator
        @route.get
        async def get_handler():
            return "GET"

        assert "GET" in route.endpoints
        assert route.endpoints["GET"].func is get_handler

        # Test PUT decorator
        @route.put
        async def put_handler():
            return "PUT"

        assert "PUT" in route.endpoints
        assert route.endpoints["PUT"].func is put_handler

        # Test POST decorator
        @route.post
        async def post_handler():
            return "POST"

        assert "POST" in route.endpoints
        assert route.endpoints["POST"].func is post_handler

        # Test DELETE decorator
        @route.delete
        async def delete_handler():
            return "DELETE"

        assert "DELETE" in route.endpoints
        assert route.endpoints["DELETE"].func is delete_handler

        # # Test partial application
        # get_decorator = route.get(summary="Test")

        # @get_decorator
        # async def another_get_handler():
        #     return "GET"

        # assert route.endpoints["GET"].config.summary == "Test"
