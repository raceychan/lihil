from typing import Any

AnyDict = dict[Any, Any]


def both_instance(a: Any, b: Any, *target_types: type) -> bool:
    return isinstance(a, target_types) and isinstance(b, target_types)


def deep_update(original: AnyDict, update_data: AnyDict) -> AnyDict:
    """
    Recursively update a nested dictionary without overwriting entire nested structures.
    """

    for key, value in update_data.items():
        if key not in original:
            original[key] = value
        else:
            ori_val = original[key]
            if both_instance(ori_val, value, dict):
                deep_update(ori_val, value)
            else:
                original[key] = value
    return original


def deep_merge(original: AnyDict, tobe_merged: AnyDict) -> AnyDict:
    """
    Recursively merge two dictionary, if a key exists in both dicts, merge two values if both are containers, else update.
    """

    for key, value in tobe_merged.items():
        if key not in original:
            original[key] = value
        else:
            ori_val = original[key]
            if both_instance(ori_val, value, dict):
                deep_merge(ori_val, value)
            elif both_instance(ori_val, value, list, tuple):
                original[key] = ori_val + value
            elif both_instance(ori_val, value, set):
                original[key] = ori_val.union(value)
            else:
                original[key] = value
    return original
