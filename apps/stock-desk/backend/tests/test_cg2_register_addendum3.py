"""ADR-0030 supplement 7 addendum 3 (S-15c) for ``scripts/cg2_register.py``.

Point 1: the three new watched files and the ``ls-files -v`` tags (R-1). Point 2: the register run's
preflight binding. Point 3: two equal backups, the port check after the typed answer, ``Popen``.
Point 4: ``review_refs`` checked at run time. Point 5: the refusal reason. Point 6: the exit codes
of interruptions. Point 7: the preflight probes. Same synthetic worlds as the flow tests.
"""

from __future__ import annotations

import hashlib
import inspect
import os
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from app.forecast import claims, schema
from tests.cg2_register_loader import SCRIPT_PATH
from tests.cg2_register_world import STAMP, World, git, real
from tests.test_cg2_register_flow import STOP_SENTENCES, run, stop, stop_lines


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def watched(world: World) -> dict[str, Path]:
    return {
        "script": world.backend / "scripts" / "cg2_register.py",
        "preflight_bat": world.repo / real.BAT_RELS[0],
        "register_bat": world.repo / real.BAT_RELS[1],
    }


# === point 1: R-1 ========================================================================


@pytest.mark.parametrize("which", ["script", "preflight_bat", "register_bat"])
@pytest.mark.parametrize("mode", ["preflight", "register"])
def test_p1_each_new_watched_file_with_an_uncommitted_change_stops(
    world: World, capsys: Any, which: str, mode: str
) -> None:
    path = watched(world)[which]
    path.write_bytes(path.read_bytes() + b"# edited\r\n")
    stop(world, capsys, mode, "git_dirty")


@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
@pytest.mark.parametrize("target", ["app", "prereg", "c8", "script", "preflight_bat"])
def test_p1_a_hidden_change_is_a_stop(world: World, capsys: Any, flag: str, target: str) -> None:
    paths = {
        "app": world.backend / "app" / "forecast" / "__init__.py",
        "prereg": world.repo / world.pins.frozen("prereg").path,
        "c8": world.repo / world.pins.frozen("c8").path,
        **watched(world),
    }
    path = paths[target]
    git(world.repo, "update-index", flag, str(path.relative_to(world.repo)))
    path.write_bytes(path.read_bytes() + b"# edited and hidden from status\r\n")
    stop(world, capsys, "preflight", "git_dirty")


def test_p1_the_hidden_change_would_pass_without_the_tag_check(world: World, capsys: Any) -> None:
    """The point of the tag check: ``status`` alone reports a clean tree."""
    path = watched(world)["script"]
    git(world.repo, "update-index", "--assume-unchanged", str(path.relative_to(world.repo)))
    path.write_bytes(path.read_bytes() + b"# hidden\n")
    code, out = real.run_git(world.repo, ["status", "--porcelain", "--", real.SCRIPT_REL])
    assert code == 0 and out == b""
    stop(world, capsys, "preflight", "git_dirty")


