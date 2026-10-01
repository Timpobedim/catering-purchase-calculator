"""Нормализация названий: «Картофель », «картофель» и «КАРТОФЕЛЬ» — один и тот же продукт, ё = е."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

TRUE_MARKS = {"да", "+", "yes", "true", "1", "истина"}


def normalize_key(value: Any) -> str:
    text = str(value).replace("ё", "е").replace("Ё", "Е")
    return " ".join(text.split()).casefold()


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:  # NaN из pandas
        return True
    return isinstance(value, str) and not value.strip()


def to_decimal(value: Any) -> Decimal:
    """Число из ячейки Excel: 0.2, «0,2», « 1 250,50 » → Decimal.

    Float переводится через str, поэтому 0.1 остаётся 0.1, а не 0.1000000000000000055…
    """
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"«{value}» — не число") from exc


def to_bool(value: Any) -> bool:
    return not is_blank(value) and normalize_key(value) in TRUE_MARKS
