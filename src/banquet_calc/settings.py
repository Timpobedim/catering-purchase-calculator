"""Настройки GUI в JSON в папке пользователя: последние файлы, папка результата, запас."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Settings:
    menu_path: str = ""
    catalog_path: str = ""
    output_dir: str = ""
    margin_percent: float = 5.0


def settings_path() -> Path:
    base = Path(os.environ["APPDATA"]) if os.environ.get("APPDATA") else Path.home() / ".config"
    return base / "banquet-calc" / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    """Повреждённый или устаревший файл не мешает запуску — берутся значения по умолчанию."""
    target = path or settings_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    try:
        return Settings(**{key: value for key, value in data.items() if key in Settings.__dataclass_fields__})
    except TypeError:
        return Settings()


def save_settings(settings: Settings, path: Path | None = None) -> None:
    target = path or settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
