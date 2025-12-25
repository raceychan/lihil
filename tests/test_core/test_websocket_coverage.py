"""
Tests to improve coverage for websocket functionality.
"""

from unittest.mock import Mock

import pytest

from lihil.errors import NotSupportedError
from lihil.routing import EndpointProps, Graph
from lihil.websocket import WebSocketEndpoint, WebSocketRoute


class TestWSEndpointCoverage:
    """Test WebSocketEndpoint error cases and edge scenarios."""

    def test_ws_endpoint_sync_function_error(self):
        """Test WebSocketEndpoint raises error for sync functions."""
        route = "/ws"

        def sync_function():
            return "sync"

        with pytest.raises(
            NotSupportedError, match="sync function is not supported for websocket"
        ):
            WebSocketEndpoint(route, sync_function, {})

    def test_ws_endpoint_properties(self):
        """Test WSEndpoint property getters."""
        route = "/ws"
        props = EndpointProps()

        async def async_function():
            pass

        endpoint = WebSocketEndpoint(route, async_function, props)

        assert endpoint.unwrapped_func == async_function
        assert endpoint.props == props


class TestWSRouteCoverage:
    """Test WebSocketRoute error cases and edge scenarios."""

    def test_ws_route_setup_empty_endpoint_error(self):
        """Test WebSocketRoute.setup raises error when endpoint is None."""
        route = WebSocketRoute("/ws")

        with pytest.raises(RuntimeError):
            route.setup()

    def test_ws_route_setup_body_param_error(self):
        """Test WebSocketRoute.setup raises error for body params in websocket."""
        route = WebSocketRoute("/ws")

        # Mock endpoint
        async def ws_handler(body: dict):  # This should trigger body param error
            pass

        route.endpoint(ws_handler)

        # Mock the endpoint parser to return a signature with body_param
        mock_sig = Mock()
        mock_sig.body_param = Mock()  # Non-None body param

        mock_parser = Mock()
        mock_parser.parse.return_value = mock_sig

        with pytest.raises(
            NotSupportedError, match="Websocket does not support body param"
        ):
            route.endpoint_parser = mock_parser
            route.setup(graph=Graph())

    def test_ws_route_merge_with_endpoint(self):
        """Test WebSocketRoute.merge when subroute has endpoint."""
        parent_route = WebSocketRoute("/ws")

        # Create subroute with endpoint
        sub_route = WebSocketRoute("/sub")

        async def sub_handler():
            pass

        sub_route.endpoint(sub_handler)

        # Test include/merge
        parent_route.merge(sub_route)

        assert len(parent_route._subroutes) == 1
        new_sub = parent_route._subroutes[0]
        assert new_sub.endpoint is not None

    def test_ws_route_merge_without_endpoint(self):
        """Test WebSocketRoute.merge when subroute has no endpoint."""
        parent_route = WebSocketRoute("/ws")
        sub_route = WebSocketRoute("/sub")  # No endpoint set

        parent_route.merge(sub_route)

        assert len(parent_route._subroutes) == 1
        new_sub = parent_route._subroutes[0]
        assert not new_sub.is_setup

    def test_ws_route_chainup_plugins(self):
        """Test WebSocketEndpoint.chainup_plugins functionality."""
        from lihil.routing import EndpointProps

        route = "/ws"

        async def ws_handler():
            pass

        # Create plugins
        plugin1 = Mock()
        plugin2 = Mock()
        plugin1.return_value = ws_handler
        plugin2.return_value = ws_handler

        props = EndpointProps(plugins=[plugin1, plugin2])
        endpoint = WebSocketEndpoint(route, ws_handler, props)

        # Mock signature
        sig = Mock()

        result = endpoint.chainup_plugins(ws_handler, sig, Graph())

        # Verify plugins were called
        assert plugin1.called
        assert plugin2.called
        assert result == ws_handler

    def test_ws_route_chainup_plugins_duplicate_plugins(self):
        """Test WebSocketEndpoint.chainup_plugins with duplicate plugins."""
        from lihil.routing import EndpointProps

        route = "/ws"

        async def ws_handler():
            pass

        # Same plugin instance used twice
        plugin = Mock()
        plugin.return_value = ws_handler

        props = EndpointProps(plugins=[plugin, plugin])  # Same plugin twice
        endpoint = WebSocketEndpoint(route, ws_handler, props)

        sig = Mock()

        result = endpoint.chainup_plugins(ws_handler, sig, Graph())

        # Plugin should only be called once despite being in list twice
        assert plugin.call_count == 1
        assert result == ws_handler
