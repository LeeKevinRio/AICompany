"""One-click R2 first run: copy the DB, count for N-208, run the N-177 / N-190 probe.

Standard library only; never imports ``app``; never touches the network (the only socket use is
one connect to 127.0.0.1 to see whether the backend still listens).

Read-only toward the original database: it is copied (never opened) and everything after the
copy works on the copy. The text pasted back to the coordinator is a closed whitelist:
counts, hashes, timestamps. No symbol, no path, no stderr text, no value from ``.env``.

Everything printed to the console is plain ASCII (cmd.exe handles other text unreliably).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

HEADER = "r2_first_run version=1"
DB_NAME = "stock-desk.db"
DB_FILES = ("stock-desk.db", "stock-desk.db-wal", "stock-desk.db-shm")
PORT = 8000
ENV_VAR = "STOCK_DESK_DB_PATH"
ENV_KEY_PATTERN = re.compile(r"^\s*STOCK_DESK_DB_PATH\s*=")
PROBE_SCRIPT = Path("scripts") / "n177_n190_backtrack_probe.py"
PROBE_PREFIXES = (
    "n177_n190_backtrack_probe version=",
    "gate_affected_symbols=",
    "n199_a_rows=",
    "n199_b_rows=",
    "n199_c_rows=",
    "script_sha256_lf=",
    "db_sha256_before=",
    "db_sha256_after=",
    "run_at_utc=",
)
PASTE_BACK_NAME = "paste-back.txt"

INTRO = (
    "R2 first run (read-only check of a COPY of the stock-desk database)",
    "",
    "This tool only reads a copy. It never writes to the original database.",
    "Before you continue, close these three windows:",
    "  - stock-desk backend",
    "  - stock-desk scheduler",
    "  - stock-desk frontend",
)
OUTRO = (
    "",
    "Done. Notepad should now show the text to send back (paste-back.txt).",
    "  1. Select all (Ctrl+A), copy (Ctrl+C), and paste it to the coordinator.",
    "  2. The probe-report folder holds report.md with holdings and cash.",
    "     Keep it on this computer only. Do not paste or send it to anyone.",
    "  3. Keep the work folder (stock-desk-n208 in your user folder). Do not delete it.",
    "  4. You can start dev-up.bat again now.",
)
UNEXPECTED = "ERROR: unexpected failure; send a screenshot of this window to the coordinator"


def _say(text: str = "") -> None:
    """Console output, ASCII only (the file keeps the exact text)."""
    print(text.encode("ascii", "backslashreplace").decode("ascii"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def n208_count(db_path: Path) -> tuple[list[str], int]:
    """The N-208 read-only count; same logic and same output lines as the CEO instructions."""
    lines: list[str] = []

    def out(*parts: object) -> None:
        lines.append(" ".join(str(part) for part in parts))

    def done(code: int) -> tuple[list[str], int]:
        out(f"N208_COUNT_RESULT={code}")
        return lines, code

    p = Path(db_path)
    if not p.is_file():
        out("ERROR: db copy not found")
        return done(20)
    c = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        c.execute("PRAGMA query_only=ON")
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "playbook_batches" not in names:
            out("ERROR: table playbook_batches not found")
            return done(20)
        rows = c.execute("SELECT symbol, batch_no, status FROM playbook_batches").fetchall()
        per = Counter(r[0] for r in rows)
        nos: dict[object, set[object]] = {}
        for s, n, _ in rows:
            nos.setdefault(s, set()).add(n)
        active = {s for s, _, st in rows if st in ("planned", "open")}
        out("(a) distinct_symbols:", len(per))
        out("(a2) symbols_with_planned_or_open:", len(active))
        out("(b) batches_per_symbol_distribution:")
        for k, v in sorted(Counter(per.values()).items()):
            out(f"    {k} batches: {v} symbols")
        if not per:
            out("    (no rows)")
        out(
            "(b2) symbols_whose_batch_no_is_not_1..k:",
            sum(1 for s in nos if nos[s] != set(range(1, per[s] + 1))),
        )
        st = Counter(r[2] for r in rows)
        out("(c) batches_by_status:")
        for k in ("planned", "open", "closed", "skipped"):
            out(f"    {k}: {st.pop(k, 0)}")
        out("    other_status:", sum(st.values()))
        today = datetime.now(UTC).date().isoformat()
        nt: object = None
        bpt: object = None
        if "playbook_rule_params" in names:
            r = c.execute(
                "SELECT payload FROM playbook_rule_params WHERE effective_date <= ? "
                "ORDER BY effective_date DESC, version DESC LIMIT 1",
                (today,),
            ).fetchone()
            pend = c.execute(
                "SELECT COUNT(*) FROM playbook_rule_params WHERE effective_date > ?", (today,)
            ).fetchone()[0]
        else:
            r, pend = None, 0
        out("(d) rule_params_in_force_on (UTC date, same basis as backend):", today)
        if r is None:
            not_set = "\u672a\u8a2d\u5b9a (NOT_SET; default {} from app/playbook/models.py:{})"
            out("    n_targets: " + not_set.format(5, 88))
            out("    batches_per_target: " + not_set.format(3, 89))
            nt, bpt = 5, 3
        else:
            try:
                d = json.loads(r[0])
            except ValueError:
                d = {}
                out("    payload: UNREADABLE")
            nt, bpt = d.get("n_targets"), d.get("batches_per_target")
            out(
                "    n_targets:",
                nt if nt is not None else "KEY_ABSENT (default 5 from app/playbook/models.py:88)",
            )
            out(
                "    batches_per_target:",
                bpt if bpt is not None else "KEY_ABSENT (default 3 from app/playbook/models.py:89)",
            )
            nt = 5 if nt is None else nt
            bpt = 3 if bpt is None else bpt
        out("    pending_versions_after_today:", pend)
        out("(e) distinct_symbols == n_targets:", len(per) == nt)
        out("(e2) symbols_with_planned_or_open == n_targets:", len(active) == nt)
        out(
            "(e3) every symbol has batches_per_target batches:",
            bool(per) and all(v == bpt for v in per.values()),
        )
    except sqlite3.Error:
        lines.clear()
        out("ERROR: db copy unreadable")
        return done(21)
    finally:
        c.close()
    return done(0)


def port_is_listening(port: int = PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def inside_git_work_tree(path: Path) -> bool:
    resolved = path.resolve()
    return any((folder / ".git").exists() for folder in (resolved, *resolved.parents))


def env_file_sets_db_path(env_file: Path) -> bool:
    """True when some line of the file starts with the key. Only the key is looked for."""
    if not env_file.is_file():
        return False
    with open(env_file, encoding="utf-8", errors="replace") as handle:
        return any(ENV_KEY_PATTERN.match(line) for line in handle)


def compare_copy(source_dir: Path, copy_dir: Path) -> list[str]:
    """One ``<name>: <verdict>`` line per DB file (same verdicts as the CEO instructions)."""
    lines = []
    for name in DB_FILES:
        a, b = source_dir / name, copy_dir / name
        if a.exists() != b.exists():
            verdict = "PRESENCE_DIFFERS"
        elif not a.exists():
            verdict = "absent_both"
        elif sha256_file(a) == sha256_file(b):
            verdict = "SAME"
        else:
            verdict = "DIFFERENT"
        lines.append(f"{name}: {verdict}")
    return lines


def write_paste_back(work: Path, lines: Sequence[str]) -> None:
    work.mkdir(parents=True, exist_ok=True)
    with open(work / PASTE_BACK_NAME, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def run(
    *,
    backend_dir: Path,
    home: Path,
    env: Mapping[str, str],
    port_check: Callable[[], bool] = port_is_listening,
    wait: Callable[[str], object] = input,
    opener: Callable[[Path], object] | None = None,
    copier: Callable[[Path, Path], object] = shutil.copyfile,
    now: Callable[[], datetime] = datetime.now,
) -> int:
    work = home / "stock-desk-n208" / now().strftime("%Y%m%d-%H%M%S")

    def stop(message: str) -> int:
        _say()
        _say(message)
        write_paste_back(work, [HEADER, message])
        _say()
        _say("A text file with this message was written to the work folder.")
        _say("Tell the coordinator which STOP message you saw.")
        return 3

    for text in INTRO:
        _say(text)
    wait("Press Enter when the three windows are closed. ")

    source_dir = backend_dir / "data"
    if env.get(ENV_VAR):
        return stop("STOP: STOCK_DESK_DB_PATH is set in the environment")
    if env_file_sets_db_path(backend_dir.parent / ".env"):
        return stop("STOP: STOCK_DESK_DB_PATH is set in apps/stock-desk/.env")
    if not (source_dir / DB_NAME).is_file():
        return stop("STOP: stock-desk.db not found at the default location")
    if port_check():
        return stop(
            "STOP: something is listening on port 8000; close the stock-desk windows and run again"
        )
    if inside_git_work_tree(work):
        return stop("STOP: the work folder would be inside a git work tree")

    backup, probe, report = work / "backup", work / "probe", work / "probe-report"
    for folder in (backup, probe, report):
        folder.mkdir(parents=True)

    result: list[str] = [HEADER]
    copy_lines: list[str] = []
    for name in DB_FILES:
        if (source_dir / name).exists():
            copier(source_dir / name, backup / name)
            copy_lines.append(f"copied: {name}")
        else:
            copy_lines.append(f"not present: {name}")
    copy_lines += compare_copy(source_dir, backup)
    for line in copy_lines:
        _say(line)
    if any(line.endswith((": DIFFERENT", ": PRESENCE_DIFFERS")) for line in copy_lines):
        return stop("STOP: the database changed while copying; a service is still running")
    result += copy_lines
    for name in DB_FILES:
        if (backup / name).exists():
            shutil.copyfile(backup / name, probe / name)

    count_lines, _ = n208_count(probe / DB_NAME)
    result += count_lines

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-X",
            "utf8",
            str(PROBE_SCRIPT),
            "--db-path",
            str(probe / DB_NAME),
            "--out-dir",
            str(report),
        ],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    result += [line for line in completed.stdout.splitlines() if line.startswith(PROBE_PREFIXES)]
    result.append(f"probe_exit={completed.returncode}")
    if completed.returncode != 0:
        result.append(f"probe_stderr_lines={len(completed.stderr.splitlines())}")
    result += ["db_location=default", "port_8000_listening=no"]

    write_paste_back(work, result)
    _say()
    _say("----- text to send back (also saved as paste-back.txt) -----")
    for line in result:
        _say(line)
    _say("-----")

    if opener is None and sys.platform == "win32":
        opener = getattr(os, "startfile", None)
    if opener is not None:
        try:
            opener(work / PASTE_BACK_NAME)
        except OSError:
            _say("Could not open notepad. Open paste-back.txt in the work folder yourself.")
    for text in OUTRO:
        _say(text)
    return 0


def main(
    argv: Sequence[str] | None = None,
    **injected: object,
) -> int:
    parser = argparse.ArgumentParser(prog="r2_first_run.py")
    # Test-only overrides; the batch file never passes them.
    parser.add_argument("--backend-dir", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--home", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    backend = Path(args.backend_dir) if args.backend_dir else Path(__file__).resolve().parents[1]
    home = Path(args.home) if args.home else Path.home()
    try:
        return run(backend_dir=backend, home=home, env=os.environ, **injected)  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - fixed text only, never the exception or a path
        _say(UNEXPECTED)
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
