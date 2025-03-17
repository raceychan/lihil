from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from lihil.config import AppConfig, OASConfig
from lihil.errors import AppConfiguringError, DuplicatedRouteError, InvalidLifeSpanError
from lihil.lihil import AppState, Lihil
from lihil.plugins.testclient import LocalClient
from lihil.routing import Route


class CustomAppState(AppState):
    counter: int = 0


async def initialize_app_lifespan(app: Lihil) -> None:
    """
    Helper function to initialize a Lihil app by sending lifespan events.
    This ensures the app's call_stack is properly set up before testing routes.
    """
    # Create lifespan scope
    scope = {"type": "lifespan"}

    # Define receive function that sends startup event
    async def receive():
        return {"type": "lifespan.startup"}

    # Define send function that captures responses
    async def send(message):
        pass

    # Send lifespan event to initialize the app
    await app(scope, receive, send)


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
