"""Tests for scripts/r2_first_run.py and the r2-probe.bat launcher.

Everything lives under ``tmp_path``: the "home", the fake backend folder, the synthetic DBs.
The real home, the real ``data`` folder, ``.env`` and port 8000 are never touched; the port
check, the notepad opener and the Enter prompt are injected.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from types import ModuleType

import pytest

from app.data.cache import PriceBarCache
from app.playbook.store import PlaybookStore

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND / "scripts" / "r2_first_run.py"
PROBE_PATH = BACKEND / "scripts" / "n177_n190_backtrack_probe.py"
BAT_PATH = BACKEND.parent / "r2-probe.bat"
INSTRUCTIONS = BACKEND.parents[2] / "work" / "dispatch" / "2026-11-13-R2探測操作說明-CEO.md"
SYMBOLS = ("2330", "2317", "9958")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("r2_first_run", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


r2 = _load()


# ------------------------------------------------------------------ staging


def _seed(path: Path, *, with_params: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    store = PlaybookStore(db_path=path)
    PriceBarCache(path)
    store.ensure_batches(list(SYMBOLS), batches_per_target=2)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("UPDATE playbook_batches SET status='open' WHERE symbol='2330'")
        conn.execute("UPDATE playbook_batches SET status='closed' WHERE symbol='9958'")
        if with_params:
            conn.execute(
                "INSERT INTO playbook_rule_params VALUES (?, ?, ?, ?, ?)",
                (
                    1,
                    json.dumps({"n_targets": 3, "batches_per_target": 2}),
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01",
                    "active",
                ),
            )
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


class Rig:
    """A fake backend folder (with a copy of the probe script) and a fake home."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.app = root / "stock-desk"
        self.backend = self.app / "backend"
        self.home = root / "home"
        (self.backend / "scripts").mkdir(parents=True)
        shutil.copyfile(PROBE_PATH, self.backend / "scripts" / PROBE_PATH.name)
        self.home.mkdir()
        self.db = self.backend / "data" / "stock-desk.db"
        self.opened: list[Path] = []
        self.prompts: list[str] = []

    def run(
        self,
        *,
        env: dict[str, str] | None = None,
        listening: bool = False,
        **extra: object,
    ) -> int:
        kwargs: dict[str, object] = {
            "backend_dir": self.backend,
            "home": self.home,
            "env": env or {},
            "port_check": lambda: listening,
            "wait": lambda prompt: self.prompts.append(prompt),
            "opener": self.opened.append,
        }
        kwargs.update(extra)
        return int(r2.run(**kwargs))

    def paste_back(self) -> Path:
        found = list(self.home.glob("stock-desk-n208/*/paste-back.txt"))
        assert len(found) == 1
        return found[0]

    def lines(self) -> list[str]:
        return self.paste_back().read_text(encoding="utf-8").splitlines()


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


@pytest.fixture
def seeded(rig: Rig) -> Rig:
    _seed(rig.db)
    return rig


