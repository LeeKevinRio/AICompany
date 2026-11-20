"""Synthetic worlds for the tests of ``scripts/forecast_status.py`` (ADR-0030 supplement 11).

Everything is a ``tmp_path`` file: a synthetic "main" ledger (built by the real recorder over
synthetic bars, as ``tests/test_forecast_report.py`` does), a fake home and a fake clock. Nothing
here opens the real ``<backend>/data/``, reads ``.env`` or touches the network.

The script is loaded once inside the test process without keeping its hooks
(:func:`load_script`), the way ``tests/pipeline_real_loader.py`` loads its precedent.
"""

from __future__ import annotations

import importlib.util
import logging
import shutil
import sys
import threading
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.test_forecast_report import NOW, _publish

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "forecast_status.py"
MODULE_NAME = "forecast_status"
RUN_STAMP = datetime(2026, 11, 20, 10, 30, 5)
STAMP_FOLDER = "20261120-103005"
_cache: list[ModuleType] = []


def load_script() -> ModuleType:
    """The script as a module; the process's hooks and warnings filters are as they were."""
    if _cache:
        return _cache[0]
    saved = (sys.excepthook, threading.excepthook, sys.unraisablehook)
    logging_disabled = logging.root.manager.disable
    spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        with warnings.catch_warnings():  # restores the filters on exit
            spec.loader.exec_module(module)
    finally:
        sys.excepthook, threading.excepthook, sys.unraisablehook = saved
        logging.disable(logging_disabled)
    _cache.append(module)
    return module


fs: Any = load_script()


@dataclass
class World:
    """A synthetic main ledger, a fake home and a recorder of what the script asked ``report``."""

    root: Path
    db: Path
    home: Path
    calls: list[list[str]] = field(default_factory=list)
    opened: list[Path] = field(default_factory=list)

    @property
    def status_root(self) -> Path:
        return Path(self.home / fs.WORK_ROOT_NAME)

    @property
    def folder(self) -> Path:
        return Path(self.status_root / STAMP_FOLDER)

    @property
    def status_file(self) -> Path:
        return Path(self.folder / fs.STATUS_NAME)

    def residue(self) -> list[Path]:
        """Everything under the fake home (nothing, when no file was to be made)."""
        return sorted(self.home.rglob("*")) if self.home.exists() else []

    def seams(self, **override: Any) -> dict[str, Any]:
        seams: dict[str, Any] = {
            "env": {},
            "home": self.home,
            "now": lambda: RUN_STAMP,
            "clock": lambda: NOW,
            "opener": self.opened.append,
        }
        seams.update(override)
        return seams


def make_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ledger_file: Path) -> World:
    """A world whose "main database" is a copy of ``ledger_file`` (derivation monkeypatched)."""
    root = tmp_path / "world"
    (root / "backend" / "data").mkdir(parents=True)
    db = root / "backend" / "data" / "stock-desk.db"
    shutil.copy2(ledger_file, db)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(fs, "main_db_path", lambda: db)
    _publish(monkeypatch)
    return World(root=root, db=db, home=home)


def run(world: World, capsys: pytest.CaptureFixture[str], **override: Any) -> tuple[int, str, str]:
    """One run of the script's ``main``: (exit code, stdout text, stderr text)."""
    capsys.readouterr()
    code = fs.main(**world.seams(**override))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def reference(world: World, capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    """``report.main`` itself on the same database and the same clock: (code, stdout text)."""
    from app.forecast import report

    capsys.readouterr()
    code = report.main([*argv, "--db", str(world.db)], clock=lambda: NOW)
    return code, capsys.readouterr().out


def recording(
    world: World,
    *,
    status: Callable[..., int] | None = None,
    verify: Callable[..., int] | None = None,
) -> Callable[..., int]:
    """A ``report_main`` seam: notes each call's argv, then runs the real one or the stand-in."""
    from app.forecast import report

    def seam(argv: Sequence[str], *, clock: Callable[[], datetime] | None = None) -> int:
        world.calls.append(list(argv))
        chosen = {"status": status, "verify": verify}[argv[0]]
        if chosen is not None:
            return chosen(argv, clock=clock)
        return int(report.main(argv, clock=clock))

    return seam
