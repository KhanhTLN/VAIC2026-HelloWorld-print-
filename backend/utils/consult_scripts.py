"""
Category trigger keywords only — questions are NOT fixed.
Criteria come from product.specifications of the matched category.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryTrigger:
    name: str
    trigger_keywords: tuple[str, ...]
    category_hints: tuple[str, ...]


CATEGORY_TRIGGERS: list[CategoryTrigger] = [
    CategoryTrigger(
        name="tủ lạnh",
        trigger_keywords=("tủ lạnh", "tu lanh", "tủ mát", "tu mat", "tủ đông", "tu dong"),
        category_hints=("tủ mát", "tủ đông", "tủ lạnh"),
    ),
    CategoryTrigger(
        name="điện thoại",
        trigger_keywords=("điện thoại", "dien thoai", "smartphone"),
        category_hints=("điện thoại di động", "điện thoại", "smartphone"),
    ),
    CategoryTrigger(
        name="máy nước nóng",
        trigger_keywords=("máy nước nóng", "may nuoc nong", "bình nóng lạnh"),
        category_hints=("máy nước nóng", "nước nóng"),
    ),
    CategoryTrigger(
        name="máy giặt",
        trigger_keywords=("máy giặt", "may giat"),
        category_hints=("máy giặt",),
    ),
    CategoryTrigger(
        name="máy rửa chén",
        trigger_keywords=("máy rửa chén", "may rua chen", "rửa bát"),
        category_hints=("máy rửa chén",),
    ),
]


def find_trigger(message: str) -> CategoryTrigger | None:
    text = message.lower()
    for trigger in CATEGORY_TRIGGERS:
        if any(keyword in text for keyword in trigger.trigger_keywords):
            return trigger
    return None
