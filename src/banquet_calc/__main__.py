"""`python -m banquet_calc` без аргументов открывает окно, с аргументами — работает как командная строка."""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) > 1:
        from banquet_calc.cli import main as cli_main

        return cli_main()
    from banquet_calc.gui import launch

    launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
