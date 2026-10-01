"""Окно на tkinter для технолога: выбрать файлы, указать запас, нажать «Рассчитать».

Расчёт идёт в фоновом потоке, а результат возвращается в окно через root.after — интерфейс
не «замерзает», пока читаются книги Excel.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from banquet_calc.calculation import CalculationError
from banquet_calc.report import money
from banquet_calc.service import RunResult, run
from banquet_calc.settings import Settings, load_settings, save_settings

TITLE = "Закупка для банкета"


class App:
    def __init__(self, root: tk.Tk, settings: Settings, settings_file: Path | None = None) -> None:
        self.root = root
        self.settings = settings
        self.settings_file = settings_file
        root.title(TITLE)
        root.minsize(640, 420)

        self.menu_var = tk.StringVar(value=settings.menu_path)
        self.catalog_var = tk.StringVar(value=settings.catalog_path)
        self.output_var = tk.StringVar(value=settings.output_dir)
        self.margin_var = tk.StringVar(value=f"{settings.margin_percent:g}")
        self.status_var = tk.StringVar(value="Выберите файл меню и номенклатуру")
        self.last_output: Path | None = None

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        self._file_row(frame, 0, "Меню с техкартами:", self.menu_var, self._choose_menu)
        self._file_row(frame, 1, "Номенклатура:", self.catalog_var, self._choose_catalog)
        self._file_row(frame, 2, "Папка результата:", self.output_var, self._choose_output)
        ttk.Label(frame, text="Запас, %:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Spinbox(frame, from_=0, to=50, increment=1, textvariable=self.margin_var, width=6).grid(
            row=3, column=1, sticky="w"
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=3, sticky="w", pady=8)
        self.run_button = ttk.Button(buttons, text="Рассчитать", command=self.start)
        self.run_button.pack(side="left")
        self.open_button = ttk.Button(
            buttons, text="Открыть папку", command=self._open_output, state="disabled"
        )
        self.open_button.pack(side="left", padx=6)
        ttk.Button(buttons, text="Сбросить настройки", command=self._reset).pack(side="left")

        ttk.Label(frame, textvariable=self.status_var).grid(row=5, column=0, columnspan=3, sticky="w")
        self.log = tk.Text(frame, height=10, wrap="word", state="disabled")
        self.log.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(6, 0))
        frame.rowconfigure(6, weight=1)

    def _file_row(
        self, frame: ttk.Frame, row: int, label: str, variable: tk.StringVar, command: Callable[[], None]
    ) -> None:
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Выбрать…", command=command).grid(row=row, column=2)

    def _choose_menu(self) -> None:
        if path := filedialog.askopenfilename(title="Файл меню", filetypes=[("Excel", "*.xlsx")]):
            self.menu_var.set(path)
            if not self.output_var.get():
                self.output_var.set(str(Path(path).parent))

    def _choose_catalog(self) -> None:
        if path := filedialog.askopenfilename(title="Номенклатура", filetypes=[("Excel", "*.xlsx")]):
            self.catalog_var.set(path)

    def _choose_output(self) -> None:
        if path := filedialog.askdirectory(title="Папка для закупочного листа"):
            self.output_var.set(path)

    def _write_log(self, lines: list[str]) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", "\n".join(lines))
        self.log.configure(state="disabled")

    def start(self) -> None:
        try:
            margin = Decimal(self.margin_var.get().replace(",", "."))
        except ArithmeticError:
            messagebox.showerror(TITLE, "Запас должен быть числом, например 5")
            return
        menu, catalog, output = self.menu_var.get(), self.catalog_var.get(), self.output_var.get()
        if not (menu and catalog and output):
            messagebox.showwarning(TITLE, "Укажите файл меню, номенклатуру и папку результата")
            return
        self.settings = Settings(menu, catalog, output, float(margin))
        save_settings(self.settings, self.settings_file)
        self.run_button.configure(state="disabled")
        self.status_var.set("Считаю…")
        threading.Thread(
            target=self.work, args=(Path(menu), Path(catalog), Path(output), margin), daemon=True
        ).start()

    def work(self, menu: Path, catalog: Path, output: Path, margin: Decimal) -> None:
        """Выполняется в фоновом потоке: с виджетами работает только через root.after."""
        try:
            outcome = run(menu, catalog, output, margin)
        except CalculationError as exc:
            problems = exc.problems
            self.root.after(0, self.failed, problems)
        else:
            self.root.after(0, self.finished, outcome)

    def finished(self, outcome: RunResult) -> None:
        self.last_output = outcome.output
        result = outcome.result
        total = money(result.total_cost)
        self.status_var.set(f"Готово: {outcome.output.name} — позиций: {len(result.lines)}, сумма {total} ₽")
        self._write_log(result.warnings or ["Предупреждений нет"])
        self.run_button.configure(state="normal")
        self.open_button.configure(state="normal")

    def failed(self, problems: list[str]) -> None:
        self.status_var.set("Расчёт остановлен — исправьте исходные файлы")
        self._write_log(problems)
        self.run_button.configure(state="normal")

    def _open_output(self) -> None:
        if self.last_output is None:
            return
        folder = self.last_output.parent
        if sys.platform == "win32":
            os.startfile(folder)  # noqa: S606 — открывается папка результата, которую выбрал пользователь
        else:
            subprocess.run(["xdg-open", str(folder)], check=False)  # noqa: S603, S607

    def _reset(self) -> None:
        self.settings = Settings()
        save_settings(self.settings, self.settings_file)
        for variable in (self.menu_var, self.catalog_var, self.output_var):
            variable.set("")
        self.margin_var.set(f"{self.settings.margin_percent:g}")
        self.status_var.set("Настройки сброшены")


def launch() -> None:
    root = tk.Tk()
    App(root, load_settings())
    root.mainloop()
