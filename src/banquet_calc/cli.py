"""Командная строка: тот же расчёт без окна — для планировщика задач и проверки в CI."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from banquet_calc.calculation import CalculationError
from banquet_calc.report import money
from banquet_calc.service import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="banquet-calc", description="Закупочный лист для банкета по техкартам"
    )
    parser.add_argument("--menu", type=Path, required=True, help="файл меню с техкартами (.xlsx)")
    parser.add_argument("--catalog", type=Path, required=True, help="номенклатура продуктов (.xlsx)")
    parser.add_argument("--out", type=Path, default=Path("output"), help="папка для результата")
    parser.add_argument(
        "--margin", type=Decimal, help="запас в процентах (по умолчанию — из файла меню или 5)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outcome = run(args.menu, args.catalog, args.out, args.margin)
    except CalculationError as exc:
        print("Расчёт остановлен — исправьте исходные файлы:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  • {problem}", file=sys.stderr)
        return 2
    result = outcome.result
    print(f"Готово: {outcome.output}")
    print(f"Позиций: {len(result.lines)}, сумма закупки: {money(result.total_cost)} ₽")
    for warning in result.warnings:
        print(f"  ! {warning}")
    return 0
