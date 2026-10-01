from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from conftest import write_book

from banquet_calc.calculation import CalculationError
from banquet_calc.models import CardKind
from banquet_calc.workbook import read_catalog, read_menu

SECTIONS = [{"Раздел": "Овощи", "Название в закупке": "Овощи и зелень", "Порядок": 1}]


def product_row(name: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Наименование": name,
        "Раздел": "овощи",
        "Ед. изм.": "кг",
        "Фасовка": 2.5,
        "Цена за упаковку": "1 250,50",
        "Поставщик": "Овощебаза",
        "Коэф. отхода допустим": "да",
    }
    row.update(overrides)
    return row


def test_catalog_is_parsed_with_normalized_keys(tmp_path: Path) -> None:
    path = write_book(
        tmp_path / "catalog.xlsx",
        {
            "Разделы": SECTIONS,
            "Продукты": [
                product_row("  Сёмга   филе "),
                product_row("Соль", **{"Коэф. отхода допустим": ""}),
            ],
        },
    )

    sections, products = read_catalog(path)

    assert sections["овощи"].title == "Овощи и зелень"
    salmon = products["семга филе"]
    assert salmon.name == "Сёмга   филе"
    assert (salmon.pack_size, salmon.pack_price, salmon.waste_allowed) == (
        Decimal("2.5"),
        Decimal("1250.50"),
        True,
    )
    assert products["соль"].waste_allowed is False


def test_missing_column_is_named(tmp_path: Path) -> None:
    rows = [{k: v for k, v in product_row("Соль").items() if k != "Фасовка"}]
    path = write_book(tmp_path / "catalog.xlsx", {"Разделы": SECTIONS, "Продукты": rows})

    with pytest.raises(CalculationError, match="лист «Продукты»: нет столбцов «Фасовка»"):
        read_catalog(path)


def test_catalog_problems_are_collected_with_rows(tmp_path: Path) -> None:
    path = write_book(
        tmp_path / "catalog.xlsx",
        {
            "Разделы": SECTIONS,
            "Продукты": [
                product_row("Сёмга"),
                product_row("Семга"),
                product_row("Соль", **{"Фасовка": "много"}),
                product_row("Кефир", **{"Раздел": "молочные"}),
            ],
        },
    )

    with pytest.raises(CalculationError) as error:
        read_catalog(path)

    problems = error.value.problems
    assert "строка 3: «Семга» встречается дважды" in problems[0]
    assert "строка 4: «много» — не число" in problems[1]
    assert "раздел «молочные» не описан" in problems[2]


def test_menu_fills_card_names_down_and_reads_parameters(tmp_path: Path) -> None:
    path = write_book(
        tmp_path / "menu.xlsx",
        {
            "Меню": [{"Блюдо": "Оливье", "Порций": 40}],
            "Техкарты": [
                {
                    "Техкарта": "Оливье",
                    "Тип": "Блюдо",
                    "Ингредиент": "Картофель отварной",
                    "Количество": 0.05,
                },
                {
                    "Техкарта": None,
                    "Тип": None,
                    "Ингредиент": "Укроп",
                    "Количество": "0,002",
                    "Коэф. отхода": 1.35,
                },
                {
                    "Техкарта": "Картофель отварной",
                    "Тип": "полуфабрикат",
                    "Ингредиент": "Картофель",
                    "Количество": 1,
                },
            ],
            "Своя номенклатура": [product_row("Сырная тарелка")],
            "Параметры": [{"Параметр": "Запас, %", "Значение": "7%"}],
        },
    )

    menu = read_menu(path)

    olivier = menu.techcards["оливье"]
    assert olivier.kind is CardKind.DISH
    assert [(item.key, item.quantity, item.waste_factor, item.row) for item in olivier.ingredients] == [
        ("картофель отварной", Decimal("0.05"), None, 2),
        ("укроп", Decimal("0.002"), Decimal("1.35"), 3),
    ]
    assert menu.techcards["картофель отварной"].kind is CardKind.SEMI_FINISHED
    assert "сырная тарелка" in menu.local_products
    assert menu.margin_percent == Decimal(7)


def test_menu_problems_are_reported(tmp_path: Path) -> None:
    path = write_book(
        tmp_path / "menu.xlsx",
        {
            "Меню": [{"Блюдо": "Оливье", "Порций": "сорок"}],
            "Техкарты": [
                {"Техкарта": "Оливье", "Тип": "салат", "Ингредиент": "Картофель", "Количество": 1},
                {"Техкарта": "Морс", "Тип": "блюдо", "Ингредиент": "Клюква", "Количество": "два"},
            ],
        },
    )

    with pytest.raises(CalculationError) as error:
        read_menu(path)

    text = str(error.value)
    assert "лист «Меню», строка 2: «сорок» — не число" in text
    assert "тип «салат»" in text
    assert "лист «Техкарты», строка 3: «два» — не число" in text


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(CalculationError, match="Файл не найден"):
        read_menu(tmp_path / "нет.xlsx")
