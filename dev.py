from lihil import HTML, Lihil

lhl = Lihil[None]()


@lhl.get
async def home() -> HTML:
    return "<p> hello </p>"