def test_p1_every_git_call_disables_fsmonitor_and_the_untracked_cache(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[list[str]] = []
    original = real.subprocess.run

    def spy(argv: Any, *args: Any, **kwargs: Any) -> Any:
        if argv and argv[0] == "git":
            seen.append(list(argv))
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(real.subprocess, "run", spy)
    assert run(world, capsys, "preflight")[0] == 0
    assert len(seen) >= 8
    for argv in seen:
        flags = [argv[i + 1] for i, a in enumerate(argv) if a == "-c"]
        assert flags == ["core.fsmonitor=false", "core.untrackedCache=false"], argv


def test_p1_no_code_digest_constant_is_pinned_and_the_tree_id_constant_stays() -> None:
    assert not any("digest" in name for name in vars(real.Pins)["__dataclass_fields__"])
    assert real.REAL_PINS.app_tree_id == "9c157d8640fb97d7e90dc7edc3f5ff0252aa00d7"


def test_p1_the_watched_files_are_the_script_and_the_two_launchers() -> None:
    assert real.SCRIPT_REL == "apps/stock-desk/backend/scripts/cg2_register.py"
    assert real.BAT_RELS == (
        "apps/stock-desk/cg2-preflight.bat",
        "apps/stock-desk/cg2-register.bat",
    )


# === point 2: the preflight binding ======================================================


def good_preflight(world: World, capsys: Any) -> Path:
    assert world.run("preflight") == 0
    capsys.readouterr()
    (path,) = world.paste_backs()
    return path


def refused_binding(world: World, capsys: Any) -> None:
    before = world.logical_state()
    probes = world.runner.probes
    code, lines = run(world, capsys, "register", preflight=False)
    assert (code, lines) == (3, stop_lines("preflight_mismatch"))
    assert world.runner.probes == probes  # the probe was not called by the register run
    assert world.backups() == []  # no backup
    assert world.runner.calls == [] and world.runner.events == []  # no child, no question
    assert world.logical_state() == before


def test_p2_a_matching_preflight_lets_the_register_run_go_on(world: World, capsys: Any) -> None:
    good_preflight(world, capsys)
    later = real.datetime(2026, 11, 20, 21, 9, 0)
    code, _lines = run(world, capsys, "register", preflight=False, now=lambda: later)
    assert code == 0


def test_p2_no_preflight_file(world: World, capsys: Any) -> None:
    refused_binding(world, capsys)


def test_p2_an_empty_paste_back_folder(world: World, capsys: Any) -> None:
    (world.work / real.PASTE_DIR_NAME).mkdir(parents=True)
    refused_binding(world, capsys)


def test_p2_the_file_cannot_be_read_as_text(world: World, capsys: Any) -> None:
    path = good_preflight(world, capsys)
    path.write_bytes(b"\xff\xfe\x00broken\xff")
    refused_binding(world, capsys)


def test_p2_a_line_is_off_the_whitelist(world: World, capsys: Any) -> None:
    path = good_preflight(world, capsys)
    path.write_text(path.read_text("utf-8-sig") + "backup_path=somewhere\n", "utf-8-sig")
    refused_binding(world, capsys)


def test_p2_no_pass_line(world: World, capsys: Any) -> None:
    path = good_preflight(world, capsys)
    lines = [x for x in path.read_text("utf-8-sig").splitlines() if x != "preflight_result=PASS"]
    path.write_text("\n".join(lines) + "\n", "utf-8-sig")
    refused_binding(world, capsys)


def test_p2_the_git_head_is_not_this_runs(world: World, capsys: Any) -> None:
    path = good_preflight(world, capsys)
    text = path.read_text("utf-8-sig").replace(f"git_head={world.head}", f"git_head={'c' * 40}")
    path.write_text(text, "utf-8-sig")
    refused_binding(world, capsys)


def test_p2_the_script_hash_is_not_this_runs(world: World, capsys: Any) -> None:
    path = good_preflight(world, capsys)
    lines = path.read_text("utf-8-sig").splitlines()
    lines = [
        f"script_sha256_lf={'d' * 64}" if x.startswith("script_sha256_lf=") else x for x in lines
    ]
    path.write_text("\n".join(lines) + "\n", "utf-8-sig")
    refused_binding(world, capsys)


def test_p2_a_file_that_is_not_a_passed_preflight_at_all(world: World, capsys: Any) -> None:
    folder = world.work / real.PASTE_DIR_NAME
    folder.mkdir(parents=True)
    (folder / f"preflight-{STAMP}.txt").write_text("", "utf-8-sig")
    refused_binding(world, capsys)


def test_p2_the_newest_file_decides(world: World, capsys: Any) -> None:
    older = good_preflight(world, capsys)
    newer = older.with_name("preflight-20261120-215959.txt")
    newer.write_bytes(older.read_bytes().replace(b"preflight_result=PASS", b"preflight_result=NO"))
    refused_binding(world, capsys)
    newer.unlink()
    older_text = older.read_bytes()
    older.write_bytes(older_text.replace(b"preflight_result=PASS", b"preflight_result=NO"))
    newer.write_bytes(older_text)  # an old bad one, a new good one
    later = real.datetime(2026, 11, 20, 22, 0, 0)
    assert run(world, capsys, "register", preflight=False, now=lambda: later)[0] == 0


def test_p2_the_binding_comes_after_the_prechecks(world: World, capsys: Any) -> None:
    world.add_object("CREATE TABLE plan_x (a)")
    code, lines = run(world, capsys, "register", preflight=False)
    assert (code, lines) == (3, stop_lines("ledger_objects"))


# === point 3: backups, the port after the typed answer, Popen ============================


@pytest.mark.parametrize("wal", [False, True], ids=["no_wal", "wal"])
def test_p3_the_two_backups_are_equal_and_the_recorded_hash_is_theirs(
    world: World, capsys: Any, wal: bool
) -> None:
    holder = None
    if wal:
        with closing(sqlite3.connect(world.db)) as setup:
            setup.execute("PRAGMA journal_mode = WAL")
        holder = sqlite3.connect(world.db)
        holder.execute("PRAGMA wal_autocheckpoint = 0")
        holder.execute("INSERT INTO app_settings VALUES ('in_wal', 'yes')")
        holder.commit()
    try:
        code, lines = run(world, capsys, "register")
    finally:
        if holder is not None:
            holder.close()
    assert code == 0
    first = world.main_backup()
    (second,) = [p for p in world.backups() if p != first]
    assert second.name == real.verify_file_name(STAMP) and first.name == real.backup_file_name(
        STAMP
    )
    assert first.read_bytes() == second.read_bytes()  # byte for byte
    digest = hashlib.sha256(first.read_bytes()).hexdigest()
    assert lines.count(f"backup_sha256={digest}") == 1


def test_p3_two_backups_that_differ_are_a_stop_and_both_stay(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = real._backup_once
    calls = {"n": 0}

    def with_a_write_between(db: Path, target: Path) -> Any:
        result = original(db, target)
        calls["n"] += 1
        if calls["n"] == 1:  # another process writes between the two copies
            world.add_object("INSERT INTO app_settings VALUES ('late', 'write')")
        return result

    monkeypatch.setattr(real, "_backup_once", with_a_write_between)
    code, lines = run(world, capsys, "register")
    assert code == 3 and lines[0] == STOP_SENTENCES["backup_mismatch"]
    assert len(world.backups()) == 2  # nothing is deleted
    assert lines == [STOP_SENTENCES["backup_mismatch"]]  # no hash is agreed, so none is shown
    assert world.runner.calls == [] and world.asked.count(real.PROMPT_SEEN) == 0


def test_p3_the_port_is_checked_again_after_the_typed_answer(world: World, capsys: Any) -> None:
    def ask(prompt: str) -> str:
        world.asked.append(prompt)
        if prompt == real.PROMPT_SEEN:
            world.listening = True  # a service started while the CEO was typing
            return "0"
        return ""

    code, lines = run(world, capsys, "register", ask=ask)
    digest = hashlib.sha256(world.main_backup().read_bytes()).hexdigest()
    assert code == 3
    assert lines == [STOP_SENTENCES["port_listening"], f"backup_sha256={digest}"]
    assert world.runner.calls == []  # the child was never started
    assert [p.name for p in world.paste_backs()] == []


def test_p3_popen_that_cannot_start_the_child_is_exit_3_and_not_late(
    world: World, capsys: Any
) -> None:
    world.runner.start_error = OSError("C:\\secret\\python.exe")
    code, lines = run(world, capsys, "register")
    assert code == 3 and lines[0] == STOP_SENTENCES["claims_not_started"]
    assert lines[-1].startswith("backup_sha256=") and not any("secret" in x for x in lines)
    assert world.paste_backs() == []  # nothing "may have been written"


def test_p3_an_error_that_is_not_oserror_while_starting_is_still_before_the_registration(
    world: World, capsys: Any
) -> None:
    world.runner.start_error = RuntimeError("secret")
    code, lines = run(world, capsys, "register")
    assert code == 1 and lines[0] == real.UNEXPECTED_SAFE
    assert world.paste_backs() == []


def test_p3_late_starts_only_after_the_child_exists(world: World, capsys: Any) -> None:
    seen: dict[str, bool] = {}
    state_holder: dict[str, Any] = {}
    original = real.State

    class Spy(original):  # type: ignore[valid-type, misc]
        def __init__(self) -> None:
            super().__init__()
            state_holder["state"] = self

    real.State = Spy  # type: ignore[misc]
    try:
        world.runner.before_run = lambda: seen.setdefault(
            "late_at_start", state_holder["state"].late
        )
        assert run(world, capsys, "register")[0] == 0
    finally:
        real.State = original
    assert seen == {"late_at_start": False}


def test_p3_a_child_that_times_out_is_unconfirmed_exit_5(world: World, capsys: Any) -> None:
    world.runner.raises = real.ClaimsTimeout()
    code, lines = run(world, capsys, "register")
    assert code == 5 and lines[0] == STOP_SENTENCES["written_unknown"]
    (paste,) = world.paste_backs()
    assert paste.read_text("utf-8-sig").splitlines()[-2] == "register_result=UNCONFIRMED"


# === point 4: review_refs at run time ====================================================


@pytest.mark.parametrize("index", range(2))
@pytest.mark.parametrize("mode", ["preflight", "register"])
def test_p4_a_review_record_that_is_not_in_head_stops(
    world: World, capsys: Any, mode: str, index: int
) -> None:
    ref = world.pins.review_refs[index]
    git(world.repo, "rm", "-q", "--cached", ref)
    git(world.repo, "commit", "-q", "-m", "remove a record")
    git(world.repo, "update-ref", "refs/remotes/origin/product/stock-desk", "HEAD")
    code, lines = run(world, capsys, mode)
    assert (code, lines) == (3, stop_lines("review_refs_missing"))
    assert world.runner.probes == 0 and world.backups() == [] and world.runner.calls == []


def test_p4_every_path_is_asked_of_git_with_cat_file_e(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []

    def spy(cwd: Path, args: Any) -> tuple[int, bytes]:
        if "cat-file" in args and "-e" in args:
            asked.append(list(args))
        code, out = real.run_git(cwd, args)
        return int(code), bytes(out)

    assert run(world, capsys, "preflight", git=spy)[0] == 0
    assert [a[-1] for a in asked] == [f"HEAD:{ref}" for ref in world.pins.review_refs]


def test_p4_the_paths_in_the_constants_have_no_whitespace() -> None:
    for ref in real.REAL_PINS.review_refs:
        assert ref == ref.strip() and not any(ch.isspace() for ch in ref)


# === point 5: the refusal reason =========================================================


def test_p5_the_tables_equal_the_two_tables_of_claims() -> None:
    assert dict(real.REFUSALS_EXIT_4) == claims.BOOTSTRAP_PATH_REFUSALS
    assert dict(real.REFUSALS_EXIT_3) == claims.BOOTSTRAP_REFUSALS
    keys = [*claims.BOOTSTRAP_PATH_REFUSALS, *claims.BOOTSTRAP_REFUSALS, "unknown"]
    assert list(real.REFUSAL_CODES) == keys and len(set(keys)) == len(keys) == 19


def test_p5_the_script_does_not_import_claims() -> None:
    import ast

    imported = set()
    for node in ast.walk(ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("claims" in name for name in imported)


ALL_CODES = [
    *[(4, key) for key in claims.BOOTSTRAP_PATH_REFUSALS],
    *[(3, key) for key in claims.BOOTSTRAP_REFUSALS],
]


@pytest.mark.parametrize(("exit_code", "key"), ALL_CODES)
def test_p5_each_code_is_shown_after_the_stop_sentence_and_only_on_the_screen(
    world: World, capsys: Any, exit_code: int, key: str
) -> None:
    table = claims.BOOTSTRAP_PATH_REFUSALS if exit_code == 4 else claims.BOOTSTRAP_REFUSALS
    world.runner.override = real.CliResult(exit_code, "", table[key] + "\n")
    code, lines = run(world, capsys, "register")
    stop_key = "refused_4" if exit_code == 4 else "refused_3"
    digest = hashlib.sha256(world.main_backup().read_bytes()).hexdigest()
    assert code == 3
    assert lines == [STOP_SENTENCES[stop_key], f"refusal_reason={key}", f"backup_sha256={digest}"]
    assert not any(table[key] in line for line in lines)  # the stderr text is never shown
    assert world.paste_backs() == []  # and no paste-back file holds it either


@pytest.mark.parametrize("exit_code", [3, 4])
@pytest.mark.parametrize(
    "stderr",
    [
        "",
        "refused: something else entirely\n",
        "refused: the production database is not at its default location extra",
        'Traceback (most recent call last):\n  File "C:\\Users\\x\\claims.py"\n',
        " refused: --frozen-commit must be 40 lower-case hex digits\n",
        "refused: --frozen-commit must be 40 lower-case hex digits\nsecond line\n",
    ],
)
def test_p5_anything_else_is_unknown_and_never_shown(
    world: World, capsys: Any, exit_code: int, stderr: str
) -> None:
    world.runner.override = real.CliResult(exit_code, "", stderr)
    code, lines = run(world, capsys, "register")
    assert code == 3 and lines[1] == "refusal_reason=unknown"
    assert not any("Traceback" in x or "Users" in x or "something" in x for x in lines)


def test_p5_a_sentence_of_the_other_exit_codes_table_is_unknown(world: World, capsys: Any) -> None:
    world.runner.override = real.CliResult(3, "", claims.BOOTSTRAP_PATH_REFUSALS["db_missing"])
    assert run(world, capsys, "register")[1][1] == "refusal_reason=unknown"


def test_p5_a_crlf_line_end_is_removed_before_the_comparison() -> None:
    text = claims.BOOTSTRAP_REFUSALS["store"]
    assert real.refusal_reason(3, text + "\r\n") == "store"
    assert real.refusal_reason(3, text + "\n\n") == "store"
    assert real.refusal_reason(4, text) == "unknown"


@pytest.mark.parametrize("exit_code", [5, 1, 2, 7])
def test_p5_exit_5_and_the_others_print_no_reason(
    world: World, capsys: Any, exit_code: int
) -> None:
    world.runner.override = real.CliResult(exit_code, "", claims.BOOTSTRAP_REFUSALS["store"] + "\n")
    _code, lines = run(world, capsys, "register")
    assert not any(line.startswith("refusal_reason=") for line in lines)


def test_p5_the_reason_line_is_a_closed_set_and_screen_only() -> None:
    assert real.REFUSAL_PATTERN.fullmatch("refusal_reason=not_empty")
    assert real.REFUSAL_PATTERN.fullmatch("refusal_reason=unknown")
    for bad in ("refusal_reason=other", "refusal_reason=", "refusal_reason=not_empty ", "x"):
        assert not real.REFUSAL_PATTERN.fullmatch(bad)
    assert not real.on_whitelist("refusal_reason=unknown")  # never allowed into a file
    assert real.on_screen("refusal_reason=unknown")


def _cli_case(world: World, name: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Make the REAL registration program refuse for ``name``; return the expected code."""
    original = real.bootstrap_args

    def patched(mutate: Callable[[list[str]], list[str]]) -> None:
        monkeypatch.setattr(real, "bootstrap_args", lambda **kw: mutate(original(**kw)))

    def swap(args: list[str]) -> list[str]:
        a = args.index("--rules-version")
        b = args.index("--rules-version", a + 1)
        args[a + 1], args[b + 1] = args[b + 1], args[a + 1]
        return args

    if name == "env_db_path":
        world.runner.env = {"STOCK_DESK_DB_PATH": "x.db"}
    elif name == "not_empty":
        world.runner.before_run = lambda: world.add_object("CREATE TABLE plan_late (a)")
    elif name == "horizons":
        patched(swap)
    elif name == "replaces":
        patched(lambda a: [*a, "--replaces-claim-id", "x"])
    elif name == "prereg_blob":
        patched(lambda a: [("0" * 40 if x == world.head else x) for x in a])
    elif name == "prereg_mismatch":
        patched(lambda a: [("e" * 64 if x == world.pins.frozen("prereg").sha256 else x) for x in a])
    elif name == "provisional":
        patched(lambda a: [*a[:-1], "2"])
    elif name == "frozen_commit":
        patched(lambda a: [("short" if x == world.head else x) for x in a])
    elif name == "store":
        from tests.cg2_register_world import StuckClock

        world.runner.clock = StuckClock()
    else:
        raise AssertionError(name)
    return name


@pytest.mark.parametrize(
    "name",
    [
        "env_db_path",
        "not_empty",
        "horizons",
        "replaces",
        "prereg_blob",
        "prereg_mismatch",
        "provisional",
        "frozen_commit",
        "store",
    ],
)
def test_p5_the_real_program_refuses_and_the_code_is_the_one_of_its_sentence(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    _cli_case(world, name, monkeypatch)
    code, lines = run(world, capsys, "register")
    assert code == 3 and lines[1] == f"refusal_reason={name}", lines


def test_p5_the_database_symlink_case_gives_db_not_default(
    world: World, capsys: Any, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere.db"
    world.db.rename(elsewhere)
    world.db.symlink_to(elsewhere)
    _code, lines = run(world, capsys, "register")
    assert lines[1] == "refusal_reason=db_not_default"


# === point 6: interruptions ==============================================================


def test_p6_an_interrupt_while_starting_is_exit_2_with_no_paste_back(
    world: World, capsys: Any
) -> None:
    world.runner.start_error = KeyboardInterrupt()
    code, lines = run(world, capsys, "register")
    assert code == 2 and lines[0] == real.INTERRUPTED_SAFE and world.paste_backs() == []


def test_p6_an_interrupt_after_the_start_is_exit_5_and_leaves_an_unconfirmed_paste_back(
    world: World, capsys: Any
) -> None:
    world.runner.raises = KeyboardInterrupt()
    code, lines = run(world, capsys, "register")
    assert code == 5 and lines[0] == real.INTERRUPTED_LATE
    (paste,) = world.paste_backs()
    text = paste.read_text("utf-8-sig").splitlines()
    assert text[-2] == "register_result=UNCONFIRMED" and text[-1].startswith("done_at_utc=")
    assert all(real.on_whitelist(x) for x in text)


def test_p6_an_interrupt_at_the_port_check_after_the_answer_is_exit_2(
    world: World, capsys: Any
) -> None:
    def port() -> bool:
        if world.asked.count(real.PROMPT_SEEN):
            raise KeyboardInterrupt
        return False

    code, lines = run(world, capsys, "register", port_check=port)
    assert code == 2 and lines[0] == real.INTERRUPTED_SAFE


@pytest.mark.parametrize("stage", ["prompt", "prechecks", "probe", "backup", "answer"])
def test_p6_every_stage_before_the_start_gives_exit_2(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise KeyboardInterrupt

    if stage == "prompt":
        world.ask = lambda prompt: boom() if prompt == real.PROMPT_CLOSE else ""  # type: ignore[method-assign]
    elif stage == "prechecks":
        monkeypatch.setattr(real, "check_r4", boom)
    elif stage == "probe":
        world.runner.probe = boom  # type: ignore[method-assign]
    elif stage == "backup":
        monkeypatch.setattr(real, "_backup_once", boom)
    else:
        world.ask = lambda prompt: boom() if prompt == real.PROMPT_SEEN else ""  # type: ignore[method-assign]
    code, lines = run(world, capsys, "register", preflight=stage != "prechecks")
    assert code == 2 and lines[0] == real.INTERRUPTED_SAFE


# === point 7 and G: the probe in the preflight; the child's scan lines ===================


def test_p7_the_preflight_runs_the_probe(world: World, capsys: Any) -> None:
    assert run(world, capsys, "preflight")[0] == 0
    assert world.runner.probes == 1


@pytest.mark.parametrize("answer", ["wrong_backend", "none"])
def test_p7_a_probe_that_does_not_match_stops_the_preflight(
    world: World, capsys: Any, answer: str
) -> None:
    world.runner.probe_result = world.root if answer == "wrong_backend" else None
    code, lines = run(world, capsys, "preflight")
    assert (code, lines) == (3, stop_lines("claims_unreachable"))
    assert world.paste_backs() == []  # no preflight result is made without a working probe


def _real_lines(world: World, capsys: Any) -> list[str]:
    assert run(world, capsys, "register")[0] == 0
    return world.paste_backs()[0].read_bytes().decode("utf-8-sig").splitlines()[-18:-2]


@pytest.mark.parametrize("index", [1, 2])
def test_g_the_childs_scan_lines_must_equal_the_preflights(
    tmp_path: Path, capsys: Any, index: int
) -> None:
    good = _real_lines(World(tmp_path / "a"), capsys)
    bad = list(good)
    bad[index] = bad[index].replace("rules_strings 159", "rules_strings 158")
    assert bad[index] != good[index]
    world = World(tmp_path / "b")
    world.runner.override = real.CliResult(0, "\n".join(bad) + "\n", "")
    code, lines = run(world, capsys, "register")
    assert code == 5 and lines[0] == STOP_SENTENCES["output_unverified"]


# === I: the tests the qa review found weak, and the side files ===========================


def test_i_the_full_ledger_object_set_is_exactly_the_expected_one(
    world: World, capsys: Any
) -> None:
    assert run(world, capsys, "register")[0] == 0
    found = {(k, n) for k, n in world.objects() if n.startswith(("forecast_", "plan_"))}
    expected = {key for key in schema.EXPECTED_OBJECTS if key[1].startswith(("forecast_", "plan_"))}
    # triggers and indexes carry other names too; every expected object must be there
    assert set(schema.EXPECTED_OBJECTS) <= {(k, n) for k, n in world.objects()}
    assert {k for k in found if k[0] == "table"} == {k for k in expected if k[0] == "table"}
    assert len({k for k in found if k[0] == "table"}) == 5


def test_i_no_delete_rename_or_replace_is_called_from_the_script(
    world: World, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    callers: list[tuple[str, str]] = []
    for owner, name in (
        (os, "remove"),
        (os, "unlink"),
        (os, "rename"),
        (os, "replace"),
        (os, "rmdir"),
        (shutil, "rmtree"),
        (shutil, "move"),
        (Path, "unlink"),
        (Path, "rename"),
        (Path, "replace"),
        (Path, "rmdir"),
    ):
        original = getattr(owner, name)

        def spy(*a: Any, _n: str = name, _o: Callable[..., Any] = original, **k: Any) -> Any:
            frame = inspect.stack()[1]
            callers.append((_n, frame.filename))
            return _o(*a, **k)

        monkeypatch.setattr(owner, name, spy)
    assert run(world, capsys, "register")[0] == 0
    assert [c for c in callers if Path(c[1]).resolve() == SCRIPT_PATH.resolve()] == []


def test_i_the_two_test_only_flags_are_never_in_a_launcher() -> None:
    app_dir = Path(__file__).resolve().parents[2]
    for name in ("cg2-preflight.bat", "cg2-register.bat"):
        text = (app_dir / name).read_bytes().decode("ascii")
        assert "--backend-dir" not in text and "--home" not in text
    assert "TEST ONLY" in SCRIPT_PATH.read_text(encoding="utf-8")


def test_i_a_wal_beside_the_main_database_leaves_the_logic_alone_and_only_a_shm_may_appear(
    world: World, capsys: Any, tmp_path: Path
) -> None:
    # A database with an uncheckpointed -wal and no -shm: the state after a crash.
    with closing(sqlite3.connect(world.db)) as setup:
        setup.execute("PRAGMA journal_mode = WAL")
    holder = sqlite3.connect(world.db)
    holder.execute("PRAGMA wal_autocheckpoint = 0")
    holder.execute("INSERT INTO app_settings VALUES ('in_wal', 'yes')")
    holder.commit()
    keep = tmp_path / "keep"
    keep.mkdir()
    for suffix in ("", "-wal"):
        shutil.copyfile(f"{world.db}{suffix}", keep / f"stock-desk.db{suffix}")
    holder.close()
    for side in world.data.iterdir():
        side.unlink()
    for suffix in ("", "-wal"):
        shutil.copyfile(keep / f"stock-desk.db{suffix}", f"{world.db}{suffix}")
    assert sorted(p.name for p in world.data.iterdir()) == ["stock-desk.db", "stock-desk.db-wal"]
    reference = tmp_path / "reference"
    reference.mkdir()
    for suffix in ("", "-wal"):
        shutil.copyfile(keep / f"stock-desk.db{suffix}", reference / f"stock-desk.db{suffix}")
    with closing(
        sqlite3.connect(f"{(reference / 'stock-desk.db').as_uri()}?mode=ro", uri=True)
    ) as c:
        before_dump = tuple(c.iterdump())
    assert any("in_wal" in line for line in before_dump)  # the dump sees the -wal rows
    code, _lines = run(world, capsys, "preflight")
    assert code == 0
    names = {p.name for p in world.data.iterdir()}
    # recorded: after read-only reads, the -wal is still there and at most a -shm was added
    assert {"stock-desk.db", "stock-desk.db-wal"} <= names
    assert names <= {"stock-desk.db", "stock-desk.db-wal", "stock-desk.db-shm"}
    assert "stock-desk.db-journal" not in names
    with closing(sqlite3.connect(f"{world.db.as_uri()}?mode=ro", uri=True)) as c:
        assert tuple(c.iterdump()) == before_dump  # the logical state is unchanged
