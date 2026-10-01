from __future__ import annotations

from decimal import Decimal

import pytest
from conftest import SECTIONS, card, catalog, menu, product

from banquet_calc.calculation import CalculationError, calculate, find_cycle, merge_catalogs
from banquet_calc.models import CardKind

SEMI = CardKind.SEMI_FINISHED


def lines_by_name(result):  # type: ignore[no-untyped-def]
    return {line.name: line for line in result.lines}


def test_semi_finished_products_are_expanded_through_all_levels() -> None:
    products = catalog(
        product("Сыр пармезан", "молочные", pack="0.2", price="480"),
        product("Майонез", "молочные", pack="0.8", price="280"),
        product("Салат романо", pack="0.5", price="240"),
    )
    salad = card("Салат", ("Салат романо", "0.06"), ("Соус", "0.05"))
    sauce = card("Соус", ("Майонез", "0.8"), ("Основа", "0.2"), kind=SEMI)
    base = card("Основа", ("Сыр пармезан", "1"), kind=SEMI)

    result = calculate(menu({"Салат": 40}, salad, sauce, base), products, SECTIONS, Decimal(0))

    lines = lines_by_name(result)
    # 40 порций × 0,05 кг соуса × 0,2 кг основы на кг соуса × 1 кг сыра на кг основы
    assert lines["Сыр пармезан"].required == Decimal("0.4")
    assert lines["Сыр пармезан"].packs == 2
    assert lines["Сыр пармезан"].cost == Decimal(960)
    assert lines["Майонез"].required == Decimal("1.6")
    assert lines["Салат романо"].required == Decimal("2.4")


def test_waste_factor_turns_net_into_gross() -> None:
    products = catalog(product("Картофель", pack="5", price="250", waste=True))
    dish = card("Картофель по-деревенски", ("Картофель", "0.2", "1.33"))

    result = calculate(menu({"Картофель по-деревенски": 10}, dish), products, SECTIONS, Decimal(0))

    assert lines_by_name(result)["Картофель"].required == Decimal("2.66")


def test_margin_is_applied_before_rounding_to_packs() -> None:
    products = catalog(product("Картофель", pack="5", price="250"))
    dish = card("Пюре", ("Картофель", "0.49"))

    without_margin = calculate(menu({"Пюре": 10}, dish), products, SECTIONS, Decimal(0))
    with_margin = calculate(menu({"Пюре": 10}, dish), products, SECTIONS, Decimal(5))

    assert lines_by_name(without_margin)["Картофель"].packs == 1  # 4,9 кг
    line = lines_by_name(with_margin)["Картофель"]
    assert line.required == Decimal("5.145")
    assert line.packs == 2
    assert line.purchase_quantity == Decimal(10)


@pytest.mark.parametrize(
    ("spec", "cards", "message"),
    [
        pytest.param(
            ("Сыр пармезан", "0.1", "1.1"), (), "не предусмотрен номенклатурой", id="waste-not-allowed"
        ),
        pytest.param(("Картофель", "0.1", "0.9"), (), "не может быть меньше 1", id="waste-below-one"),
        pytest.param(("Соус", "0.1", "1.2"), ("Соус",), "а не полуфабрикатов", id="waste-on-semi-finished"),
        pytest.param(("Картофель", "0"), (), "больше нуля", id="zero-quantity"),
    ],
)
def test_invalid_ingredient_stops_calculation(
    spec: tuple[str, ...], cards: tuple[str, ...], message: str
) -> None:
    products = catalog(product("Сыр пармезан", "молочные"), product("Картофель", waste=True))
    extra = [card(name, ("Сыр пармезан", "1"), kind=SEMI) for name in cards]
    dish = card("Блюдо", spec)  # type: ignore[arg-type]

    with pytest.raises(CalculationError) as error:
        calculate(menu({"Блюдо": 1}, dish, *extra), products, SECTIONS, Decimal(0))

    assert message in str(error.value)
    assert "Техкарта «Блюдо», строка 2" in str(error.value)


def test_cycle_of_semi_finished_products_is_reported_with_path() -> None:
    first = card("Соус А", ("Соус Б", "0.5"), kind=SEMI)
    second = card("Соус Б", ("Соус А", "0.5"), kind=SEMI)

    assert find_cycle({item.key: item for item in (first, second)}) == ["Соус А", "Соус Б", "Соус А"]
    with pytest.raises(CalculationError, match="Соус А → Соус Б → Соус А"):
        calculate(menu({"Соус А": 1}, first, second), {}, SECTIONS, Decimal(0))


def test_all_problems_are_reported_at_once() -> None:
    dish = card("Блюдо", ("Картофель", "0", "0.5"))

    with pytest.raises(CalculationError) as error:
        calculate(
            menu({"Блюдо": 1, "Нет такого": 1}, dish),
            catalog(product("Картофель", waste=True)),
            SECTIONS,
            Decimal(0),
        )

    assert len(error.value.problems) == 3


def test_unknown_ingredient_is_kept_in_separate_section_with_warning() -> None:
    dish = card("Канапе", ("Картофель", "0.1"), ("Икра красная", "0.01"))

    result = calculate(menu({"Канапе": 10}, dish), catalog(product("Картофель")), SECTIONS, Decimal(0))

    unknown = result.lines[-1]
    assert unknown.name == "Икра красная"
    assert unknown.section.title.startswith("Нет в номенклатуре")
    assert (unknown.packs, unknown.cost) == (None, None)
    assert any("Икра красная" in warning for warning in result.warnings)


def test_lines_are_sorted_by_section_order_then_name() -> None:
    products = catalog(
        product("Сливки", "молочные"), product("Морковь"), product("Картофель"), product("Кефир", "молочные")
    )
    dish = card("Всё", *[(name, "0.1") for name in ("Сливки", "Морковь", "Картофель", "Кефир")])

    result = calculate(menu({"Всё": 1}, dish), products, SECTIONS, Decimal(0))

    assert [line.name for line in result.lines] == ["Картофель", "Морковь", "Кефир", "Сливки"]


def test_total_cost_and_breakdown_per_dish() -> None:
    products = catalog(product("Картофель", pack="5", price="250"), product("Морковь", pack="2", price="110"))
    first = card("Пюре", ("Картофель", "0.2"))
    second = card("Рагу", ("Картофель", "0.1"), ("Морковь", "0.1"))

    result = calculate(menu({"Пюре": 10, "Рагу": 10}, first, second), products, SECTIONS, Decimal(0))

    assert result.total_cost == Decimal(250 + 110)
    assert [(row.dish, row.ingredient, row.quantity) for row in result.breakdown] == [
        ("Пюре", "Картофель", Decimal("2.0")),
        ("Рагу", "Картофель", Decimal("1.0")),
        ("Рагу", "Морковь", Decimal("1.0")),
    ]


def test_local_catalog_extends_and_overrides_with_warning() -> None:
    main = catalog(product("Картофель", price="250"))
    local = catalog(product("Картофель", price="300"), product("Сырная тарелка", price="1800"))

    merged, warnings = merge_catalogs(main, local)

    assert merged["картофель"].pack_price == Decimal(300)
    assert "сырная тарелка" in merged
    assert len(warnings) == 1
