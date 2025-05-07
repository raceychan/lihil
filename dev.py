from lihil import HTML, AppConfig, ConfigBase, Lihil


class SBConfig(ConfigBase): ...


lhl = Lihil[None]()


@lhl.get
async def home() -> HTML:
    return "<p> hello </p>"
