"""Synthetic worlds for the tests of ``scripts/cg2_register.py``.

Everything is a ``tmp_path`` file: a stand-in git repository laid out like the real one
(``apps/stock-desk/backend`` with a synthetic ``app/`` and two synthetic rule YAMLs, the two
documents under ``work/``), a fake "main" database at ``<backend>/data/stock-desk.db``, a fake home
and a stand-in registration runner that calls ``claims.main`` in this process with the stand-in
backend. Nothing here opens, stats or names the real ``<backend>/data/``, reads a real ``.env`` or
touches the network. The rule sets and the definition are the published CG-2 ones, so the real
hash constants hold here; only the file-level constants (documents, YAMLs, ``app/`` tree) are
synthetic.
"""

from __future__ import annotations

import hashlib
import io
import sqlite3
import subprocess
from collections.abc import Callable, Sequence
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.forecast import claims
from app.forecast import store as store_module
from tests.cg2_register_loader import load_script

real: Any = load_script()

NOW = datetime(2026, 11, 20, 21, 5, 3)
UTC_NOW = datetime(2026, 11, 20, 13, 5, 9, tzinfo=UTC)
STAMP = "20261120-210503"
PREREG_BYTES = b"# pre-registration (synthetic stand-in)\n"
C8_BYTES = b"# C-8 decision record (synthetic stand-in)\n"
H3_BYTES = b"h3: synthetic stand-in\n"
H5_BYTES = b"h5: synthetic stand-in\n"
APP_ROWS = [("theme", "dark"), ("currency", "TWD")]
REVIEW_REFS = ("work/reviews/risk-a.md", "work/reviews/qa-b.md")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


