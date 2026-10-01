"""Чтение номенклатуры и файла меню из Excel.

Структура книг описана в README. Ошибки формата собираются все сразу и называют лист, строку
и столбец — пользователь исправляет Excel за один заход, а не по одной ошибке за запуск.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from banquet_calc.calculation import CalculationError
from banquet_calc.models import CardKind, Ingredient, Menu, MenuItem, Product, Section, TechCard
from banquet_calc.normalize import is_blank, normalize_key, to_bool, to_decimal

PRODUCT_COLUMNS = ["Наименование", "Раздел", "Ед. изм.", "Фасовка", "Цена за упаковку", "Поставщик"]
WASTE_FLAG_COLUMN = "Коэф. отхода допустим"
EXCEL_HEADER_ROW = 1  # номер строки заголовка в Excel: данные начинаются со второй


def _read_sheets(path: Path) -> dict[str, pd.DataFrame]:
    try:
        return pd.read_excel(path, sheet_name=None, dtype=object)
    except FileNotFoundError as exc:
        raise CalculationError([f"Файл не найден: {path}"]) from exc
    except (ValueError, OSError) as exc:
        raise CalculationError([f"Не удалось прочитать {path.name}: {exc}"]) from exc


def _require(sheets: dict[str, pd.DataFrame], sheet: str, columns: list[str], file: str) -> pd.DataFrame:
    if sheet not in sheets:
        raise CalculationError([f"{file}: нет листа «{sheet}»"])
    frame = sheets[sheet]
    frame.columns = [str(column).strip() for column in frame.columns]
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise CalculationError(
            [f"{file}, лист «{sheet}»: нет столбцов " + ", ".join(f"«{c}»" for c in missing)]
        )
    return frame.dropna(how="all")


def _excel_row(index: Any) -> int:
    return int(index) + EXCEL_HEADER_ROW + 1


def _parse_products(frame: pd.DataFrame, where: str, source: str, problems: list[str]) -> dict[str, Product]:
    products: dict[str, Product] = {}
    for index, row in frame.iterrows():
        line = f"{where}, строка {_excel_row(index)}"
        if is_blank(row["Наименование"]):
            problems.append(f"{line}: пустое наименование")
            continue
        try:
            pack_size = to_decimal(row["Фасовка"])
            pack_price = to_decimal(row["Цена за упаковку"])
        except ValueError as exc:
            problems.append(f"{line}: {exc}")
            continue
        if pack_size <= 0:
            problems.append(f"{line}: фасовка должна быть больше нуля")
            continue
        key = normalize_key(row["Наименование"])
        if key in products:
            problems.append(f"{line}: «{row['Наименование']}» встречается дважды")
            continue
        products[key] = Product(
            key=key,
            name=str(row["Наименование"]).strip(),
            section=normalize_key(row["Раздел"]),
            unit=str(row["Ед. изм."]).strip(),
            pack_size=pack_size,
            pack_price=pack_price,
            supplier="" if is_blank(row["Поставщик"]) else str(row["Поставщик"]).strip(),
            waste_allowed=to_bool(row.get(WASTE_FLAG_COLUMN)),
            source=source,
        )
    return products


def read_catalog(path: Path) -> tuple[dict[str, Section], dict[str, Product]]:
    sheets = _read_sheets(path)
    sections_frame = _require(sheets, "Разделы", ["Раздел", "Название в закупке", "Порядок"], path.name)
    products_frame = _require(sheets, "Продукты", PRODUCT_COLUMNS, path.name)

    problems: list[str] = []
    sections: dict[str, Section] = {}
    for index, row in sections_frame.iterrows():
        try:
            order = int(to_decimal(row["Порядок"]))
        except ValueError as exc:
            problems.append(f"{path.name}, лист «Разделы», строка {_excel_row(index)}: {exc}")
            continue
        key = normalize_key(row["Раздел"])
        sections[key] = Section(key=key, title=str(row["Название в закупке"]).strip(), order=order)

    products = _parse_products(products_frame, f"{path.name}, лист «Продукты»", "номенклатура", problems)
    for product in products.values():
        if product.section not in sections:
            problems.append(
                f"{path.name}: у «{product.name}» раздел «{product.section}» не описан в листе «Разделы»"
            )
    if problems:
        raise CalculationError(problems)
    return sections, products


def read_menu(path: Path) -> Menu:
    sheets = _read_sheets(path)
    menu_frame = _require(sheets, "Меню", ["Блюдо", "Порций"], path.name)
    cards_frame = _require(sheets, "Техкарты", ["Техкарта", "Тип", "Ингредиент", "Количество"], path.name)
    problems: list[str] = []

    items = []
    for index, row in menu_frame.iterrows():
        line = f"{path.name}, лист «Меню», строка {_excel_row(index)}"
        try:
            portions = int(to_decimal(row["Порций"]))
        except ValueError as exc:
            problems.append(f"{line}: {exc}")
            continue
        items.append(
            MenuItem(dish=str(row["Блюдо"]).strip(), key=normalize_key(row["Блюдо"]), portions=portions)
        )

    # Название техкарты и тип можно писать только в первой строке блока — как в обычной таблице Excel.
    cards_frame[["Техкарта", "Тип"]] = cards_frame[["Техкарта", "Тип"]].ffill()
    techcards: dict[str, TechCard] = {}
    for card_name, block in cards_frame.groupby("Техкарта", sort=False):
        kind_value = normalize_key(block["Тип"].iloc[0])
        if kind_value not in {kind.value for kind in CardKind}:
            problems.append(
                f"{path.name}: у техкарты «{card_name}» тип «{kind_value}» — ожидается блюдо или полуфабрикат"
            )
            continue
        ingredients = []
        for index, row in block.iterrows():
            line = f"{path.name}, лист «Техкарты», строка {_excel_row(index)}"
            if is_blank(row["Ингредиент"]):
                problems.append(f"{line}: пустой ингредиент")
                continue
            try:
                quantity = to_decimal(row["Количество"])
                waste = None if is_blank(row.get("Коэф. отхода")) else to_decimal(row["Коэф. отхода"])
            except ValueError as exc:
                problems.append(f"{line}: {exc}")
                continue
            ingredients.append(
                Ingredient(
                    name=str(row["Ингредиент"]).strip(),
                    key=normalize_key(row["Ингредиент"]),
                    quantity=quantity,
                    waste_factor=waste,
                    row=_excel_row(index),
                )
            )
        key = normalize_key(card_name)
        if key in techcards:
            problems.append(f"{path.name}: техкарта «{card_name}» описана дважды")
            continue
        techcards[key] = TechCard(
            name=str(card_name).strip(), key=key, kind=CardKind(kind_value), ingredients=tuple(ingredients)
        )

    local_products: dict[str, Product] = {}
    if "Своя номенклатура" in sheets:
        local_frame = _require(sheets, "Своя номенклатура", PRODUCT_COLUMNS, path.name)
        local_products = _parse_products(
            local_frame, f"{path.name}, лист «Своя номенклатура»", "своя номенклатура", problems
        )

    margin: Decimal | None = None
    if "Параметры" in sheets:
        params = _require(sheets, "Параметры", ["Параметр", "Значение"], path.name)
        for _, row in params.iterrows():
            if normalize_key(row["Параметр"]) == normalize_key("Запас, %"):
                try:
                    margin = to_decimal(str(row["Значение"]).replace("%", ""))
                except ValueError as exc:
                    problems.append(f"{path.name}, лист «Параметры»: запас — {exc}")

    if problems:
        raise CalculationError(problems)
    return Menu(items=tuple(items), techcards=techcards, local_products=local_products, margin_percent=margin)
