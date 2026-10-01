"""Модель данных. Количества и деньги — в Decimal: сотые доли килограмма и рубля не должны теряться."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class CardKind(StrEnum):
    DISH = "блюдо"
    SEMI_FINISHED = "полуфабрикат"


@dataclass(frozen=True)
class Section:
    """Раздел закупочного листа: «Овощи и зелень», «Мясо и птица»…"""

    key: str
    title: str
    order: int


@dataclass(frozen=True)
class Product:
    key: str  # нормализованное наименование — по нему ингредиенты техкарт ищутся в номенклатуре
    name: str
    section: str
    unit: str  # кг, л, шт
    pack_size: Decimal  # фасовка в единицах unit
    pack_price: Decimal  # цена за упаковку, ₽
    supplier: str
    waste_allowed: bool  # можно ли указывать коэффициент отхода (брутто/нетто)
    source: str = "номенклатура"


@dataclass(frozen=True)
class Ingredient:
    name: str  # как написано в техкарте
    key: str
    quantity: Decimal  # нетто на единицу выхода техкарты: на порцию блюда или на 1 кг полуфабриката
    waste_factor: Decimal | None  # брутто = нетто × коэффициент
    row: int  # строка в Excel — для понятных сообщений об ошибках


@dataclass(frozen=True)
class TechCard:
    name: str
    key: str
    kind: CardKind
    ingredients: tuple[Ingredient, ...]


@dataclass(frozen=True)
class MenuItem:
    dish: str
    key: str
    portions: int


@dataclass(frozen=True)
class Menu:
    items: tuple[MenuItem, ...]
    techcards: dict[str, TechCard]
    local_products: dict[str, Product]
    margin_percent: Decimal | None  # «Запас, %» из листа «Параметры», если задан