def _tree_state(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


# ------------------------------------------------------------------ whitelist

SHA = r"[0-9a-f]{64}"
ALLOWED = [
    r"r2_first_run version=1",
    r"copied: stock-desk\.db(-wal|-shm)?",
    r"not present: stock-desk\.db(-wal|-shm)?",
    r"stock-desk\.db(-wal|-shm)?: (SAME|absent_both)",
    r"\(a2?\) [a-z_]+: \d+",
    r"\(b\) batches_per_symbol_distribution:",
    r"    \d+ batches: \d+ symbols",
    r"    \(no rows\)",
    r"\(b2\) symbols_whose_batch_no_is_not_1\.\.k: \d+",
    r"\(c\) batches_by_status:",
    r"    (planned|open|closed|skipped|other_status): \d+",
    r"\(d\) rule_params_in_force_on \(UTC date, same basis as backend\): \d{4}-\d{2}-\d{2}",
    r"    (n_targets|batches_per_target): \d+",
    r"    pending_versions_after_today: \d+",
    r"\(e[23]?\) [a-zA-Z_ =]+: (True|False)",
    r"N208_COUNT_RESULT=\d+",
    r"ERROR: (db copy not found|table playbook_batches not found|db copy unreadable)",
    r"n177_n190_backtrack_probe version=\d+",
    r"gate_affected_symbols=\d+",
    r"n199_[abc]_rows=\d+",
    rf"script_sha256_lf={SHA}",
    rf"db_sha256_(before|after)={SHA}",
    r"run_at_utc=\d{4}-\d{2}-\d{2}T[0-9:.+]+",
    r"probe_exit=\d+",
    r"probe_stderr_lines=\d+",
    r"db_location=default",
    r"port_8000_listening=no",
]
ALLOWED_RE = [re.compile(f"^{p}$") for p in ALLOWED]


def _assert_whitelisted(lines: list[str], extra: list[re.Pattern[str]] | None = None) -> None:
    patterns = ALLOWED_RE + (extra or [])
    for line in lines:
        assert any(p.match(line) for p in patterns), f"line not on the whitelist: {line!r}"


# ------------------------------------------------------------------ normal flow


def test_normal_flow_paste_back_is_whitelisted_and_clean(seeded: Rig) -> None:
    assert seeded.run() == 0
    lines = seeded.lines()
    text = "\n".join(lines)
    _assert_whitelisted(lines)
    assert lines[0] == "r2_first_run version=1"
    assert "probe_exit=0" in lines
    assert "(a) distinct_symbols: 3" in lines
    assert "    open: 2" in lines
    for prefix in r2.PROBE_PREFIXES:
        assert any(line.startswith(prefix) for line in lines), prefix
    for symbol in SYMBOLS:
        assert symbol not in text
    for fragment in (str(seeded.root), "/", "\\", "report_md", "report_json", "Traceback"):
        assert fragment not in text
    assert not re.search(r"[A-Za-z]:[\\/]", text)
    assert seeded.opened == [seeded.paste_back()]
    assert len(seeded.prompts) == 1


def test_normal_flow_console_output_is_ascii_and_has_no_symbols(
    seeded: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    assert seeded.run() == 0
    out = capsys.readouterr().out
    assert out.isascii()
    for symbol in SYMBOLS:
        assert symbol not in out
    assert str(seeded.root) not in out
    assert "report.md" in out and "dev-up.bat" in out and "Ctrl+A" in out
    assert "stock-desk backend" in out and "stock-desk scheduler" in out


def test_folders_are_created_and_report_stays_in_work_folder(seeded: Rig) -> None:
    assert seeded.run() == 0
    work = seeded.paste_back().parent
    assert work.parent == seeded.home / "stock-desk-n208"
    for name in ("backup", "probe", "probe-report"):
        assert (work / name).is_dir()
    assert (work / "probe-report" / "report.md").is_file()
    assert (work / "backup" / "stock-desk.db").is_file()
    assert (work / "probe" / "stock-desk.db").is_file()


def test_original_unchanged_and_no_new_files_in_data_folder(seeded: Rig) -> None:
    before = _tree_state(seeded.db.parent)
    assert seeded.run() == 0
    assert _tree_state(seeded.db.parent) == before


def test_wal_and_shm_files_are_copied_when_present(seeded: Rig) -> None:
    (seeded.db.parent / "stock-desk.db-wal").write_bytes(b"")
    (seeded.db.parent / "stock-desk.db-shm").write_bytes(b"")
    assert seeded.run() == 0
    lines = seeded.lines()
    assert "copied: stock-desk.db-wal" in lines
    assert "stock-desk.db-shm: SAME" in lines


def test_empty_database_uses_fixed_not_set_text(rig: Rig) -> None:
    _seed(rig.db, with_params=False)
    assert rig.run() == 0
    lines = rig.lines()
    assert any("NOT_SET" in line for line in lines)
    _assert_whitelisted(lines, [re.compile(r"^    (n_targets|batches_per_target): .*NOT_SET.*$")])


# ------------------------------------------------------------------ N-208 parity


def _original_snippet() -> str:
    text = INSTRUCTIONS.read_text(encoding="utf-8")
    match = re.search(r"\$N208_COUNT = @'\n(.*?)\n'@", text, re.DOTALL)
    assert match is not None
    return match.group(1) + "\n"


def _run_original(db: Path) -> tuple[list[str], int]:
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-", str(db)],
        input=_original_snippet(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return done.stdout.splitlines(), done.returncode


def _params_db(path: Path, payload: str) -> Path:
    _seed(path, with_params=False)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "INSERT INTO playbook_rule_params VALUES (1, ?, 't', '2026-01-01', 'active')",
            (payload,),
        )
        conn.execute(
            "INSERT INTO playbook_rule_params VALUES (2, ?, 't', '2999-01-01', 'pending')",
            (payload,),
        )
    return path


def _make_case(kind: str, folder: Path) -> Path:
    path = folder / "x.db"
    if kind == "populated":
        _seed(path)
    elif kind == "no_params":
        _seed(path, with_params=False)
    elif kind == "key_absent":
        _params_db(path, "{}")
    elif kind == "unreadable":
        _params_db(path, "not json")
    elif kind == "no_rows":
        PlaybookStore(db_path=path)
    elif kind == "gap_batches":
        _seed(path)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(
                "UPDATE playbook_batches SET batch_no=7 WHERE symbol='2317' AND batch_no=2"
            )
            conn.execute("UPDATE playbook_batches SET status='weird' WHERE symbol='9958'")
    else:
        assert kind == "no_table"
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("CREATE TABLE other (x INTEGER)")
    return path


@pytest.mark.parametrize(
    "kind",
    ["populated", "no_params", "key_absent", "unreadable", "no_rows", "gap_batches", "no_table"],
)
def test_n208_output_is_identical_to_the_instructions_snippet(kind: str, tmp_path: Path) -> None:
    db = _make_case(kind, tmp_path)
    expected, expected_code = _run_original(db)
    lines, code = r2.n208_count(db)
    assert lines == expected
    assert code == expected_code
    assert lines[-1] == f"N208_COUNT_RESULT={code}"


def test_n208_missing_file_matches_the_snippet(tmp_path: Path) -> None:
    missing = tmp_path / "nope.db"
    expected, expected_code = _run_original(missing)
    lines, code = r2.n208_count(missing)
    assert (lines, code) == (expected, expected_code)
    assert code == 20


def test_n208_never_writes_to_the_database(tmp_path: Path) -> None:
    db = _make_case("populated", tmp_path)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    r2.n208_count(db)
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


# ------------------------------------------------------------------ STOP cases


def _assert_stop(rig: Rig, message: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert rig.lines() == ["r2_first_run version=1", message]
    assert message in capsys.readouterr().out
    assert not rig.opened
    assert not (rig.paste_back().parent / "backup").exists()


def test_stop_when_env_var_is_set(seeded: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    assert seeded.run(env={"STOCK_DESK_DB_PATH": "SENTINEL-PATH-VALUE"}) != 0
    _assert_stop(seeded, "STOP: STOCK_DESK_DB_PATH is set in the environment", capsys)


def test_stop_when_env_file_has_the_key(seeded: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    (seeded.app / ".env").write_text(
        "FINMIND_TOKEN=SENTINEL-SECRET\n  STOCK_DESK_DB_PATH = D:\\SENTINEL-DB\\x.db\n",
        encoding="utf-8",
    )
    assert seeded.run() != 0
    shown = capsys.readouterr()
    assert "SENTINEL" not in shown.out + shown.err
    assert "SENTINEL" not in seeded.paste_back().read_text(encoding="utf-8")
    assert seeded.lines() == [
        "r2_first_run version=1",
        "STOP: STOCK_DESK_DB_PATH is set in apps/stock-desk/.env",
    ]
    assert "STOP: STOCK_DESK_DB_PATH is set in apps/stock-desk/.env" in shown.out


def test_env_file_without_the_key_does_not_stop(seeded: Rig) -> None:
    (seeded.app / ".env").write_text(
        "FINMIND_TOKEN=SENTINEL-SECRET\n# STOCK_DESK_DB_PATH=commented\nX_STOCK_DESK_DB_PATH=1\n",
        encoding="utf-8",
    )
    assert seeded.run() == 0
    assert "SENTINEL" not in "\n".join(seeded.lines())


def test_stop_when_default_db_is_missing(rig: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    assert rig.run() != 0
    _assert_stop(rig, "STOP: stock-desk.db not found at the default location", capsys)


def test_stop_when_port_8000_is_listening(seeded: Rig, capsys: pytest.CaptureFixture[str]) -> None:
    assert seeded.run(listening=True) != 0
    _assert_stop(
        seeded,
        "STOP: something is listening on port 8000; close the stock-desk windows and run again",
        capsys,
    )


def test_stop_when_copy_differs_from_original(
    seeded: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    def bad_copy(src: Path, dst: Path) -> None:
        shutil.copyfile(src, dst)
        with open(dst, "ab") as handle:
            handle.write(b"x")

    assert seeded.run(copier=bad_copy) != 0
    message = "STOP: the database changed while copying; a service is still running"
    out = capsys.readouterr().out
    assert message in out and "stock-desk.db: DIFFERENT" in out
    assert seeded.lines() == ["r2_first_run version=1", message]
    assert not seeded.opened
    assert not list((seeded.paste_back().parent / "probe").iterdir())


def test_stop_when_presence_differs(seeded: Rig) -> None:
    def partial_copy(src: Path, dst: Path) -> None:
        if src.name != "stock-desk.db-wal":
            shutil.copyfile(src, dst)

    (seeded.db.parent / "stock-desk.db-wal").write_bytes(b"w")
    assert seeded.run(copier=partial_copy) != 0
    assert seeded.lines()[-1].startswith("STOP: the database changed while copying")


def test_stop_when_work_folder_is_inside_a_git_work_tree(
    seeded: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    (seeded.home / ".git").mkdir()
    assert seeded.run() != 0
    _assert_stop(seeded, "STOP: the work folder would be inside a git work tree", capsys)
    assert not (seeded.paste_back().parent / "probe").exists()


# ------------------------------------------------------------------ probe failure


def test_probe_failure_writes_only_exit_code_and_line_count(rig: Rig) -> None:
    rig.db.parent.mkdir(parents=True)
    rig.db.write_text("SENTINEL-NOT-A-DATABASE", encoding="utf-8")
    assert rig.run() == 0
    _assert_whitelisted(rig.lines())
    lines = rig.lines()
    text = "\n".join(lines)
    assert any(re.fullmatch(r"probe_exit=[1-9]\d*", line) for line in lines)
    assert any(re.fullmatch(r"probe_stderr_lines=[1-9]\d*", line) for line in lines)
    assert "SENTINEL" not in text
    assert "cannot read" not in text
    assert not any(line.startswith(r2.PROBE_PREFIXES) for line in lines)


def test_probe_stdout_noise_and_stderr_never_reach_the_file(
    seeded: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            [],
            4,
            stdout="report_md=/x/y\nreport_json=/x/z\nnoise\n",
            stderr="/secret/path\nmore\n",
        )

    monkeypatch.setattr(r2.subprocess, "run", fake_run)
    assert seeded.run() == 0
    lines = seeded.lines()
    assert lines[-4:] == [
        "probe_exit=4",
        "probe_stderr_lines=2",
        "db_location=default",
        "port_8000_listening=no",
    ]
    assert not any("report_" in line or "secret" in line or "noise" in line for line in lines)


# ------------------------------------------------------------------ robustness


def test_unexpected_exception_prints_fixed_text_and_exits_nonzero(
    seeded: Rig, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(path: Path) -> None:
        raise RuntimeError(f"SENTINEL {path}")

    monkeypatch.delenv("STOCK_DESK_DB_PATH", raising=False)
    monkeypatch.setattr(r2, "n208_count", boom)
    code = r2.main(
        ["--backend-dir", str(seeded.backend), "--home", str(seeded.home)],
        port_check=lambda: False,
        wait=lambda prompt: None,
        opener=lambda path: None,
    )
    assert code == 1
    captured = capsys.readouterr()
    assert r2.UNEXPECTED in captured.out
    assert "SENTINEL" not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err


def test_opener_failure_is_reported_without_a_path(
    seeded: Rig, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing(path: Path) -> None:
        raise OSError(str(path))

    assert seeded.run(opener=failing) == 0
    out = capsys.readouterr().out
    assert "Could not open notepad" in out
    assert str(seeded.root) not in out


def test_port_check_detects_a_listener_on_loopback() -> None:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert r2.port_is_listening(port) is True
    assert r2.port_is_listening(port) is False


def test_cli_main_with_overrides(seeded: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STOCK_DESK_DB_PATH", raising=False)
    code = r2.main(
        ["--backend-dir", str(seeded.backend), "--home", str(seeded.home)],
        port_check=lambda: False,
        wait=lambda prompt: None,
        opener=lambda path: None,
    )
    assert code == 0
    _assert_whitelisted(seeded.lines())


# ------------------------------------------------------------------ static checks


def test_script_imports_only_the_standard_library() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            modules.add((node.module or "").split(".")[0])
    assert modules
    assert "app" not in modules
    assert modules <= set(sys.stdlib_module_names)


def test_bat_is_ascii_thin_and_does_not_pull() -> None:
    text = BAT_PATH.read_bytes().decode("ascii")
    assert "r2_first_run.py" in text
    assert "git pull" not in text.lower()
    assert "uv run --no-sync python -I -X utf8 scripts\\r2_first_run.py" in text
    assert "@echo off" in text
    assert "pause" in text
    assert "where uv" in text


def test_script_source_is_ascii() -> None:
    SCRIPT_PATH.read_bytes().decode("ascii")
