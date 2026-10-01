"""Расчёт закупки: раскрытие техкарт с полуфабрикатами, проверки, запас, округление до фасовки."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from banquet_calc.models import Menu, Product, Section, TechCard

UNKNOWN_SECTION = Section(key="__unknown__", title="Нет в номенклатуре — проверьте названия", order=10**6)


class CalculationError(Exception):
    """Ошибка в исходных данных, которую пользователь должен исправить в Excel."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class PurchaseLine:
    section: Section
    name: str
    unit: str
    required: Decimal  # нужно с учётом запаса
    product: Product | None  # None — ингредиента нет ни в номенклатуре, ни среди техкарт
    packs: int | None
    purchase_quantity: Decimal | None
    cost: Decimal | None


@dataclass(frozen=True)
class BreakdownRow:
    dish: str
    portions: int
    ingredient: str
    unit: str
    quantity: Decimal  # брутто на все порции, без запаса


@dataclass(frozen=True)
class CalculationResult:
    lines: list[PurchaseLine]
    breakdown: list[BreakdownRow]
    warnings: list[str]
    margin_percent: Decimal

    @property
    def total_cost(self) -> Decimal:
        return sum((line.cost for line in self.lines if line.cost is not None), Decimal(0))


def merge_catalogs(
    products: dict[str, Product], local: dict[str, Product]
) -> tuple[dict[str, Product], list[str]]:
    """Своя номенклатура из файла меню дополняет общую и может заменить позицию — с предупреждением."""
    merged = dict(products)
    warnings = []
    for key, product in local.items():
        if key in merged:
            warnings.append(
                f"«{product.name}»: позиция из листа «Своя номенклатура» заменяет общую номенклатуру"
            )
        merged[key] = product
    return merged, warnings


def find_cycle(techcards: dict[str, TechCard]) -> list[str] | None:
    """Путь цикла полуфабрикатов («Соус А → Соус Б → Соус А») или None."""
    state: dict[str, int] = {}  # 1 — в обработке, 2 — готово
    stack: list[str] = []

    def visit(key: str) -> list[str] | None:
        state[key] = 1
        stack.append(key)
        for ingredient in techcards[key].ingredients:
            if ingredient.key not in techcards:
                continue
            if state.get(ingredient.key) == 1:
                start = stack.index(ingredient.key)
                return [techcards[k].name for k in [*stack[start:], ingredient.key]]
            if ingredient.key not in state and (cycle := visit(ingredient.key)):
                return cycle
        stack.pop()
        state[key] = 2
        return None

    for key in techcards:
        if key not in state and (cycle := visit(key)):
            return cycle
    return None


def validate(menu: Menu, products: dict[str, Product]) -> tuple[list[str], list[str]]:
    """Возвращает (ошибки, предупреждения). Ошибки останавливают расчёт, предупреждения — нет."""
    errors: list[str] = []
    warnings: list[str] = []
    for item in menu.items:
        if item.key not in menu.techcards:
            errors.append(f"Меню: блюда «{item.dish}» нет среди техкарт")
        if item.portions <= 0:
            errors.append(f"Меню: у блюда «{item.dish}» число порций должно быть больше нуля")

    for card in menu.techcards.values():
        if not card.ingredients:
            errors.append(f"Техкарта «{card.name}»: нет ни одного ингредиента")
        for ingredient in card.ingredients:
            where = f"Техкарта «{card.name}», строка {ingredient.row}"
            if ingredient.quantity <= 0:
                errors.append(f"{where}: количество «{ingredient.name}» должно быть больше нуля")
            factor = ingredient.waste_factor
            if factor is None:
                if ingredient.key not in products and ingredient.key not in menu.techcards:
                    warnings.append(f"{where}: «{ingredient.name}» нет в номенклатуре — позиция без цены")
                continue
            if ingredient.key in menu.techcards:
                errors.append(f"{where}: коэффициент отхода указывается для продуктов, а не полуфабрикатов")
            elif factor < 1:
                errors.append(f"{where}: коэффициент отхода «{ingredient.name}» не может быть меньше 1")
            elif ingredient.key in products and not products[ingredient.key].waste_allowed:
                errors.append(
                    f"{where}: для «{ingredient.name}» коэффициент отхода не предусмотрен номенклатурой"
                )

    if cycle := find_cycle(menu.techcards):
        errors.append("Полуфабрикаты ссылаются друг на друга по кругу: " + " → ".join(cycle))
    return errors, warnings


def expand(
    card_key: str, multiplier: Decimal, techcards: dict[str, TechCard]
) -> Iterator[tuple[str, str, Decimal]]:
    """Раскрывает техкарту до продуктов: (ключ, название, брутто на multiplier единиц выхода)."""
    for ingredient in techcards[card_key].ingredients:
        quantity = multiplier * ingredient.quantity * (ingredient.waste_factor or Decimal(1))
        if ingredient.key in techcards:
            yield from expand(ingredient.key, quantity, techcards)
        else:
            yield ingredient.key, ingredient.name, quantity


def packs_needed(required: Decimal, pack_size: Decimal) -> int:
    return int((required / pack_size).to_integral_value(rounding=ROUND_CEILING))


def calculate(
    menu: Menu, products: dict[str, Product], sections: dict[str, Section], margin_percent: Decimal
) -> CalculationResult:
    errors, warnings = validate(menu, products)
    if errors:
        raise CalculationError(errors)

    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    names: dict[str, str] = {}
    breakdown: list[BreakdownRow] = []
    for item in menu.items:
        per_dish: defaultdict[str, Decimal] = defaultdict(Decimal)
        for key, name, quantity in expand(item.key, Decimal(item.portions), menu.techcards):
            per_dish[key] += quantity
            totals[key] += quantity
            names.setdefault(key, products[key].name if key in products else name)
        for key, quantity in per_dish.items():
            unit = products[key].unit if key in products else "?"
            breakdown.append(BreakdownRow(item.dish, item.portions, names[key], unit, quantity))

    factor = 1 + margin_percent / 100
    lines = []
    for key, total in totals.items():
        required = total * factor
        product = products.get(key)
        if product is None:
            lines.append(PurchaseLine(UNKNOWN_SECTION, names[key], "?", required, None, None, None, None))
            continue
        section = sections.get(product.section) or Section(
            product.section, product.section.capitalize(), 10**5
        )
        packs = packs_needed(required, product.pack_size)
        lines.append(
            PurchaseLine(
                section=section,
                name=product.name,
                unit=product.unit,
                required=required,
                product=product,
                packs=packs,
                purchase_quantity=packs * product.pack_size,
                cost=packs * product.pack_price,
            )
        )
    lines.sort(key=lambda line: (line.section.order, line.section.title, line.name.casefold()))
    return CalculationResult(
        lines=lines, breakdown=breakdown, warnings=warnings, margin_percent=margin_percent
    )
