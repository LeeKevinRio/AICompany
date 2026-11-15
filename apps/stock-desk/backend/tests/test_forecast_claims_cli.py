"""``python -m app.forecast.claims register`` (ADR-0030 D-1 points 2-3, D-2 point 5, D-6 CG-2).

Every ledger is a ``tmp_path`` file and every clock an injected ``FakeClock``;
the rule sets are the landed h3 / h5 files and the definition the G7 stand-in,
published in ``app.forecast.definitions`` for each test only (the production
registries stay empty, K-11). The "production" database of the path tests is a
``tmp_path`` stand-in passed as ``backend_dir`` / ``cwd`` / ``env``: no test
opens, stats or names the service database.

Covered: a registration with every field; the registered claims pass the
recorder's CG-2 check; each required argument missing and each required value
blank or empty; ``replace_reason`` exactly with ``replaces_claim_id``; the three
replacement counter-examples of supplement 3 (revised) point 6 (another
horizon, a second replacement, a claim registered later); the registry is
append-only (a second registration, ``INSERT OR REPLACE``, UPDATE, DELETE); the
CG-2 banned phrase scan (NFKC, whitespace removed; FL-78 (m): seam
``definitions._read_rules_bytes``); production paths refused; the module runs
as ``__main__`` (``--help``, which exits before any path check) and a fresh
process refuses with the empty registries against stand-in paths (qa batch 4
follow-up 3: no subprocess looks at the real ``<backend>/data/``); claims and
the store import in either order.
"""

from __future__ import annotations

import ast
import hashlib
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from app.dirdef.definition import DirectionDefinition, definition_logic_sha256, definition_sha256
from app.dirdef.hashing import canonical_json
from app.dirdef.registry import PublishedRuleset
from app.dirdef.rules import rules_logic_sha256
from app.forecast import claims, definitions
from app.forecast.canonical import APP_ROOT, canonical_timestamp
from app.forecast.recorder import check_recording_claims
from app.forecast.store import ForecastStore
from tests.dirdef_helpers import DIRDEF_V1_0_G7
from tests.forecast_ledger_helpers import FakeClock, file_ledger, publish_definition, taipei
from tests.outlook_helpers import definition, rule_bytes, ruleset

H3 = "outlook-market-v1.0-h3"
H5 = "outlook-market-v1.0-h5"
H3_V11 = "outlook-market-v1.1-h3"
H3_V12 = "outlook-market-v1.2-h3"
H5_V11 = "outlook-market-v1.1-h5"
DEFINITION = "dirdef-v1.0"
PREREG = b"# pre-registration v0.32 (synthetic fixture)\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _claim_key(rules_version: str) -> str:
    horizon = 5 if rules_version.endswith("-h5") else 3
    return f"market|h{horizon}|{rules_version}|{DEFINITION}|forward"


def publish(monkeypatch: pytest.MonkeyPatch, *, defn: DirectionDefinition | None = None) -> None:
    publish_definition(monkeypatch, defn or definition())
    h3 = PublishedRuleset(horizon=3, rules_sha256=_sha(rule_bytes(3)))
    h5 = PublishedRuleset(horizon=5, rules_sha256=_sha(rule_bytes(5)))
    entries = {H3: h3, H5: h5, H3_V11: h3, H3_V12: h3, H5_V11: h5}
    monkeypatch.setattr(definitions, "PUBLISHED_RULESETS", MappingProxyType(entries))
    monkeypatch.setattr(definitions, "_RULESET_CACHE", {})


