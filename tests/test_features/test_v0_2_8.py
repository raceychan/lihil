from lihil import Route


async def test_route_merge_endpoint_plugin_with_smae_plugin():
    called: list[str] = []

    def dummy_plugin(*args):
        called.append("plugin called")

    route = Route(plugins=[dummy_plugin])

    async def dummy_handler(): ...

    route.get(dummy_handler, plugins=[dummy_plugin])

    ep = route.get_endpoint(dummy_handler)

    # merged plugin from route and endpoint so we have two plugins
    assert ep.props.plugins == [dummy_plugin]

    # but only one plugin called since we deduplicate using id(plugin)
    assert called == ["plugin called"]


async def test_route_merge_endpoint_plugin():
    called: list[str] = []

    def dummy_plugin(*args):
        called.append("plugin called")

    def dummy_plugin2(*args):
        called.append("called again")

    route = Route(plugins=[dummy_plugin])

    async def dummy_handler(): ...

    route.get(dummy_handler, plugins=[dummy_plugin2])

    ep = route.get_endpoint(dummy_handler)

    # merged plugin from route and endpoint so we have two plugins
    assert ep.props.plugins == [dummy_plugin, dummy_plugin2]

    # but only one plugin called since we deduplicate using id(plugin)
    assert called == ["plugin called", "called again"]
