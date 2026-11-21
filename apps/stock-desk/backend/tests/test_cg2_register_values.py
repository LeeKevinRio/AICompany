"""The constants, the shapes, the boundaries and the launchers of ``scripts/cg2_register.py``.

* M-8: the constants equal what git and the program give today (``git cat-file blob``, the
  published definition and rule sets) and what the CG-2 values tests pin;
* the whitelist: every shape has a sample and unrelated lines are not on it;
* the AST boundaries: hooks first, the forbidden imports, no write SQL, no delete or rename, the
  order backup -> typed answer -> child;
* the two ``.bat`` launchers: syntax and the exact command.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.forecast import definitions
from tests.cg2_register_loader import SCRIPT_PATH
from tests.cg2_register_world import real
from tests.test_cg2_registration_values import (
    C8_RECORD_PATH,
    C8_RECORD_SHA256,
    DEFINITION_LOGIC_SHA256,
    DEFINITION_SHA256,
    PREREG_DOC_PATH,
    PREREG_DOC_SHA256,
    RULESETS,
)

BACKEND = Path(__file__).resolve().parents[1]
PINS = real.REAL_PINS


def _repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(out.stdout.strip())


def _blob(path: str) -> bytes:
    return subprocess.run(
        ["git", "cat-file", "blob", f"HEAD:{path}"],
        cwd=_repo_root(),
        check=True,
        capture_output=True,
    ).stdout


# === M-8: the constants =========================================================================


def test_m8_the_file_constants_equal_the_blobs_at_head() -> None:
    for item in PINS.frozen_files:
        assert hashlib.sha256(_blob(item.path)).hexdigest() == item.sha256, item.role


def test_m8_the_file_constants_equal_the_values_the_cg2_values_tests_pin() -> None:
    assert (PINS.frozen("prereg").path, PINS.frozen("prereg").sha256) == (
        PREREG_DOC_PATH,
        PREREG_DOC_SHA256,
    )
    assert (PINS.frozen("c8").path, PINS.frozen("c8").sha256) == (C8_RECORD_PATH, C8_RECORD_SHA256)
    assert [item.role for item in PINS.frozen_files] == ["prereg", "c8", "h3", "h5"]


def test_m8_the_two_yaml_constants_are_the_registered_rules_hashes() -> None:
    assert PINS.frozen("h3").sha256 == PINS.rules[0].rules_sha256
    assert PINS.frozen("h5").sha256 == PINS.rules[1].rules_sha256
    assert PINS.frozen("h3").path.endswith("/app/outlook/rules/h3.yaml")
    assert PINS.frozen("h5").path.endswith("/app/outlook/rules/h5.yaml")


def test_m8_the_definition_and_rule_constants_equal_the_registered_values() -> None:
    assert PINS.definition_version == "dirdef-v1.0"
    assert PINS.definition_sha256 == DEFINITION_SHA256
    assert PINS.definition_logic_sha256 == DEFINITION_LOGIC_SHA256
    for pin in PINS.rules:
        horizon, rules_sha, logic_sha = RULESETS[pin.version]
        assert (pin.horizon, pin.rules_sha256, pin.rules_logic_sha256) == (
            horizon,
            rules_sha,
            logic_sha,
        )
    assert tuple(pin.version for pin in PINS.rules) == real.RULES_VERSIONS


def test_m8_the_constants_equal_what_the_program_computes_today() -> None:
    # The same check the one-click makes at run time, against the published registries.
    scans = real.check_hashes_and_phrases(PINS)
    assert len(scans) == 2
    entry = definitions.get_ruleset_entry(PINS.rules[0].version)
    assert entry.rules_sha256 == PINS.rules[0].rules_sha256


def test_m8_every_constant_is_a_full_hash_or_a_path() -> None:
    hashes = [
        PINS.definition_sha256,
        PINS.definition_logic_sha256,
        *(i.sha256 for i in PINS.frozen_files),
        *(p.rules_sha256 for p in PINS.rules),
        *(p.rules_logic_sha256 for p in PINS.rules),
    ]
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes) and len(set(hashes)) == 8
    assert re.fullmatch(r"[0-9a-f]{40}", PINS.app_tree_id)


def test_r1_the_app_tree_constant_is_the_app_tree_of_this_checkout() -> None:
    """The equivalent of "no diff in ``app/`` since the CG-2 merge commit" (R-1).

    If this fails after a legitimate change of ``app/``, the constant must be re-pinned (and the
    CG-2 PR re-reviewed); after the registration the one-click is retired, and so is this test.
    """
    tree = subprocess.run(
        ["git", "rev-parse", f"HEAD:{real.APP_REL}"],
        cwd=_repo_root(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert tree == PINS.app_tree_id


def test_the_review_refs_are_the_final_list_in_repo_relative_form_without_spaces() -> None:
    assert PINS.review_refs == (
        "work/reviews/2026-11-15-凍結包第2輪單項確認-風控.md",
        "work/reviews/2026-11-15-事先宣告v0.32套用單項確認-風控.md",
        "work/reviews/2026-11-15-C8決策紀錄檔確認-風控.md",
        "work/reviews/2026-11-17-CG2登記PR-M9核對M2M3M6-風控.md",
        "work/reviews/2026-11-17-CG2登記PR-M9最終審查-qa.md",
        "work/reviews/2026-11-21-CG2登記PR-M9補充核對M2M3M6-風控.md",
        "work/reviews/2026-11-21-CG2登記PR-M9補充最終審查-qa.md",
    )
    for ref in PINS.review_refs:
        assert ref.startswith("work/reviews/") and not re.search(r"\s", ref)
        assert "\\" not in ref and ".." not in ref.split("/") and not ref.startswith("/")
        assert ref.endswith(".md")
    assert len(set(PINS.review_refs)) == len(PINS.review_refs)
    assert " ".join(PINS.review_refs).count(" ") == len(PINS.review_refs) - 1


def test_the_review_refs_all_exist_at_head() -> None:
    """EXPECTED TO FAIL until the coordinator commits the two final records (M-9 風控 and qa).

    Not skipped, not xfail, not weakened: ``check_review_refs`` stops a real run on the same
    condition. The failure lists exactly the paths that are not yet in ``HEAD``.
    """
    root = _repo_root()
    missing = [
        ref
        for ref in PINS.review_refs
        if subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{ref}"], cwd=root, capture_output=True
        ).returncode
        != 0
    ]
    assert missing == []


def test_the_backend_rel_path_is_this_backend() -> None:
    assert (_repo_root() / real.BACKEND_REL).resolve() == BACKEND


# === the whitelist ==============================================================================

H64 = "a" * 64
H40 = "b" * 40
SAMPLES = {
    "version": real.VERSION_LINE,
    "mode": "mode=register",
    "script_sha256_lf": f"script_sha256_lf={H64}",
    "git_head": f"git_head={H40}",
    "git_clean": "git_clean=yes",
    "core_autocrlf": "core_autocrlf=input",
    "head_published": "head_published=yes",
    "app_unchanged": "app_unchanged=yes",
    "code_digest": f"code_digest={H64}",
    "frozen_sha256": f"frozen_c8_sha256={H64}",
    "eol_check": "eol_check=ok",
    "attr_check": "attr_check=ok",
    "definition_sha256": f"definition_sha256={H64}",
    "definition_logic_sha256": f"definition_logic_sha256={H64}",
    "rules_sha256": f"rules_sha256_h5={H64}",
    "rules_logic_sha256": f"rules_logic_sha256_h3={H64}",
    "hashes_pinned": "hashes_pinned=ok",
    "env_db_path": "env_db_path=unset",
    "db_location": "db_location=default",
    "port_8000_listening": "port_8000_listening=no",
    "ledger_objects": "ledger_objects=none",
    "banned_phrase_scan": (
        "banned_phrase_scan_h3=hits 0 rules_strings 159 definition_strings 12 phrases 10"
    ),
    "preflight_result": "preflight_result=PASS",
    "backup_integrity": "backup_integrity=ok",
    "backup_ledger_objects": "backup_ledger_objects=none",
    "backup_sha256": f"backup_sha256={H64}",
    "bootstrap": "bootstrap=ok",
    "registered_rows": "registered_rows=2",
    "frozen_commit": f"frozen_commit={H40}",
    "prereg_doc_sha256": f"prereg_doc_sha256={H64}",
    "registered_at": "registered_at_h5=2026-11-20T13:05:09.123456+00:00",
    "provisional_results_seen": "provisional_results_seen=0",
    "post_commit_check": "post_commit_check=ok",
    "register_result": "register_result=UNCONFIRMED",
    "done_at_utc": "done_at_utc=2026-11-20T13:05:09Z",
}


def test_every_whitelist_shape_has_a_sample() -> None:
    assert set(SAMPLES) == {name for name, _p in real.WHITELIST}


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_whitelist_shape(name: str) -> None:
    patterns = dict(real.WHITELIST)
    assert patterns[name].fullmatch(SAMPLES[name])
    assert [n for n, p in real.WHITELIST if p.fullmatch(SAMPLES[name])] == [name]


@pytest.mark.parametrize(
    "line",
    [
        "",
        "git_head=" + "b" * 39,
        "git_head=" + "B" * 40,
        "git_clean=no",
        "bootstrap=ok ",
        " bootstrap=ok",
        "registered_rows=3",
        "provisional_results_seen=2",
        "backup_path=C:\\Users\\x\\backups\\a.db",
        "claim_id=market|h3|outlook-market-v1.0-h3|dirdef-v1.0|forward",
        "registered_at_h3=2026-11-20T13:05:09Z",
        "banned_phrase_scan_h3=hits 1 rules_strings 1 definition_strings 1 phrases 1",
        "banned_phrase_scan_h4=hits 0 rules_strings 1 definition_strings 1 phrases 1",
        "register_result=DONE\n",
        "traceback (most recent call last):",
    ],
)
def test_lines_off_the_whitelist_are_not_on_it(line: str) -> None:
    assert not real.on_whitelist(line)


def test_the_sixteen_shapes_are_all_on_the_whitelist() -> None:
    samples = {
        "bootstrap=ok",
        "registered_rows=2",
        f"frozen_commit={H40}",
        f"prereg_doc_sha256={H64}",
        "provisional_results_seen=1",
        "post_commit_check=ok",
        "registered_at_h3=2026-11-20T13:05:09.123456+00:00",
        f"rules_sha256_h3={H64}",
        f"rules_logic_sha256_h5={H64}",
        f"definition_sha256={H64}",
        f"definition_logic_sha256={H64}",
        "banned_phrase_scan_h3=hits 0 rules_strings 1 definition_strings 1 phrases 1",
        "banned_phrase_scan_h5=hits 0 rules_strings 1 definition_strings 1 phrases 1",
    }
    assert all(real.on_whitelist(x) for x in samples)
    assert len(real.CLI_OUTPUT_SHAPES) == 16


# === the AST boundaries =========================================================================


def _tree() -> ast.Module:
    return ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _call_names(node: ast.AST) -> list[str]:
    names = []
    for call in ast.walk(node):
        if isinstance(call, ast.Call):
            names.append(ast.unparse(call.func))
    return names


def test_ast_the_hooks_are_the_first_effective_statements() -> None:
    body = _tree().body

    def is_hook(node: ast.stmt) -> bool:
        return (
            isinstance(node, ast.Assign)
            and ast.unparse(node.targets[0])
            in ("sys.excepthook", "threading.excepthook", "sys.unraisablehook")
        ) or (
            isinstance(node, ast.Expr)
            and ast.unparse(node.value)
            in ("warnings.simplefilter('ignore')", "logging.disable(logging.CRITICAL)")
        )

    positions = [i for i, node in enumerate(body) if is_hook(node)]
    assert len(positions) == 5
    first_use = next(
        i
        for i, node in enumerate(body)
        if isinstance(node, ast.ImportFrom)
        and ((node.module or "").split(".")[0] == "app" or node.module == "pathlib")
        or ast.unparse(node).startswith("if (_BACKEND_DIR")
    )
    assert max(positions) < first_use
    before = [n for n in body[: max(positions)] if not is_hook(n)]
    assert [ast.unparse(n) for n in before if isinstance(n, ast.ImportFrom | ast.Import)] == [
        "from __future__ import annotations",
        "import logging",
        "import sys",
        "import threading",
        "import warnings",
    ]
    assert [n.name for n in before if isinstance(n, ast.FunctionDef)] == ["_fixed_hook"]


FORBIDDEN_MODULES = (
    "app.forecast.claims",
    "app.forecast.store",
    "app.forecast.schema",
    "app.forecast.recorder",
    "app.forecast.report",
    "app.services",
    "app.data.cache",
    "app.data.service",
    "app.data.providers",
    "tests",
)


def test_ast_the_script_imports_none_of_the_registration_or_store_modules() -> None:
    imported: set[str] = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
    for forbidden in FORBIDDEN_MODULES:
        assert not any(m == forbidden or m.startswith(forbidden + ".") for m in imported), forbidden
    assert {"app.forecast.canonical", "app.forecast.definitions"} <= imported


def test_runtime_the_isolated_import_loads_none_of_the_forbidden_modules() -> None:
    driver = (
        "import runpy, sys\n"
        f"runpy.run_path({str(SCRIPT_PATH)!r}, run_name='loaded')\n"
        f"bad = [m for m in {list(FORBIDDEN_MODULES[:-1])!r} if m in sys.modules]\n"
        "print(bad)\n"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", driver], capture_output=True, text=True, timeout=120
    )
    assert done.stderr == "" and done.stdout.strip() == "[]", done.stdout


def test_ast_the_script_has_no_delete_rename_or_replace() -> None:
    banned = {
        "unlink",
        "remove",
        "rename",
        "replace",
        "rmdir",
        "rmtree",
        "move",
        "utime",
        "chmod",
        "truncate",
        "touch",
        "write_bytes",
        "write_text",
    }
    for name in _call_names(_tree()):
        tail = name.rsplit(".", 1)[-1]
        assert tail not in banned, name


def test_ast_every_statement_the_script_executes_on_a_connection_is_read_only() -> None:
    allowed = ("PRAGMA query_only=ON", "PRAGMA integrity_check")
    seen = []
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(".execute"):
            first = node.args[0]
            if isinstance(first, ast.Constant):
                assert first.value in allowed, first.value
            else:
                assert ast.unparse(first) == "_LEDGER_SQL"
            seen.append(ast.unparse(first))
    assert len(seen) == 3
    assert real._LEDGER_SQL.startswith("SELECT ")
    forbidden = ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "VACUUM", "REPLACE")
    assert not any(word in real._LEDGER_SQL.upper() for word in forbidden)


def test_ast_the_only_connections_are_read_only_or_the_backup_target() -> None:
    forms = [
        ast.unparse(node.args[0])
        for node in ast.walk(_tree())
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "sqlite3.connect"
    ]
    assert sorted(forms) == sorted(
        [
            "main_db_uri(db)",  # R-4
            "main_db_uri(db)",  # the backup's source
            "str(target)",  # the new backup file
            "f'{target.as_uri()}?mode=ro&immutable=1'",  # the read-back of the backup
        ]
    )
    uri_source = ast.unparse(_functions(_tree())["main_db_uri"])
    assert "mode=ro" in uri_source and "mode=rw" not in uri_source


def test_ast_the_main_database_is_never_opened_hashed_or_read_by_bytes() -> None:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Call) and ast.unparse(node.func) in (
            "open",
            "sha256_file",
            "Path.read_bytes",
        ):
            assert "db" not in [ast.unparse(a) for a in node.args], ast.unparse(node)
    flow = _functions(_tree())
    for name in ("check_r4", "_backup_once", "check_r3"):
        calls = _call_names(flow[name])
        assert "open" in calls if name == "_backup_once" else "open" not in calls
    # make_backup opens only the new backup target ("xb"), never the source
    opens = [
        n
        for n in ast.walk(flow["_backup_once"])
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "open"
    ]
    assert [ast.unparse(o.args[0]) for o in opens] == ["target"] and ast.unparse(
        opens[0].args[1]
    ) == "'xb'"


def test_ast_the_order_probe_backup_typed_answer_child() -> None:
    """RC-181 (structure): the backup is made before the question and before the child."""
    flow = _functions(_tree())["flow"]
    calls = [
        (node.lineno, ast.unparse(node.func))
        for node in ast.walk(flow)
        if isinstance(node, ast.Call)
    ]
    first: dict[str, int] = {}
    for line, name in sorted(calls):
        first.setdefault(name, line)
    ask_lines = [line for line, name in sorted(calls) if name == "seams.ask"]
    assert len(ask_lines) == 2  # the "close the windows" prompt, then the typed answer
    order = [
        ask_lines[0],
        first["prechecks"],
        first["check_preflight_binding"],
        first["seams.claims.probe"],
        first["make_backup"],
        ask_lines[1],
        first["seams.port_check"],
        first["seams.claims.start"],
        first["seams.claims.finish"],
    ]
    assert order == sorted(order) and len(set(order)) == len(order)
    assert [n for _l, n in sorted(calls) if n == "seams.claims.start"] == ["seams.claims.start"]


def test_ast_the_typed_answer_has_no_default_and_no_other_source() -> None:
    flow = _functions(_tree())["flow"]
    text = ast.unparse(flow)
    assert "typed = seams.ask(PROMPT_SEEN)" in text
    assert "typed not in ('0', '1')" in text
    assert "int(typed)" not in text and "typed or" not in text and "typed ==" not in text
    assert text.count("PROMPT_SEEN") == 1  # one question, never repeated
    assert not any(isinstance(n, ast.While | ast.For) for n in ast.walk(flow) if n is not flow)
    for env_name in ("environ", "getenv"):
        assert env_name not in text


def test_ast_the_bootstrap_arguments_hold_no_database_path_and_no_replacement() -> None:
    func = _functions(_tree())["bootstrap_args"]
    strings = [
        n.value for n in ast.walk(func) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    strings = [x for x in strings if x != ast.get_docstring(func)]
    assert "--db" not in strings and "--replaces-claim-id" not in strings
    assert "--frozen-commit" in strings and "head" in ast.unparse(func)


def test_ast_the_child_is_the_same_interpreter_with_isolated_utf8() -> None:
    cls = next(
        n for n in ast.walk(_tree()) if isinstance(n, ast.ClassDef) and n.name == "SubprocessClaims"
    )
    argv = ast.unparse(
        next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_argv")
    )
    assert "sys.executable, '-I', '-X', 'utf8'" in argv
    text = ast.unparse(cls)
    assert "'-m', 'app.forecast.claims'" in text and "cwd=self.backend_dir" in text
    assert "capture_output=True" in text  # the child's output is never inherited


def test_the_tests_never_point_a_path_at_the_real_backend_data_folder() -> None:
    # The real backend folder is used only for the probe and ``--help`` of the child (no database).
    pattern = re.compile(r"BACKEND\s*/\s*[\"']data[\"']|BACKEND\.joinpath\([\"']data")
    for name in (
        "test_cg2_register_flow.py",
        "test_cg2_register_values.py",
        "cg2_register_world.py",
    ):
        text = (BACKEND / "tests" / name).read_text(encoding="utf-8")
        assert not pattern.search(text), name
    world_text = (BACKEND / "tests" / "cg2_register_world.py").read_text(encoding="utf-8")
    assert "__file__" not in world_text  # every path of the world derives from ``tmp_path``


# === the launchers ==============================================================================

APP_DIR = BACKEND.parent
BATS = {
    "preflight": APP_DIR / "cg2-preflight.bat",
    "register": APP_DIR / "cg2-register.bat",
}


@pytest.mark.parametrize("mode", sorted(BATS))
def test_the_bat_is_a_crlf_launcher_that_clears_uv_env_file_first(mode: str) -> None:
    bat = BATS[mode]
    command = rf"uv run --no-sync python -I -X utf8 scripts\cg2_register.py {mode}"
    raw = bat.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") and b"\r\r" not in raw
    lines = raw.decode("ascii").split("\r\n")
    assert lines[0] == "@echo off"
    assert 'set "UV_ENV_FILE="' in lines
    assert lines.index('set "UV_ENV_FILE="') < lines.index(command)
    assert lines.count(command) == 1
    assert lines.index(command) < max(i for i, x in enumerate(lines) if x == "pause")
    assert 'cd /d "%BACKEND_DIR%"' in lines
    assert not any("STOCK_DESK" in x or ".env" in x for x in lines if not x.startswith("REM"))


@pytest.mark.parametrize("mode", sorted(BATS))
def test_the_bat_has_no_non_cmd_syntax_and_only_r2_launcher_lines_besides_its_own(
    mode: str,
) -> None:
    lines = BATS[mode].read_bytes().decode("ascii").split("\r\n")
    commands = [x for x in lines if not x.startswith("REM")]
    assert not any("/dev/null" in x for x in commands)
    assert not any(token in x for x in commands for token in ("&&", "||", "2>&1", "$(", "`"))
    assert "where uv >nul 2>nul" in lines
    r2 = (APP_DIR / "r2-probe.bat").read_bytes().decode("ascii").split("\r\n")
    own = {
        f"title stock-desk cg2-{mode}",
        'set "UV_ENV_FILE="',
        rf"uv run --no-sync python -I -X utf8 scripts\cg2_register.py {mode}",
        "  echo Tell the coordinator.",  # RC-198: replaces the r2 launcher's "run again" line
        "",
    }
    r2_commands = {x for x in r2 if not x.startswith("REM")}
    assert [x for x in commands if x not in r2_commands and x not in own] == []


def test_the_two_bats_differ_only_in_the_mode_title_and_comments() -> None:
    def commands(mode: str) -> list[str]:
        lines = BATS[mode].read_bytes().decode("ascii").split("\r\n")
        return [
            x.replace(f"cg2-{mode}", "cg2-X").replace(
                f"cg2_register.py {mode}", "cg2_register.py X"
            )
            for x in lines
            if not x.startswith("REM")
        ]

    assert commands("preflight") == commands("register")


def test_the_bats_name_only_this_script_and_no_other_tool() -> None:
    for bat in BATS.values():
        text = bat.read_bytes().decode("ascii")
        assert "pipeline_acceptance_real" not in text and "claims" not in text
        assert "git " not in text and "bootstrap" not in text


def test_the_bats_are_tracked_as_crlf() -> None:
    out = subprocess.run(
        ["git", "check-attr", "eol", "--", *[str(p) for p in BATS.values()]],
        cwd=_repo_root(),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert out.count("eol: crlf") == 2


# === misc ========================================================================================


def test_the_work_folder_is_named_apart_from_the_acceptance() -> None:
    acceptance: Any = __import__(
        "tests.pipeline_real_loader", fromlist=["load_script"]
    ).load_script()
    assert real.WORK_ROOT_NAME != acceptance.WORK_ROOT_NAME
    assert real.BACKUP_DIR_NAME == "backups" and real.PASTE_DIR_NAME == "paste-backs"


def test_the_acceptance_script_is_unchanged_in_its_interface_by_this_script() -> None:
    # This script copies; it never imports the acceptance script.
    text = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "import pipeline_acceptance_real" not in text and "from scripts" not in text


# === the CEO instruction (RC-164, RC-182, RC-185 to RC-211) ======================================


def _verifier() -> dict[str, Any]:
    import runpy

    return runpy.run_path(str(BACKEND / "scripts" / "verify_cg2_instruction.py"), run_name="v")


def _inputs(v: dict[str, Any]) -> dict[str, Any]:
    ns = {
        name: getattr(real, name)
        for name in (
            "STOPS",
            "NEW_STOP_KEYS",
            "PROMPT_SEEN",
            "_TELL",
            "backup_file_name",
            "verify_file_name",
        )
    }
    return {
        "rc182_report": v["RC182_REPORT"].read_text(encoding="utf-8"),
        "block5_report": v["BLOCK5_REPORT"].read_text(encoding="utf-8"),
        "old_report": v["RC185_REPORT"].read_text(encoding="utf-8"),
        "new_report": v["RC199_REPORT"].read_text(encoding="utf-8"),
        "final_report": v["RC213_REPORT"].read_text(encoding="utf-8"),
        "sentences": v["script_sentences"](
            {**ns, **{k: getattr(real, k) for k in _SENTENCE_NAMES}}
        ),
        "script": ns,
    }


_SENTENCE_NAMES = (
    "INTERRUPTED_SAFE",
    "INTERRUPTED_LATE",
    "UNEXPECTED_SAFE",
    "UNEXPECTED_LATE",
    "HOOK_SENTENCE",
    "PROMPT_CLOSE",
)


def test_the_ceo_instruction_quotes_every_risk_text_verbatim_and_lists_every_sentence() -> None:
    v = _verifier()
    results = v["check"](v["DOC"].read_text(encoding="utf-8"), **_inputs(v))
    assert [text for ok, text in results if not ok] == []
    assert len(results) >= 30


def test_the_verifier_has_teeth() -> None:
    v = _verifier()
    doc = v["DOC"].read_text(encoding="utf-8")
    inputs = _inputs(v)
    rc182 = v["extract_rc182"](inputs["rc182_report"])
    rc207 = v["block_after"](inputs["new_report"], "**RC-207")
    rc213 = v["block_after"](inputs["final_report"], "**RC-213")
    rc214 = v["block_after"](inputs["final_report"], "**RC-214")
    rc215 = v["block_after"](inputs["final_report"], "**RC-215")
    rc216 = v["block_after"](inputs["final_report"], "**RC-216")
    row = v["new_stop_row_lines"](inputs["new_report"])[0]
    for tampered in (
        doc.replace(rc182, rc182.replace("不會", "可能不會")),  # a softened quote
        doc.replace(rc182, rc182[:-5]),  # a cut quote
        doc.replace(rc207, rc207.replace("不要再執行登記檔", "不要執行登記檔")),
        doc.replace(rc213, rc213.replace("-verify.db", "-second.db")),  # a file name that differs
        doc.replace(rc214, rc214.replace("不要自己重跑", "可以重跑")),
        doc.replace(rc215, ""),  # the added line is missing
        doc.replace(rc216, "待風控單項確認後才交給 CEO"),  # the old status
        doc.replace(rc213, ""),  # the replaced block is gone
        doc.replace(row, row.replace("Nothing was registered", "All good")),
        doc + "\n這一步保證不會出事。\n",  # a guarantee word in own text
        doc.replace("風控單項確認通過", "待風控定稿"),
        doc.replace("不要自己修改任何設定或檔案。", "", 1),  # a row without the warning
    ):
        results = v["check"](tampered, **inputs)
        assert any(not ok for ok, _t in results)
    extra = [*inputs["sentences"], "STOP: x"]
    assert any(not ok for ok, _t in v["check"](doc, **{**inputs, "sentences": extra}))
    wrong = {**inputs["script"], "PROMPT_SEEN": "Type 0 or 1: "}
    assert any(not ok for ok, _t in v["check"](doc, **{**inputs, "script": wrong}))


def test_the_extraction_rules_fail_closed() -> None:
    v = _verifier()
    with pytest.raises(ValueError):
        v["extract_rc182"]("no bullet here\n")
    with pytest.raises(ValueError):
        v["extract_block5"]("**區塊五：登記時「是否看過暫定對照」**\n\nnot a quote\n")
    with pytest.raises(ValueError):
        v["block_after"]("**RC-999 x**\n\n**RC-998 y**\n> quote\n", "**RC-999")
    with pytest.raises(ValueError):
        v["block_after"]("nothing\n", "**RC-999")
    two = v["RC182_REPORT"].read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        v["extract_rc182"](two + "\n" + two)


def test_the_instruction_names_the_backup_place_both_launchers_and_the_applied_status() -> None:
    doc = _verifier()["DOC"].read_text(encoding="utf-8")
    for needle in (
        "cg2-preflight.bat",
        "cg2-register.bat",
        r"stock-desk-cg2-registration\backups",
        real.backup_file_name("<時間戳>"),
        real.verify_file_name("<時間戳>"),
        "還原方式（只描述；請不要自己動手）",
        "已套用風控 RC-185～RC-216，風控單項確認通過",
        "不要再執行登記檔",
    ):
        assert needle in doc, needle
    assert "待風控定稿" not in doc
    assert real.WORK_ROOT_NAME in doc and real.BACKUP_DIR_NAME in doc


def test_the_instruction_has_no_code_explanation_for_the_refusal_reasons() -> None:
    doc = _verifier()["DOC"].read_text(encoding="utf-8")
    for code in real.REFUSAL_CODES:
        assert f"refusal_reason={code}" not in doc
    assert doc.count("refusal_reason=") >= 1  # only the generic RC-205 sentence names the line
