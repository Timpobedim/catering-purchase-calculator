from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from banquet_calc.settings import Settings, load_settings, save_settings


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"

    save_settings(Settings(menu_path="меню.xlsx", margin_percent=7.5), path)

    assert load_settings(path) == Settings(menu_path="меню.xlsx", margin_percent=7.5)


@pytest.mark.parametrize("content", ["{битый json", '{"menu_path": "a", "unknown": 1}', '["список"]'])
def test_broken_settings_fall_back_to_defaults(tmp_path: Path, content: str) -> None:
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")

    settings = load_settings(path)

    assert settings.margin_percent == 5.0


def test_gui_runs_calculation_and_shows_result(demo_files: tuple[Path, Path], tmp_path: Path) -> None:
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("нет графической среды")
    root.withdraw()
    from banquet_calc.gui import App

    try:
        app = App(root, Settings(), settings_file=tmp_path / "settings.json")
        menu, catalog = demo_files

        app.work(menu, catalog, tmp_path / "out", Decimal(5))  # фоновая часть, но синхронно
        root.update()

        assert app.status_var.get().startswith("Готово")
        assert app.last_output is not None
        assert app.last_output.exists()
        assert str(app.open_button["state"]) == "normal"
    finally:
        root.destroy()