class TickClock:
    """A store clock that moves one second per read."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        self.now = self.now + timedelta(seconds=1)
        return self.now


class StuckClock:
    """A store clock that never moves: the second row can never be later (a store refusal)."""

    def __call__(self) -> datetime:
        return datetime(2026, 11, 20, 13, 0, 0, tzinfo=UTC)


class InProcessClaims:
    """The stand-in runner: ``claims.main`` with the stand-in backend, output captured.

    ``before_run`` runs just before the program (a place to change the world between the
    preflight and the registration); ``calls`` records every argument list it was given.
    """

    def __init__(self, world: World) -> None:
        self.world = world
        self.env: dict[str, str] = {}
        self.clock: Callable[[], datetime] = TickClock(datetime(2026, 11, 20, 13, 0, 0, tzinfo=UTC))
        self.calls: list[list[str]] = []
        self.probes = 0
        self.before_run: Callable[[], None] | None = None
        self.raises: BaseException | None = None
        self.override: Any = None
        self.probe_result: Path | None = world.backend
        self.events: list[str] = world.events

    def probe(self) -> Path | None:
        self.probes += 1
        return self.probe_result

    def run(self, args: Sequence[str]) -> Any:
        self.events.append("run")
        self.calls.append(list(args))
        if self.before_run is not None:
            self.before_run()
        if self.raises is not None:
            raise self.raises
        if self.override is not None:
            return self.override
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = claims.main(
                list(args),
                env=self.env,
                backend_dir=self.world.backend,
                clock=self.clock,  # type: ignore[arg-type]
            )
        return real.CliResult(code, out.getvalue(), err.getvalue())


@dataclass
class World:
    """A stand-in repository, backend, main database and home."""

    root: Path
    backend: Path = field(init=False)
    data: Path = field(init=False)
    db: Path = field(init=False)
    home: Path = field(init=False)
    pins: Any = field(init=False)
    head: str = field(init=False)
    runner: InProcessClaims = field(init=False)
    answers: list[str] = field(default_factory=list)
    asked: list[str] = field(default_factory=list)
    opened: list[Path] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    listening: bool = False
    env: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        root = self.root
        root.mkdir(parents=True, exist_ok=True)
        self.backend = root / "repo" / "apps" / "stock-desk" / "backend"
        self.repo = root / "repo"
        self.data = self.backend / "data"
        self.db = self.data / "stock-desk.db"
        self.home = root / "home"
        self.home.mkdir()
        self.data.mkdir(parents=True)
        for package in ("forecast", "outlook", "dirdef"):
            (self.backend / "app" / package).mkdir(parents=True)
            (self.backend / "app" / package / "__init__.py").write_text("# stand-in\n")
        (self.backend / "app" / "__init__.py").write_text("# stand-in\n")
        (self.backend / "app" / "data").mkdir()
        (self.backend / "app" / "data" / "session_calendar.py").write_text("# stand-in\n")
        rules = self.backend / "app" / "outlook" / "rules"
        rules.mkdir()
        (rules / "h3.yaml").write_bytes(H3_BYTES)
        (rules / "h5.yaml").write_bytes(H5_BYTES)
        (self.backend / ".gitattributes").write_text(
            "uv.lock text eol=lf\n"
            "/app/outlook/rules/h3.yaml text eol=lf\n"
            "/app/outlook/rules/h5.yaml text eol=lf\n"
        )
        prereg = self.repo / real.REAL_PINS.frozen("prereg").path
        c8 = self.repo / real.REAL_PINS.frozen("c8").path
        for path, data in ((prereg, PREREG_BYTES), (c8, C8_BYTES)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            (path.parent / ".gitattributes").write_text(f"/{path.name} text eol=lf\n")
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "stand-in")
        self.head = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "update-ref", "refs/remotes/origin/product/stock-desk", self.head)
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute("CREATE TABLE app_settings (k TEXT PRIMARY KEY, v TEXT)")
            conn.executemany("INSERT INTO app_settings VALUES (?, ?)", APP_ROWS)
            conn.execute("PRAGMA user_version = 7")
            conn.commit()
        self.pins = self.make_pins()
        self.runner = InProcessClaims(self)

    def make_pins(self) -> Any:
        """The real hash constants; the file-level constants of this stand-in repository."""
        real_pins = real.REAL_PINS
        sha = {
            "prereg": PREREG_BYTES,
            "c8": C8_BYTES,
            "h3": H3_BYTES,
            "h5": H5_BYTES,
        }
        files = tuple(
            replace(item, sha256=hashlib.sha256(sha[item.role]).hexdigest())
            for item in real_pins.frozen_files
        )
        tree = git(self.repo, "rev-parse", f"HEAD:{real.APP_REL}")
        return replace(real_pins, frozen_files=files, app_tree_id=tree, review_refs=REVIEW_REFS)

    # --- the seams ---------------------------------------------------------------------------

    def ask(self, prompt: str) -> str:
        self.asked.append(prompt)
        if prompt == real.PROMPT_SEEN:
            self.events.append("ask_seen")
            return self.answers.pop(0) if self.answers else "0"
        return ""

    def opener(self, path: Path) -> None:
        self.opened.append(path)

    def run(self, mode: str, **overrides: Any) -> int:
        seams: dict[str, Any] = {
            "env": self.env,
            "port_check": lambda: self.listening,
            "ask": self.ask,
            "opener": self.opener,
            "now": lambda: NOW,
            "utc_now": lambda: UTC_NOW,
            "claims": self.runner,
            "pins": self.pins,
            "app_check": lambda _backend: True,
        }
        seams.update(overrides)
        argv = [mode, "--backend-dir", str(self.backend), "--home", str(self.home)]
        return int(real.main(argv, **seams))

    # --- what the tests look at -------------------------------------------------------------

    @property
    def work(self) -> Path:
        return self.home / real.WORK_ROOT_NAME

    def backups(self) -> list[Path]:
        folder = self.work / real.BACKUP_DIR_NAME
        return sorted(folder.iterdir()) if folder.is_dir() else []

    def paste_backs(self) -> list[Path]:
        folder = self.work / real.PASTE_DIR_NAME
        return sorted(folder.iterdir()) if folder.is_dir() else []

    def logical_state(self) -> tuple[tuple[str, ...], tuple[object, ...]]:
        """The main database's dump and header pragmas, read through a ``mode=ro`` connection."""
        with closing(sqlite3.connect(f"{self.db.as_uri()}?mode=ro", uri=True)) as conn:
            dump = tuple(conn.iterdump())
            pragmas = tuple(
                conn.execute(f"PRAGMA {name}").fetchone()[0]
                for name in ("user_version", "application_id", "page_size")
            )
        return dump, pragmas

    def objects(self, db: Path | None = None) -> list[tuple[str, str]]:
        with closing(sqlite3.connect(f"{(db or self.db).as_uri()}?mode=ro", uri=True)) as conn:
            return [
                (str(k), str(n))
                for k, n in conn.execute("SELECT type, name FROM sqlite_master ORDER BY 1, 2")
            ]

    def registry(self) -> list[tuple[str, int]]:
        with closing(sqlite3.connect(f"{self.db.as_uri()}?mode=ro", uri=True)) as conn:
            return [
                (str(c), int(v))
                for c, v in conn.execute(
                    "SELECT claim_id, provisional_results_seen"
                    " FROM forecast_claim_registry ORDER BY rowid"
                )
            ]

    def store(self) -> store_module.ForecastStore:
        return store_module.ForecastStore(self.db)

    def add_object(self, sql: str) -> None:
        with closing(sqlite3.connect(self.db)) as conn:
            conn.execute(sql)
            conn.commit()
