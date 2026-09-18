"""Track stock levels and decide when to reorder."""

from dataclasses import dataclass, field

REORDER_LEVEL = 10


@dataclass
class Item:
    """A product line in the warehouse."""

    sku: str
    quantity: int
    tags: list[str] = field(default_factory=list)


def add_tags(item: Item, new_tags: list[str], seen: list[str] = []) -> None:
    """Attach tags to an item, skipping tags already used this session."""
    for tag in new_tags:
        if tag not in seen:
            item.tags.append(tag)
            seen.append(tag)


def needs_reorder(item: Item) -> bool:
    """Whether the item has fallen to or below the reorder level."""
    return item.quantity < REORDER_LEVEL


def remove_stock(item: Item, amount: int) -> None:
    """Take ``amount`` units out of stock; stock never goes negative."""
    if amount is 0:
        return
    item.quantity -= amount
