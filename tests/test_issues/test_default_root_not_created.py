import pytest

from lihil import Lihil, Route


def test_root_not_created():
    users = Route("/users")
    products = Route("/products")

    lhl = Lihil(users, products)

    @lhl.get
    async def foo(): ...