class Cli:
    """A ``tmp_path`` ledger, a stand-in backend folder and the published fixtures."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.db = file_ledger(root)
        self.clock = FakeClock(taipei(2026, 11, 1, 9))
        self.backend = root / "backend"
        (self.backend / "data").mkdir(parents=True)
        self.prereg = root / "prereg-v0.32.md"
        self.prereg.write_bytes(PREREG)
        publish(monkeypatch)

    def argv(self, rules_version: str | None = H3, **overrides: str | None) -> list[str]:
        values: dict[str, str | None] = {
            "--db": str(self.db),
            "--rules-version": rules_version,
            "--definition-version": DEFINITION,
            "--frozen-commit": "0123456789abcdef0123456789abcdef01234567",
            "--prereg-doc": str(self.prereg),
            "--review-refs": "work/reviews/risk.md work/reviews/qa.md",
            "--provisional-results-seen": "0",
        }
        values.update({f"--{k.replace('_', '-')}": v for k, v in overrides.items()})
        argv = ["register"]
        for flag, value in values.items():
            if value is not None:
                argv += [flag, value]
        return argv

    def main(self, argv: list[str], *, env: dict[str, str] | None = None) -> int:
        self.clock.advance(seconds=1)
        return claims.main(
            argv, env=env or {}, cwd=self.root, backend_dir=self.backend, clock=self.clock
        )

    def register(self, rules_version: str | None = H3, **overrides: str | None) -> int:
        return self.main(self.argv(rules_version, **overrides))

    def rows(self) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.db)) as conn:
            conn.row_factory = sqlite3.Row
            return [
                dict(r)
                for r in conn.execute("SELECT * FROM forecast_claim_registry ORDER BY rowid")
            ]


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Cli:
    return Cli(tmp_path, monkeypatch)


# --- a registration ------------------------------------------------------------------------------


def test_register_writes_one_row_with_every_field(
    cli: Cli, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.register(provisional_results_seen="1") == claims.EXIT_OK
    (row,) = cli.rows()
    assert row["claim_id"] == _claim_key(H3)
    assert (row["scope_kind"], row["scope_key"], row["horizon"], row["kind"]) == (
        "market",
        "TAIEX",
        3,
        "forward",
    )
    assert row["rules_bytes"] == rule_bytes(3)
    assert row["rules_sha256"] == _sha(rule_bytes(3))
    assert row["rules_logic_sha256"] == rules_logic_sha256(ruleset(3))
    assert row["definition_json"] == canonical_json(definition().model_dump(mode="json"))
    assert row["frozen_commit"] == "0123456789abcdef0123456789abcdef01234567"
    assert (row["prereg_doc_path"], row["prereg_doc_blob"]) == (str(cli.prereg), PREREG)
    assert row["review_refs"] == "work/reviews/risk.md work/reviews/qa.md"
    assert (row["replaces_claim_id"], row["replace_reason"]) == (None, None)
    assert row["provisional_results_seen"] == 1
    assert row["registered_at"] == canonical_timestamp(cli.clock.now)
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("banned phrase scan (NFKC, whitespace and zero-width removed): rules ")
    assert out[0].endswith(", 10 phrases, hits 0")
    assert f"registered claim_id={_claim_key(H3)}" in out
    assert f"registered_at={row['registered_at']}" in out


def test_the_registered_claims_pass_the_recorders_cg2_check(cli: Cli) -> None:
    assert cli.register(H3) == claims.EXIT_OK
    assert cli.register(H5) == claims.EXIT_OK
    store = ForecastStore(cli.db, clock=cli.clock)
    checked = check_recording_claims(store)
    assert [(c.claim.claim_id, c.claim.horizon) for c in checked] == [
        (_claim_key(H3), 3),
        (_claim_key(H5), 5),
    ]
    assert [c.ruleset for c in checked] == [ruleset(3), ruleset(5)]
    # A replacement registered through the CLI keeps the gate open.
    assert (
        cli.register(H3_V11, replaces_claim_id=_claim_key(H3), replace_reason="text change")
        == claims.EXIT_OK
    )
    assert [c.claim.claim_id for c in check_recording_claims(store)] == [
        _claim_key(H3_V11),
        _claim_key(H5),
    ]


# --- required fields ---------------------------------------------------------------------------

REQUIRED = (
    "db",
    "rules_version",
    "definition_version",
    "frozen_commit",
    "prereg_doc",
    "review_refs",
    "provisional_results_seen",
)


@pytest.mark.parametrize("field", REQUIRED)
def test_each_required_argument_is_required(cli: Cli, field: str) -> None:
    argv = cli.argv(**{field: None})
    with pytest.raises(SystemExit) as stopped:
        cli.main(argv)
    assert stopped.value.code == 2
    assert cli.rows() == []


def test_provisional_results_seen_takes_zero_or_one_only(cli: Cli) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.register(provisional_results_seen="yes")
    assert stopped.value.code == 2
    assert cli.rows() == []


@pytest.mark.parametrize(
    "case",
    [
        "frozen-commit-blank",
        "review-refs-blank",
        "prereg-doc-empty",
        "prereg-doc-missing",
        "rules-bytes-empty",
        "definition-unpublished",
        "rules-unpublished",
    ],
)
def test_a_blank_or_empty_required_value_is_refused(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    overrides: dict[str, str | None] = {}
    if case == "frozen-commit-blank":
        overrides["frozen_commit"] = "  "
    elif case == "review-refs-blank":
        overrides["review_refs"] = ""
    elif case == "prereg-doc-empty":
        empty = cli.root / "empty.md"
        empty.write_bytes(b"")
        overrides["prereg_doc"] = str(empty)
    elif case == "prereg-doc-missing":
        overrides["prereg_doc"] = str(cli.root / "missing.md")
    elif case == "rules-bytes-empty":
        monkeypatch.setattr(definitions, "_read_rules_bytes", lambda horizon: b"")
    elif case == "definition-unpublished":
        overrides["definition_version"] = "dirdef-v9.9"
    else:
        overrides["rules_version"] = "outlook-market-v9.9-h3"
    assert cli.register(**overrides) == claims.EXIT_REFUSED
    assert cli.rows() == []
    assert capsys.readouterr().err.startswith("refused: ")


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"replaces_claim_id": _claim_key(H3)}, id="replacing-without-a-reason"),
        pytest.param({"replace_reason": "why"}, id="a-reason-without-replacing"),
        pytest.param(
            {"replaces_claim_id": _claim_key(H3), "replace_reason": " "}, id="a-blank-reason"
        ),
    ],
)
def test_replace_reason_is_required_exactly_when_replacing(
    cli: Cli, overrides: dict[str, str]
) -> None:
    assert cli.register(H3) == claims.EXIT_OK
    before = cli.rows()
    assert cli.register(H3_V11, **overrides) == claims.EXIT_REFUSED
    assert cli.rows() == before


# --- supplement 3 (revised) point 6: the three counter-examples (f1) -----------------------


def test_f1_a_replacement_across_horizons_is_refused(
    cli: Cli, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.register(H3) == claims.EXIT_OK
    assert cli.register(H5) == claims.EXIT_OK
    before = cli.rows()
    # The old h3 claim replaced by a new h5 claim.
    code = cli.register(H5_V11, replaces_claim_id=_claim_key(H3), replace_reason="x")
    assert code == claims.EXIT_REFUSED
    assert "keeps the scope and horizon" in capsys.readouterr().err
    assert cli.rows() == before


def test_f1_a_second_replacement_of_one_claim_is_refused(
    cli: Cli, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.register(H3) == claims.EXIT_OK
    assert cli.register(H3_V11, replaces_claim_id=_claim_key(H3), replace_reason="x") == 0
    before = cli.rows()
    code = cli.register(H3_V12, replaces_claim_id=_claim_key(H3), replace_reason="x")
    assert code == claims.EXIT_REFUSED
    assert "replaced more than once" in capsys.readouterr().err
    assert cli.rows() == before


def test_f1_naming_a_claim_registered_later_is_refused(
    cli: Cli, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.register(H3) == claims.EXIT_OK
    before = cli.rows()
    # H3_V12 is registered after this attempt: at registration it names no earlier claim.
    code = cli.register(H3_V11, replaces_claim_id=_claim_key(H3_V12), replace_reason="x")
    assert code == claims.EXIT_REFUSED
    assert "not a registered forward claim" in capsys.readouterr().err
    assert cli.rows() == before
    assert cli.register(H3_V12, replaces_claim_id=_claim_key(H3), replace_reason="x") == 0
    # Nor may it name itself.
    code = cli.register(H3_V11, replaces_claim_id=_claim_key(H3_V11), replace_reason="x")
    assert code == claims.EXIT_REFUSED


# --- append-only ---------------------------------------------------------------------------------


def test_a_second_registration_of_one_claim_is_refused(
    cli: Cli, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.register(H3) == claims.EXIT_OK
    before = cli.rows()
    assert cli.register(H3, review_refs="another review") == claims.EXIT_REFUSED
    assert "append-only" in capsys.readouterr().err
    assert cli.rows() == before


@pytest.mark.parametrize(
    "sql",
    [
        pytest.param("REPLACE", id="insert-or-replace"),
        pytest.param("UPDATE forecast_claim_registry SET review_refs = 'x'", id="update"),
        pytest.param("DELETE FROM forecast_claim_registry", id="delete"),
    ],
)
def test_the_registered_row_cannot_be_rewritten(cli: Cli, sql: str) -> None:
    assert cli.register(H3) == claims.EXIT_OK
    (before,) = cli.rows()
    with closing(sqlite3.connect(cli.db, isolation_level=None)) as conn:
        if sql == "REPLACE":
            row = {**before, "review_refs": "rewritten"}
            names = ", ".join(row)
            marks = ", ".join("?" for _ in row)
            statement = f"INSERT OR REPLACE INTO forecast_claim_registry ({names}) VALUES ({marks})"
            params: tuple[object, ...] = tuple(row.values())
        else:
            statement, params = sql, ()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(statement, params)
    assert cli.rows() == [before]


# --- CG-2: banned phrase scan before registering (D-6; FL-78 (m)) --------------------------


#: qa batch 4 follow-up 4: the six zero-width characters the scan removes.
ZERO_WIDTH_FORMS = [
    pytest.param("保​證", id="U+200B"),
    pytest.param("必‌漲", id="U+200C"),
    pytest.param("必‍賺", id="U+200D"),
    pytest.param("穩⁠賠", id="U+2060"),
    pytest.param("包﻿賺", id="U+FEFF"),
    pytest.param("零­風險", id="U+00AD"),
    pytest.param("一​定­會", id="two-kinds"),
    pytest.param("無 ​風險", id="space-and-zero-width"),
    pytest.param("必 跌", id="no-break-space"),
]


def _poisoned_rules(monkeypatch: pytest.MonkeyPatch, phrase_form: str) -> None:
    """h3 bytes with ``phrase_form`` in an explanation, published under H3 (seam: the reader)."""
    text = rule_bytes(3).decode("utf-8")
    marker = "趨勢票計為偏多一票。"
    assert text.count(marker) == 1
    poisoned = text.replace(marker, f"趨勢票計為偏多一票，{phrase_form}。").encode("utf-8")
    monkeypatch.setattr(definitions, "_read_rules_bytes", lambda horizon: poisoned)
    entries = dict(vars(definitions)["PUBLISHED_RULESETS"])
    entries[H3] = PublishedRuleset(horizon=3, rules_sha256=_sha(poisoned))
    monkeypatch.setattr(definitions, "PUBLISHED_RULESETS", MappingProxyType(entries))
    monkeypatch.setattr(definitions, "_RULESET_CACHE", {})


def test_fl78m_a_rule_set_with_a_banned_phrase_cannot_be_registered(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _poisoned_rules(monkeypatch, "保證")  # the loader itself refuses it
    assert cli.register(H3) == claims.EXIT_REFUSED
    assert "PublishedVersionRejectedError" in capsys.readouterr().err
    assert cli.rows() == []


@pytest.mark.parametrize("form", ["保 證", "必　漲", "零 風險"])
def test_a_spaced_phrase_in_the_rules_is_a_scan_hit(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], form: str
) -> None:
    # The loader's plain comparison lets these through; the CG-2 scan does not.
    _poisoned_rules(monkeypatch, form)
    assert definitions.get_ruleset(H3) is not None
    assert cli.register(H3) == claims.EXIT_REFUSED
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert lines[0].endswith("hits 1")
    assert lines[1].startswith("  hit rules: ")
    assert "banned phrase" in captured.err
    assert cli.rows() == []


@pytest.mark.parametrize("form", ZERO_WIDTH_FORMS)
def test_a_zero_width_split_phrase_in_the_rules_is_a_scan_hit(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], form: str
) -> None:
    _poisoned_rules(monkeypatch, form)
    assert definitions.get_ruleset(H3) is not None  # the loader's plain comparison misses it
    assert cli.register(H3) == claims.EXIT_REFUSED
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("hits 1") and lines[1].startswith("  hit rules: ")
    assert cli.rows() == []


@pytest.mark.parametrize("form", ZERO_WIDTH_FORMS)
def test_a_zero_width_split_phrase_in_the_definition_is_a_scan_hit(form: str) -> None:
    poisoned = DirectionDefinition.model_validate(
        {**DIRDEF_V1_0_G7, "description": f"合成定義，{form}（測試）"}
    )
    scan = definitions.registration_phrase_scan(ruleset(3), poisoned)
    assert len(scan.hits) == 1 and scan.hits[0].startswith("definition: ")


def test_squeeze_removes_whitespace_and_exactly_the_zero_width_characters() -> None:
    assert definitions.ZERO_WIDTH == frozenset({"​", "‌", "‍", "⁠", "﻿", "­"})
    every = "".join(sorted(definitions.ZERO_WIDTH))
    assert definitions.squeeze(f"保{every} 　 \t證") == "保證"
    # NFKC still applies (full-width letters), other characters stay.
    assert definitions.squeeze("ＡＢ​c-d") == "ABc-d"


@pytest.mark.parametrize("horizon", [3, 5])
def test_the_zero_width_removal_changes_no_registered_hash(horizon: int) -> None:
    # Only the comparison form changes: the landed bytes, their two hashes and the
    # stand-in definition hashes are the pinned ones, and the landed files scan clean.
    pinned = {
        3: (
            "f4f366a5d5e66fd7fd49c916f5bb31401e84c2f23b3bb7a534f55be406fb3443",
            "ddd3c51a1cb9b30a3e957a5a98888ca48916deb35f66027f2f49e7b824f34484",
        ),
        5: (
            "0a385de3e2f4118bc1e7c2c5dd1a667ce0a9067399ccd1b6e7c4dbab19d5707c",
            "e5310b8e6ce14525e81616eedd4368d45a682cb8a4647129ea5617a41cedf1bb",
        ),
    }
    assert (_sha(rule_bytes(horizon)), rules_logic_sha256(ruleset(horizon))) == pinned[horizon]
    assert (definition_sha256(definition()), definition_logic_sha256(definition())) == (
        "a0d0a34d5fad3593b902c755b3c060497901acc2ba923c71fef5b9ebe89bd6e2",
        "4cc1fe80054a017f47030805a486ad81e1bda249d730c7c1f6bd2c73c01d1afa",
    )
    assert definitions.registration_phrase_scan(ruleset(horizon), definition()).hits == ()


def test_a_spaced_phrase_in_the_definition_is_a_scan_hit(
    cli: Cli, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    poisoned = DirectionDefinition.model_validate(
        {**DIRDEF_V1_0_G7, "description": "合成定義，穩 賺（測試）"}
    )
    publish(monkeypatch, defn=poisoned)
    assert definitions.get_definition(DEFINITION) is poisoned  # the plain scan lets it through
    assert cli.register(H3) == claims.EXIT_REFUSED
    out = capsys.readouterr().out.splitlines()
    assert out[0].endswith("hits 1") and out[1] == "  hit definition: 穩賺"
    assert cli.rows() == []


def test_the_landed_files_and_the_stand_in_definition_scan_clean() -> None:
    for horizon in (3, 5):
        scan = definitions.registration_phrase_scan(ruleset(horizon), definition())
        assert scan.hits == ()
        assert scan.rules_strings > 50 and scan.definition_strings > 0 and scan.phrases == 10


def test_the_scan_refuses_without_phrases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(definitions, "BANNED_PHRASES", ())
    with pytest.raises(definitions.PublishedVersionRejectedError, match="no banned phrases"):
        definitions.registration_phrase_scan(ruleset(3), definition())


def test_the_rule_bytes_must_still_match_their_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    publish(monkeypatch)
    assert definitions.get_rules_bytes(H3) == rule_bytes(3)
    definitions.get_ruleset(H3)  # cached
    monkeypatch.setattr(definitions, "_read_rules_bytes", lambda horizon: rule_bytes(3) + b"#\n")
    with pytest.raises(definitions.PublishedVersionRejectedError, match="no longer matches"):
        definitions.get_rules_bytes(H3)

    def unreadable(horizon: int) -> bytes:
        raise OSError("gone")

    monkeypatch.setattr(definitions, "_read_rules_bytes", unreadable)
    with pytest.raises(definitions.PublishedVersionRejectedError, match="cannot be read"):
        definitions.get_rules_bytes(H3)


# --- production paths --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "backend-production-db",
        "backend-data-folder",
        "cwd-production-db",
        "env-named-db",
        "env-named-folder",
        "production-name-elsewhere",
        "missing-file",
    ],
)
def test_production_and_missing_paths_are_refused(
    cli: Cli, capsys: pytest.CaptureFixture[str], case: str
) -> None:
    env: dict[str, str] = {}
    if case == "backend-production-db":
        target = cli.backend / "data" / claims.PRODUCTION_DB_NAME
    elif case == "backend-data-folder":
        target = cli.backend / "data" / "copy.db"
    elif case == "cwd-production-db":
        (cli.root / "data").mkdir()
        target = cli.root / "data" / claims.PRODUCTION_DB_NAME
    elif case in {"env-named-db", "env-named-folder"}:
        named = cli.root / "prod" / "ledger-main.db"
        named.parent.mkdir()
        env[claims.DB_PATH_ENV_VAR] = str(named)
        target = named if case == "env-named-db" else named.parent / "sibling.db"
    elif case == "production-name-elsewhere":
        target = cli.root / "elsewhere" / claims.PRODUCTION_DB_NAME
        target.parent.mkdir()
    else:
        target = cli.root / "no-such-ledger.db"
    if case != "missing-file":
        target.write_bytes(cli.db.read_bytes())  # a ledger copy, so only the path refuses
    before = target.read_bytes() if target.exists() else None
    assert cli.main(cli.argv(db=str(target)), env=env) == claims.EXIT_PATH_REFUSED
    err = capsys.readouterr().err
    assert err.startswith("refused: --db ") and str(target) not in err
    assert (target.read_bytes() if target.exists() else None) == before


def test_the_default_backend_is_this_checkouts_backend() -> None:
    # No filesystem access: the constants only.
    assert claims.BACKEND_DIR == APP_ROOT.parent
    assert (claims.PRODUCTION_DB_NAME, claims.DB_PATH_ENV_VAR) == (
        "stock-desk.db",
        "STOCK_DESK_DB_PATH",
    )


@pytest.mark.parametrize("relative", ["data/copy.db", "./data/../data/x.db", "stock-desk.db"])
def test_a_relative_path_is_judged_from_the_working_directory(cli: Cli, relative: str) -> None:
    refusal = claims.production_path_refusal(
        Path(relative), backend_dir=cli.backend, cwd=cli.root, env={}
    )
    assert refusal is not None and refusal.startswith("refused: --db ")


def test_a_non_production_copy_beside_the_backend_is_allowed(cli: Cli) -> None:
    assert (
        claims.production_path_refusal(
            cli.db, backend_dir=cli.backend, cwd=cli.root, env={claims.DB_PATH_ENV_VAR: ""}
        )
        is None
    )


# --- the module entry ------------------------------------------------------------------------


def _python(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(APP_ROOT.parent)},
    )


@pytest.mark.parametrize("module", ["app.forecast.claims", "app.forecast.store"])
def test_claims_and_store_import_in_either_order(module: str, tmp_path: Path) -> None:
    done = _python("-c", f"import {module}; import app.forecast.recorder", cwd=tmp_path)
    assert done.returncode == 0, done.stderr


def test_the_module_runs_as_main_without_a_path_check(tmp_path: Path) -> None:
    # qa batch 4 follow-up 3: ``--help`` runs the module as __main__ (import order,
    # the plain main block) and exits in argparse, before any path is compared, so
    # nothing under the real <backend>/data/ is looked at.
    done = _python("-m", "app.forecast.claims", "--help", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert "register" in done.stdout


_FRESH_MAIN = (
    "import sys\n"
    "from pathlib import Path\n"
    "from app.forecast import claims\n"
    "backend = Path(sys.argv[1])\n"
    "raise SystemExit(claims.main(sys.argv[2:], env={}, cwd=backend.parent, backend_dir=backend))\n"
)


def test_a_fresh_process_refuses_with_the_empty_production_registries(
    cli: Cli, tmp_path: Path
) -> None:
    # The registries are the real, empty ones (no publish in a fresh process). The
    # production paths compared are the tmp_path stand-ins, never the real backend's.
    done = _python("-c", _FRESH_MAIN, str(cli.backend), *cli.argv(), cwd=tmp_path)
    assert done.returncode == claims.EXIT_REFUSED, done.stderr
    assert "UnpublishedVersionError" in done.stderr
    assert cli.rows() == []
    named = cli.argv(db=str(tmp_path / "stock-desk.db"))
    refused = _python("-c", _FRESH_MAIN, str(cli.backend), *named, cwd=tmp_path)
    assert refused.returncode == claims.EXIT_PATH_REFUSED
    assert not (tmp_path / "stock-desk.db").exists()


def test_no_test_here_names_the_real_backend_data_folder() -> None:
    # Every claims.main() call in this file passes a stand-in backend_dir (qa follow-up
    # 3); the fresh-process script does the same (its text is checked here too).
    source = Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    mains = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "main"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "claims"
    ]
    assert mains and all(any(k.arg == "backend_dir" for k in m.keywords) for m in mains)
    assert "backend_dir=backend" in _FRESH_MAIN
    module_runs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(isinstance(a, ast.Constant) and a.value == "-m" for a in node.args)
    ]
    assert len(module_runs) == 1  # the --help run above


def test_the_registration_date_comes_from_the_store_clock(cli: Cli) -> None:
    cli.clock.now = taipei(2026, 11, 20, 21, 30)
    assert cli.main(cli.argv()) == claims.EXIT_OK
    (row,) = cli.rows()
    assert row["registered_at"] == canonical_timestamp(cli.clock.now)
    assert date.fromisoformat(row["registered_at"][:10]) == date(2026, 11, 20)
