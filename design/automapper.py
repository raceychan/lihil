from typing import Callable, Any

Filter = Callable[[str], bool]

def mapper_maker(
    source_type: type | None = None,
    target_type: type | None = None,
    includes: set[str] | Filter | None = None,
    excludes: set[str] | Filter | None = None,
    partial: bool = True,
    name_mapping: dict[str, str] | None = None,
    match_strategy: Callable[[str], str] | None = None,
) -> Callable[[Any], Any]:
    if callable(includes):
        include_fields = filter(includes, fields)
    else:
        include_fields = includes
    
