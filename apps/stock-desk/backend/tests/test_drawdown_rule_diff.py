"""The 1.0.3-vs-1.1.0 drawdown comparison script: rebuild, replay, read-only DB.

Bars are synthetic (``bars_from_closes``) or written into a cache under
``tmp_path`` through the real ``PriceBarCache``; the script then reads that
file. No network, no real database.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.advice.loader import Comparison, load_default_rules
from app.data.cache import PriceBarCache
from tests.signals_helpers import bars_from_closes

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "drawdown_rule_diff.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("drawdown_rule_diff", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


diff = _load()

#: Rise to 150, fall 28% to 108, recover to a new high of 160, then dip 15%.
_SCENARIO = (
    [100.0 + i * 0.5 for i in range(101)]  # 0..100: 100 -> 150
    + [150.0 - i * 1.4 for i in range(1, 31)]  # 101..130: -> 108 (-28%)
    + [108.0 + i * 1.04 for i in range(1, 51)]  # 131..180: -> 160 (new high)
    + [160.0 - i * 0.8 for i in range(1, 31)]  # 181..210: -> 136 (-15%)
)


@pytest.fixture(scope="module")
def scenario_rows() -> list[Any]:
    """The full scenario replayed once (each day recomputes every indicator)."""
    return _rows(_SCENARIO, lookback_days=400)


def _rows(closes: list[float], **kwargs: Any) -> list[Any]:
    new_rules = load_default_rules()
    rows: list[Any] = diff.replay(
        "TEST",
        bars_from_closes(closes),
        new_rules=new_rules,
        legacy_rules=diff.legacy_ruleset(new_rules),
        **kwargs,
    )
    return rows


def test_legacy_rebuild_restores_the_1_0_3_conditions_only() -> None:
    current = load_default_rules()
    legacy = diff.legacy_ruleset(current)
    assert legacy.version == "1.0.3"
    assert current.version == "1.1.0"
    for new_rule, old_rule in zip(current.rules, legacy.rules, strict=True):
        assert new_rule.id == old_rule.id
        if new_rule.id in diff.DRAWDOWN_RULE_IDS:
            assert isinstance(old_rule.condition, Comparison)
            assert isinstance(new_rule.condition, Comparison)
            assert old_rule.condition.field == "drawdown.max_drawdown"
            assert new_rule.condition.field == "drawdown.current"
            assert old_rule.condition.value == new_rule.condition.value
            assert old_rule.model_dump(exclude={"condition"}) == new_rule.model_dump(
                exclude={"condition"}
            )
        else:
            assert old_rule == new_rule


def test_legacy_rebuild_refuses_an_unexpected_shape() -> None:
    current = load_default_rules()
    already_legacy = diff.legacy_ruleset(current)
    with pytest.raises(diff.RuleShapeError):
        diff.legacy_ruleset(already_legacy)


def test_new_hits_are_always_a_subset_of_the_legacy_hits(scenario_rows: list[Any]) -> None:
    # current >= max_drawdown on the same window, so with unchanged thresholds
    # 1.1.0 can only fire on days 1.0.3 also fired.
    for row in scenario_rows:
        assert set(row.new_hits) <= set(row.legacy_hits)
        if row.current is not None:  # day 0 has a single bar
            assert row.max_drawdown <= row.current <= 0.0


def test_scenario_days_behave_as_described(scenario_rows: list[Any]) -> None:
    rows = dict(enumerate(scenario_rows))
    # Day 100: at the first high -- neither version fires.
    assert rows[100].legacy_hits == rows[100].new_hits == ()
    # Day 130: 28% below 150 -- both versions fire the lighter rule only.
    assert rows[130].current == pytest.approx(-0.28)
    assert rows[130].new_hits == ("drawdown_protection",)
    assert rows[130].legacy_hits == ("drawdown_protection",)
    # Day 180: back at a new high. 1.0.3 still fires on the old fall, 1.1.0 not.
    assert rows[180].current == 0.0
    assert rows[180].legacy_hits == ("drawdown_protection",)
    assert rows[180].new_hits == ()
    # Day 210: 15% below the new high -- 1.1.0 silent, 1.0.3 still on the old fall.
    assert rows[210].current == pytest.approx(-0.15)
    assert rows[210].new_hits == ()
    assert rows[210].legacy_hits == ("drawdown_protection",)


def test_replay_is_point_in_time_a_future_high_changes_no_earlier_day(
    scenario_rows: list[Any],
) -> None:
    base = scenario_rows
    extended = _rows([*_SCENARIO, 300.0, 320.0], lookback_days=400)
    assert extended[: len(base)] == base
    assert extended[-1].current == 0.0


def test_partial_window_days_are_flagged_and_left_out_of_the_counts() -> None:
    rows = _rows(_SCENARIO[:80], lookback_days=40)
    assert rows[0].partial_window and not rows[-1].partial_window
    counts = diff.summarize(rows)
    assert counts["full_window_days"] == sum(not r.partial_window for r in rows)
    assert counts["partial_window_days"] + counts["full_window_days"] == len(rows)


def test_segments_cover_every_day_exactly_once(scenario_rows: list[Any]) -> None:
    rows = scenario_rows
    segs = diff.segments(rows)
    assert sum(seg.days for seg in segs) == len(rows)
    assert segs[0].first == rows[0].day and segs[-1].last == rows[-1].day


def test_last_n_limits_the_evaluated_days() -> None:
    rows = _rows(_SCENARIO, lookback_days=400, last_n=5)
    assert len(rows) == 5


def _fingerprint(directory: Path) -> dict[str, str]:
    """Hash of every file in ``directory`` (db plus any -wal/-shm sidecars)."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def test_reads_the_cache_read_only_and_never_creates_a_file(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    cache = PriceBarCache(db_path)
    bars = bars_from_closes(_SCENARIO[:40], symbol="3037")
    cache.put(bars, source="twse", fetched_at=bars[-1].as_of)
    before = _fingerprint(tmp_path)

    read = diff.read_cached_bars(db_path, "3037", "TW", bars[0].date, bars[-1].date)
    assert [b.close for b in read] == [b.close for b in bars]
    after = _fingerprint(tmp_path)
    # The database file itself is byte-identical. A WAL-mode reader may leave
    # SQLite's own coordination files behind (-shm, and an *empty* -wal), which
    # carry no data; a non-empty -wal would mean something was written.
    assert after["cache.db"] == before["cache.db"]
    wal = tmp_path / "cache.db-wal"
    assert not wal.exists() or wal.stat().st_size == 0
    assert set(after) - set(before) <= {"cache.db-wal", "cache.db-shm"}

    missing = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        diff.read_cached_bars(missing, "3037", "TW", bars[0].date, bars[-1].date)
    assert not missing.exists()


def test_render_lists_counts_and_a_per_day_table() -> None:
    rows = _rows(_SCENARIO, lookback_days=400, last_n=40)
    text = diff.render_markdown("TEST", "synthetic", rows)
    assert "drawdown_protection：1.0.3 命中" in text
    assert "| 日期 |" in text and "| 起 |" in text
