"""Synthetic worlds for the tests of ``scripts/pipeline_acceptance_real.py``.

Everything is a ``tmp_path`` file: a fake "main" database (written by ``PriceBarCache`` from
``synthetic_series``), a fake backend folder, a fake home and a fake git. Nothing here opens the
real ``<backend>/data/``, reads ``.env`` or touches the network.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.data.cache import PriceBarCache
from app.data.interface import PriceBar
from tests.forecast_pipeline_harness import synthetic_return, synthetic_series
from tests.outlook_helpers import TAIPEI
from tests.pipeline_real_loader import load_script

real: Any = load_script()

LAST = date(2026, 11, 13)
DEPTH = 340  # at least the required depth (336)
NOW = datetime(2026, 11, 16, 10, 0, 0)
RUN_CLOCK = datetime(2026, 11, 16, 9, tzinfo=TAIPEI)
WORK_NAME = "20261116-100000"
LOCK_BYTES = b"# a synthetic lock file\nname = 'x'\n"
HEAD = "a" * 40


def flipped_return(j: int) -> float:
    """A second, different label distribution: the first one with every return negated."""
    return -synthetic_return(j)


def yfinance_bars(
    count: int = DEPTH, *, returns: Callable[[int], float] = synthetic_return
) -> list[PriceBar]:
    """Synthetic ^TWII bars as the cache holds them (source ``yfinance``)."""
    return [
        bar.model_copy(update={"source": "yfinance"})
        for bar in synthetic_series(LAST, count, returns=returns)
    ]


class FakeGit:
    """A canned ``git``: the answers of a clean, published checkout (or a chosen failure)."""

    def __init__(
        self,
        backend: Path,
        *,
        dirty: bool = False,
        published: bool = True,
        crlf: bool = False,
        unusable: bool = False,
        autocrlf: bytes | None = None,
    ) -> None:
        self.blob = (backend / "uv.lock").read_bytes()
        self.dirty, self.published, self.crlf = dirty, published, crlf
        self.unusable, self.autocrlf = unusable, autocrlf
        self.calls: list[list[str]] = []

    def __call__(self, cwd: Path, args: Sequence[str]) -> tuple[int, bytes]:
        words = list(args)
        self.calls.append(words)
        if self.unusable:
            return 128, b""
        if words[:2] == ["rev-parse", "--show-toplevel"]:
            return 0, b"/somewhere\n"
        if words[0] == "status":
            return 0, b" M app/x.py\n" if self.dirty else b""
        if words == ["rev-parse", "HEAD"]:
            return 0, HEAD.encode() + b"\n"
        if words[0] == "merge-base":
            return (0 if self.published else 1), b""
        if words[0] == "cat-file":
            return 0, self.blob
        if words[0] == "ls-files":
            state = b"w/crlf" if self.crlf else b"w/lf"
            return 0, b"i/lf    " + state + b"   attr/text eol=lf\tuv.lock\n"
        if words[:2] == ["config", "--get"]:
            return (0, self.autocrlf) if self.autocrlf is not None else (1, b"")
        return 1, b""


@dataclass
class World:
    """A fake installation: backend folder, main database, home folder and the fake git."""

    root: Path
    backend: Path
    home: Path
    db: Path
    git: FakeGit
    opened: list[Path] = field(default_factory=list)
    holders: list[sqlite3.Connection] = field(default_factory=list)

    @property
    def work(self) -> Path:
        return Path(self.home / str(real.WORK_ROOT_NAME) / WORK_NAME)

    @property
    def main_files(self) -> list[Path]:
        return [self.db.with_name(self.db.name + s) for s in ("", "-wal", "-shm")]

    def close(self) -> None:
        for holder in self.holders:
            holder.close()
        self.holders.clear()

    def run(self, capsys: Any, **seams: Any) -> tuple[int, list[str], str]:
        """``main`` with every seam defaulted to the synthetic world; returns code, out, err."""
        arguments: dict[str, Any] = {
            "env": {},
            "cwd": self.root,
            "port_check": lambda: False,
            "git": self.git,
            "wait": lambda _prompt: None,
            "opener": self.opened.append,
            "now": lambda: NOW,
            "wall_clock": lambda: RUN_CLOCK,
            "pause": lambda _seconds: None,
        }
        arguments.update(seams)
        code = real.main(
            ["--backend-dir", str(self.backend), "--home", str(self.home)], **arguments
        )
        captured = capsys.readouterr()
        return code, captured.out.splitlines(), captured.err


def make_world(
    root: Path,
    *,
    bars: list[PriceBar] | None = None,
    wal_tail: int = 0,
    last_source: str = "yfinance",
) -> World:
    """A fake main database with ``bars``; the last ``wal_tail`` bars stay in the ``-wal``.

    With ``wal_tail`` the database is kept open by a holder connection so the close of the
    writer does not checkpoint: the main database really has a ``-wal`` and a ``-shm``.
    """
    backend = root / "stock-desk" / "backend"
    (backend / "data").mkdir(parents=True)
    (backend / "uv.lock").write_bytes(LOCK_BYTES)
    home = root / "home"
    home.mkdir()
    db = backend / "data" / "stock-desk.db"
    series = bars if bars is not None else yfinance_bars()
    stamp = datetime(2026, 11, 14, 1, tzinfo=TAIPEI)
    world = World(root, backend, home, db, FakeGit(backend))
    head, tail = (series[:-wal_tail], series[-wal_tail:]) if wal_tail else (series, [])
    sources = {"yfinance": head}
    if last_source != "yfinance":
        sources = {"yfinance": head[:-1], last_source: head[-1:]}
    for source, part in sources.items():
        if part:
            PriceBarCache(db).put(part, source=source, fetched_at=stamp)
    if wal_tail:
        holder = sqlite3.connect(db)
        holder.execute("SELECT 1 FROM price_bars_cache").fetchall()
        world.holders.append(holder)
        PriceBarCache(db).put(tail, source="yfinance", fetched_at=stamp)
        assert db.with_name(db.name + "-wal").stat().st_size > 0
    return world


def later(day: date, days: int) -> date:
    return day + timedelta(days=days)
