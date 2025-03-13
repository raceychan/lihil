def all_subclasses(cls: type, __seen__: set[type] | None = None) -> set[type]:
    """
    Get all subclasses of a class recursively, avoiding repetition.

    Args:
        cls: The class to get subclasses for
        __seen__: Internal set to track already processed classes

    Returns:
        A set of all subclasses
    """
    if __seen__ is None:
        __seen__ = set()

    result = set()
    for subclass in cls.__subclasses__():
        if subclass not in __seen__:
            __seen__.add(subclass)
            result.add(subclass)
            result.update(all_subclasses(subclass, __seen__))
    return result
