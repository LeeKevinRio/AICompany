"""Bar normalisation and the ledger digests (ADR-0030 D-2, D-5).

``content_sha256``, ``record_content_hash`` and ``code_digest``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.forecast import canonical
from app.forecast.canonical import (
    BAR_KEYS,
    RECORD_HASH_EXCLUDED_COLUMNS,
    CanonicalFormError,
    bars_json,
    canonical_bar,
    canonical_bars,
    canonical_price,
    canonical_timestamp,
    code_digest,
    code_digest_files,
    content_sha256,
    record_content_hash,
)
from tests.forecast_ledger_helpers import TAIPEI, VALID_ROWS, bar

D1 = date(2026, 11, 12)
D2 = date(2026, 11, 13)


def _bars() -> list[dict[str, object]]:
    return [bar(D1, "16950.25"), bar(D2, "17000.5")]


# --- content_sha256 ----------------------------------------------------------------------


def test_same_content_same_hash() -> None:
    assert content_sha256(_bars()) == content_sha256(_bars())


def test_key_order_does_not_matter() -> None:
    reordered = [dict(reversed(list(item.items()))) for item in _bars()]
    assert list(reordered[0]) != list(_bars()[0])
    assert content_sha256(reordered) == content_sha256(_bars())


def test_equal_values_in_other_forms_hash_the_same() -> None:
    first, second = _bars()
    other = dict(second)
    other["close"] = "17000.50"  # decimal string with a trailing zero
    other["session_date"] = "2026-11-13"
    stamp = second["as_of"]
    assert isinstance(stamp, datetime)
    other["as_of"] = stamp.astimezone(UTC)  # same instant, other zone
    other["fetched_at"] = stamp.isoformat()
    assert content_sha256([first, other]) == content_sha256(_bars())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("session_date", date(2026, 11, 14)),
        ("open", Decimal("17000.01")),
        ("high", Decimal("17100.26")),
        ("low", Decimal("16900.5")),
        ("close", Decimal("17000.51")),
        ("volume", 1235),
        ("source", "twse"),
        ("as_of", datetime(2026, 11, 13, 20, 0, 1, tzinfo=TAIPEI)),
        ("fetched_at", datetime(2026, 11, 13, 20, 0, 0, 1, tzinfo=TAIPEI)),
    ],
)
def test_any_value_change_changes_the_hash(key: str, value: object) -> None:
    changed = _bars()
    changed[1][key] = value
    assert content_sha256(changed) != content_sha256(_bars())


def test_a_dropped_bar_changes_the_hash() -> None:
    assert content_sha256(_bars()[1:]) != content_sha256(_bars())


def test_the_stored_text_reads_back_to_the_same_hash() -> None:
    text = bars_json(_bars())
    assert content_sha256(json.loads(text)) == content_sha256(_bars())
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == content_sha256(_bars())


def test_the_stored_bar_form() -> None:
    assert canonical_bar(bar(D2)) == {
        "session_date": "2026-11-13",
        "open": "17000",
        "high": "17100.25",
        "low": "16900",
        "close": "17000.5",
        "volume": 1234,
        "source": "yfinance",
        "as_of": "2026-11-13T12:00:00.000000+00:00",
        "fetched_at": "2026-11-13T12:00:00.000000+00:00",
    }


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (Decimal("17000.50"), "17000.5"),
        (Decimal("1E+2"), "100"),
        (Decimal("-0.00"), "0"),
        (Decimal("0.0000150"), "0.000015"),
        (17000, "17000"),
        ("1.00000000000000000000000000000001", "1.00000000000000000000000000000001"),
    ],
)
def test_price_normalisation(value: object, text: str) -> None:
    assert canonical_price(value) == text


@pytest.mark.parametrize(
    "value", [17000.5, True, None, "abc", Decimal("NaN"), Decimal("Infinity"), [1]]
)
def test_a_price_without_one_decimal_value_is_refused(value: object) -> None:
    with pytest.raises(CanonicalFormError):
        canonical_price(value)


def test_timestamps_are_utc_with_microseconds() -> None:
    assert canonical_timestamp(datetime(2026, 11, 14, 0, 0, tzinfo=TAIPEI)) == (
        "2026-11-13T16:00:00.000000+00:00"
    )


@pytest.mark.parametrize("value", [datetime(2026, 11, 13, 20, 0), "2026-11-13T20:00:00", "x", 5])
def test_a_naive_or_unreadable_timestamp_is_refused(value: object) -> None:
    with pytest.raises(CanonicalFormError):
        canonical_timestamp(value)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("session_date", datetime(2026, 11, 13, 0, 0, tzinfo=UTC)),
        ("session_date", "13/11/2026"),
        ("volume", -1),
        ("volume", 1.0),
        ("volume", True),
        ("source", ""),
        ("source", " yfinance"),
        ("as_of", datetime(2026, 11, 13, 20, 0)),
    ],
)
def test_a_bad_bar_value_is_refused(key: str, value: object) -> None:
    broken = bar(D2)
    broken[key] = value
    with pytest.raises(CanonicalFormError):
        canonical_bar(broken)


def test_missing_or_extra_keys_are_refused() -> None:
    short = bar(D2)
    del short["fetched_at"]
    extra = bar(D2)
    extra["adj_close"] = Decimal("1")
    for broken in (short, extra):
        with pytest.raises(CanonicalFormError, match="bar keys differ"):
            canonical_bar(broken)
    assert len(BAR_KEYS) == 9


@pytest.mark.parametrize(
    "days",
    [[D2, D1], [D2, D2], []],
    ids=["descending", "duplicate", "empty"],
)
def test_bars_must_be_strictly_ascending_and_non_empty(days: list[date]) -> None:
    with pytest.raises(CanonicalFormError):
        canonical_bars([bar(day) for day in days])


# --- record_content_hash --------------------------------------------------------------


def test_the_record_hash_ignores_exactly_the_four_run_columns() -> None:
    base = dict(VALID_ROWS["forecast_record"])
    reference = record_content_hash(base)
    for column in ("forecast_id", "run_id", "created_at", "late", "content_hash"):
        changed = dict(base)
        changed[column] = "other"
        assert record_content_hash(changed) == reference, column
    covered = set(base) - RECORD_HASH_EXCLUDED_COLUMNS
    for column in covered:
        changed = dict(base)
        changed[column] = f"{base[column]}x"
        assert record_content_hash(changed) != reference, column
    assert "late_cutoff_at" in covered and "validation_status" in covered


# --- code_digest ------------------------------------------------------------------------


def _tree(root: Path, *, newline: str = "\n") -> Path:
    app = root / "app"
    files = {
        "forecast/__init__.py": "",
        "forecast/store.py": "def f():\n    return 1\n",
        "outlook/__init__.py": "",
        "outlook/engine.py": "X = 1\n",
        "dirdef/__init__.py": "",
        "dirdef/sub/deep.py": "Y = 2\n",
        "data/session_calendar.py": "def is_final():\n    pass\n",
    }
    for name, text in files.items():
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return app


def test_code_digest_is_stable(tmp_path: Path) -> None:
    app = _tree(tmp_path)
    assert code_digest(app) == code_digest(app)
    assert len(code_digest(app)) == 64


@pytest.mark.parametrize("newline", ["\r\n", "\r"])
def test_crlf_and_cr_digest_like_lf(tmp_path: Path, newline: str) -> None:
    lf = _tree(tmp_path / "lf")
    other = _tree(tmp_path / "other", newline=newline)
    assert (other / "forecast/store.py").read_bytes() != (lf / "forecast/store.py").read_bytes()
    assert code_digest(other) == code_digest(lf)


def test_other_whitespace_is_content(tmp_path: Path) -> None:
    app = _tree(tmp_path)
    before = code_digest(app)
    (app / "forecast/store.py").write_text("def f():\n    return 1 \n", encoding="utf-8")
    assert code_digest(app) != before


@pytest.mark.parametrize(
    "path",
    ["forecast/store.py", "outlook/engine.py", "dirdef/sub/deep.py", "data/session_calendar.py"],
)
def test_a_content_change_in_any_covered_file_changes_the_digest(tmp_path: Path, path: str) -> None:
    app = _tree(tmp_path)
    before = code_digest(app)
    target = app / path
    target.write_bytes(target.read_bytes() + b"# changed\n")
    assert code_digest(app) != before


def test_added_and_renamed_files_change_the_digest(tmp_path: Path) -> None:
    app = _tree(tmp_path)
    before = code_digest(app)
    (app / "outlook/baselines.py").write_text("", encoding="utf-8")
    added = code_digest(app)
    assert added != before
    (app / "outlook/baselines.py").rename(app / "outlook/base.py")
    assert code_digest(app) not in (before, added)


def test_files_outside_the_scope_do_not_count(tmp_path: Path) -> None:
    app = _tree(tmp_path)
    before = code_digest(app)
    (app / "data/cache.py").write_text("X = 1\n", encoding="utf-8")
    (app / "main.py").write_text("X = 1\n", encoding="utf-8")
    (app / "outlook/rules").mkdir()
    (app / "outlook/rules/h3.yaml").write_text("rules: []\n", encoding="utf-8")
    pycache = app / "forecast/__pycache__"
    pycache.mkdir()
    (pycache / "store.cpython-313.py").write_text("junk\n", encoding="utf-8")
    assert code_digest(app) == before


@pytest.mark.parametrize("missing", ["forecast", "outlook", "dirdef", "data/session_calendar.py"])
def test_a_missing_covered_part_raises(tmp_path: Path, missing: str) -> None:
    app = _tree(tmp_path)
    target = app / missing
    if target.is_dir():
        for path in sorted(target.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        target.rmdir()
    else:
        target.unlink()
    with pytest.raises(FileNotFoundError):
        code_digest(app)


def test_the_real_tree_is_covered() -> None:
    names = [path.relative_to(canonical.APP_ROOT).as_posix() for path in code_digest_files()]
    assert "data/session_calendar.py" in names
    assert "forecast/canonical.py" in names
    assert all(n.startswith(("forecast/", "outlook/", "dirdef/", "data/")) for n in names)
    assert [n for n in names if n.startswith("data/")] == ["data/session_calendar.py"]
    assert len(code_digest()) == 64


def test_the_digest_manifest_uses_app_relative_paths(tmp_path: Path) -> None:
    app = _tree(tmp_path)
    expected = hashlib.sha256(
        json.dumps(
            sorted(
                [
                    "app/" + p.relative_to(app).as_posix(),
                    hashlib.sha256(p.read_bytes()).hexdigest(),
                ]
                for p in code_digest_files(app)
            ),
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert code_digest(app) == expected


def test_timestamps_round_trip_exactly() -> None:
    stamp = datetime(2026, 11, 13, 7, 0, 0, 123456, tzinfo=UTC) + timedelta(0)
    assert datetime.fromisoformat(canonical_timestamp(stamp)) == stamp
