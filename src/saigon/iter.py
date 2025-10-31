from typing import Iterable, Optional, Callable

__all__ = [
    'is_true_or_valid',
    'first',
    'contains'
]


def is_true_or_valid[ItemType](item: ItemType) -> bool:
    """
    Checks the input value is not none or if it's True

    Args:
        item: Input value to check against

    Returns:
        True if the input value is not None, or its
        actual value is `ItemType` is bool
    """
    return (
        item is not None
        and item is True if isinstance(item, bool)
        else True
    )


def first[ItemType](
        item_list: Iterable[ItemType],
        condition: Optional[Callable[[ItemType], bool]] = is_true_or_valid
) -> Optional[ItemType]:
    """
    Returns the first item in `item_list` that meets the specified `condition`.
    Args:
        item_list: Iterable of items of type `ItemType`
        condition (Optional): Condition logic to apply to an item.
            Default is set to `is_true_or_valid`

    Returns:
        First item that meets the condition
    """
    for item in item_list:
        if condition(item):
            return item

    return None


def contains[ItemType](
        item_list: Iterable[ItemType],
        condition: Callable[[ItemType], bool] = is_true_or_valid
) -> bool:
    """
    Checks whether `item_list` contains at least one element that meets the
    specified `condition`.

    Args:
        item_list: Iterable of items of type `ItemType`
        condition (Optional): Condition logic to apply to an item.
        Default is set to `is_true_or_valid`

    Returns:
        True if at least one item meets the condition
    """
    return first(item_list, condition) is not None
