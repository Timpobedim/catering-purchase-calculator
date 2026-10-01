"""Сценарий целиком — общий для GUI и командной строки."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from banquet_calc.calculation import CalculationResult, calculate, merge_catalogs
from banquet_calc.report import write_report
from banquet_calc.workbook import read_catalog, read_menu

DEFAULT_MARGIN = Decimal(5)


@dataclass(frozen=True)
class RunResult:
    output: Path
    result: CalculationResult


def run(menu_path: Path, catalog_path: Path, output_dir: Path, margin: Decimal | None = None) -> RunResult:
    """margin — запас в процентах; если не задан, берётся из листа «Параметры», иначе 5 %."""
    sections, products = read_catalog(catalog_path)
    menu = read_menu(menu_path)
    merged, merge_warnings = merge_catalogs(products, menu.local_products)
    effective_margin = margin if margin is not None else (menu.margin_percent or DEFAULT_MARGIN)
    result = calculate(menu, merged, sections, effective_margin)
    result.warnings[:0] = merge_warnings
    output = write_report(output_dir / f"Закупка — {menu_path.stem}.xlsx", result, title=menu_path.stem)
    return RunResult(output=output, result=result)
