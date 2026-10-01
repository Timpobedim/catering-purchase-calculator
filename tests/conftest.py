from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from banquet_calc.demo import build_demo
from banquet_calc.models import CardKind, Ingredient, Menu, MenuItem, Product, Section, TechCard
from banquet_calc.normalize import normalize_key

SECTIONS = {
    "овощи": Section("овощи", "Овощи", 1),
    "молочные": Section("молочные", "Молочные продукты", 2),
}


def product(
    name: str, section: str = "овощи", *, pack: str = "1", price: str = "100", waste: bool = False
) -> Product:
    return Product(
        key=normalize_key(name),
        name=name,
        section=section,
        unit="кг",
        pack_size=Decimal(pack),
        pack_price=Decimal(price),
        supplier="Поставщик",
        waste_allowed=waste,
    )


def card(
    name: str, *ingredients: tuple[str, str] | tuple[str, str, str], kind: CardKind = CardKind.DISH
) -> TechCard:
    items = []
    for row, spec in enumerate(ingredients, start=2):
        ingredient, quantity, *waste = spec
        items.append(
            Ingredient(
                name=ingredient,
                key=normalize_key(ingredient),
                quantity=Decimal(quantity),
                waste_factor=Decimal(waste[0]) if waste else None,
                row=row,
            )
        )
    return TechCard(name=name, key=normalize_key(name), kind=kind, ingredients=tuple(items))


def menu(items: dict[str, int], *cards: TechCard) -> Menu:
    return Menu(
        items=tuple(MenuItem(dish, normalize_key(dish), portions) for dish, portions in items.items()),
        techcards={item.key: item for item in cards},
        local_products={},
        margin_percent=None,
    )


def catalog(*products: Product) -> dict[str, Product]:
    return {item.key: item for item in products}


def write_book(path: Path, sheets: dict[str, list[dict[str, Any]]]) -> Path:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=name, index=False)
    return path


@pytest.fixture
def demo_files(tmp_path: Path) -> tuple[Path, Path]:
    """(меню, номенклатура) — демо-книги, созданные заново для каждого теста."""
    return build_demo(tmp_path / "examples")
