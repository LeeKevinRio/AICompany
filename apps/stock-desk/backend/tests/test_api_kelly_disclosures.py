"""``GET /api/kelly-inputs/{symbol}/disclosures``: the display supply (K4c-1).

Every assertion here traces to a display rule in
`work/reviews/2026-08-19-C5-Kelly-文案批審.md`. The endpoint's contract is that the
**server** decides which approved sentence a screen shows, so what is pinned
below is the branching, not the prose: ``tests/test_kelly_wording.py`` holds the
verbatim inventory, and these tests assert that the right item out of it lands
in the right slot, and that the wrong one lands nowhere.

Four families:

* **來源分支** -- (e) vs (e-manual) (落地條件 11/18), (f) on the two hand-keyed
  sources and not on an import (落地條件 20), FR-5 on ``backtest`` alone (條件 42),
  the original-values view on ``backtest_overridden`` alone (條件 46/65).
* **K 分支** -- (b 完整) / (b 短) / neither, and the fourth cell where no row
  exists at all (落地條件 5).
* **同屏義務** -- (a-1) never without the effective cap beside it (落地條件 6),
  (h) beside the two counts it explains (條件 44).
* **反向斷言** -- FR-5's own labels stay off the original-values view (條件 54),
  and no Chinese string in the response is anything but approved copy
  (落地條件 3: the front end renders and composes nothing).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.advice.limits import LIMIT_NAMES
from app.api import kelly_wording as wording
from app.api.backtest import DIVIDEND_ADJUSTED_NOTE
from app.kelly.models import (
    KELLY_SOFT_NOTICE_DAYS,
    KELLY_STALE_AFTER_DAYS,
    KellyAttemptRecord,
    KellyInputRecord,
)
from tests.conftest import ApiHarness

_PATH = "/api/kelly-inputs/2330/disclosures"

#: Every Han character block, so a response can be scanned for copy the way a
#: reader would see it rather than by field name.
_CJK = re.compile(r"[一-鿿]")


def _recent(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).date().isoformat()


def _imported(**overrides: Any) -> KellyInputRecord:
    """An imported row with a full provenance block, fresh unless overridden."""
    values: dict[str, Any] = {
        "symbol": "2330",
        "market": "TW",
        "win_rate": 0.55,
        "payoff_ratio": 1.5,
        "source": "backtest",
        "backtest_win_rate": 0.55,
        "backtest_payoff_ratio": 1.5,
        "strategy_id": "breakout",
        "window_start": "2024-01-02",
        "window_end": _recent(1),
        "oos_start_date": "2025-01-02",
        "oos_end_date": _recent(1),
        "produced_at": "2026-08-20T00:00:00+00:00",
        "rates_verified": True,
        "dividend_reason_code": "adjusted",
        "adjust_dividends": True,
        "oos_round_trips": 24,
        "oos_win_trips": 13,
        "oos_loss_trips": 11,
        "oos_excluded_boundary_trips": 3,
        "oos_open_trip_at_end": 1,
        "oos_observations": 260,
        "p_ci_low": 0.35,
        "p_ci_high": 0.73,
        "f_star": 0.25,
        "f_star_ci_low": 0.05,
        "f_star_ci_high": 0.42,
        "bootstrap_seed": 7,
        "bootstrap_draws": 2000,
        "low_sample_warning": False,
        "k_observed_at_write": 1,
    }
    values.update(overrides)
    return KellyInputRecord(**values)


def _manual(**overrides: Any) -> KellyInputRecord:
    values: dict[str, Any] = {
        "symbol": "2330",
        "market": "TW",
        "win_rate": 0.55,
        "payoff_ratio": 1.5,
        "source": "manual",
    }
    values.update(overrides)
    return KellyInputRecord(**values)


def _overridden(**overrides: Any) -> KellyInputRecord:
    return _imported(source="backtest_overridden", win_rate=0.5, payoff_ratio=1.2, **overrides)


def _attempt(harness: ApiHarness, *, spec: str = "spec-1") -> None:
    harness.kelly_attempts.append(
        KellyAttemptRecord(
            symbol="2330",
            market="TW",
            strategy_id="breakout",
            request_spec=spec,
            spec_hash=spec,
            outcome="rejected",
            reason_code="low_round_trips",
        )
    )


def _get(harness: ApiHarness, path: str = _PATH) -> dict[str, Any]:
    response = harness.client.get(path)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _disclosures(harness: ApiHarness, row: KellyInputRecord | None = None) -> dict[str, Any]:
    if row is not None:
        harness.kelly_inputs.upsert(row)
    block: dict[str, Any] = _get(harness)["disclosures"]
    return block


def _rows(block: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The FR-5 detail keyed by label, for assertions that name one row."""
    detail = block["sample_detail"]
    assert detail is not None
    return {row["label"]: row for row in detail["rows"]}


# ---------------------------------------------------------------------------
# 來源分支（落地條件 11/18/20, 條件 42/46）
# ---------------------------------------------------------------------------


def test_an_imported_row_gets_the_sampled_frequency_disclosure(
    api_harness: ApiHarness,
) -> None:
    """落地條件 11/18: ``backtest`` takes (e), and (f) is not its sentence."""
    block = _disclosures(api_harness, _imported())

    assert block["win_rate_disclosure"] == wording.KELLY_WIN_RATE_IS_NOT_PROBABILITY
    assert block["manual_input_disclosure"] is None
    assert block["manual_input_tooltip"] is None
    assert block["walk_forward"] == wording.KELLY_WALK_FORWARD_SCOPE


@pytest.mark.parametrize("source", ["manual", "backtest_overridden"])
def test_a_hand_keyed_row_gets_the_typed_estimate_disclosures(
    source: str, api_harness: ApiHarness
) -> None:
    """落地條件 18/20: (e-manual) and (f), on both hand-keyed sources.

    落地條件 20 extended (f) to ``backtest_overridden`` explicitly: the effective
    pair there was typed too, and is checked exactly as little.
    """
    row = _manual() if source == "manual" else _overridden()

    block = _disclosures(api_harness, row)

    assert block["win_rate_disclosure"] == wording.KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY
    assert block["manual_input_disclosure"] == wording.KELLY_MANUAL_INPUT_DISCLOSURE
    assert block["manual_input_tooltip"] == wording.KELLY_MANUAL_INPUT_TOOLTIP
    assert wording.KELLY_WIN_RATE_IS_NOT_PROBABILITY not in str(block)


def test_the_two_win_rate_disclosures_are_mutually_exclusive_and_exhaustive(
    api_harness: ApiHarness,
) -> None:
    """落地條件 18:「互斥且窮盡，掛空或掛錯即 BLOCKING」."""
    approved = {
        wording.KELLY_WIN_RATE_IS_NOT_PROBABILITY,
        wording.KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY,
    }
    for row in (_imported(), _manual(), _overridden()):
        block = _disclosures(api_harness, row)
        assert block["win_rate_disclosure"] in approved


@pytest.mark.parametrize(
    ("source", "statement", "label"),
    [
        ("manual", wording.KELLY_SOURCE_MANUAL_STATEMENT, wording.KELLY_SOURCE_MANUAL_LABEL),
        (
            "backtest_overridden",
            wording.KELLY_SOURCE_OVERRIDDEN_STATEMENT,
            wording.KELLY_SOURCE_OVERRIDDEN_LABEL,
        ),
    ],
)
def test_the_source_sentence_and_label_travel_together(
    source: str, statement: str, label: str, api_harness: ApiHarness
) -> None:
    """任務 4 (FR-6): each source has both a sentence and a short label."""
    row = _manual() if source == "manual" else _overridden()

    block = _disclosures(api_harness, row)

    assert block["source_statement"] == statement
    assert block["source_label"] == label


def test_an_imported_row_has_no_approved_source_sentence_yet(
    api_harness: ApiHarness,
) -> None:
    """缺口, reported rather than filled: 任務 4 approved FR-6 for the two
    hand-keyed sources and for no third one. Inventing a sentence for a plain
    import is what 落地條件 2 forbids, so both slots stay empty and the API says
    so out loud.
    """
    block = _disclosures(api_harness, _imported())

    assert block["source_statement"] is None
    assert block["source_label"] is None


# ---------------------------------------------------------------------------
# K 分支（約束 30 / 落地條件 5）
# ---------------------------------------------------------------------------


def test_no_attempts_means_no_selection_bias_sentence(api_harness: ApiHarness) -> None:
    """The fourth branch: a hand-typed pair with no import history behind it."""
    block = _disclosures(api_harness, _manual())

    assert (block["k_observed"], block["k_distinct_specs"]) == (0, 0)
    assert block["selection_bias"] is None


def test_one_attempt_takes_the_short_sentence(api_harness: ApiHarness) -> None:
    _attempt(api_harness)

    block = _disclosures(api_harness, _imported())

    assert block["k_observed"] == 1
    assert block["selection_bias"] == wording.KELLY_SELECTION_BIAS_SINGLE


def test_two_attempts_take_the_full_sentence_with_both_counts(
    api_harness: ApiHarness,
) -> None:
    _attempt(api_harness, spec="spec-1")
    _attempt(api_harness, spec="spec-2")
    _attempt(api_harness, spec="spec-2")

    block = _disclosures(api_harness, _imported())

    assert (block["k_observed"], block["k_distinct_specs"]) == (3, 2)
    assert block["selection_bias"] == wording.KELLY_SELECTION_BIAS_FULL.format(
        k_observed=3, k_distinct_specs=2
    )


def test_the_counts_are_live_and_not_the_snapshot_on_the_row(
    api_harness: ApiHarness,
) -> None:
    """``k_observed_at_write`` is what K was when the row was written (約束 30).

    An attempt made afterwards still widened the search (b) discloses, so the
    disclosure reads the log rather than the snapshot.
    """
    api_harness.kelly_inputs.upsert(_imported(k_observed_at_write=1))
    _attempt(api_harness, spec="spec-1")
    _attempt(api_harness, spec="spec-2")

    block = _get(api_harness)["disclosures"]

    assert block["k_observed"] == 2
    assert _get(api_harness)["kelly_input"]["item"]["k_observed_at_write"] == 1


def test_an_imported_row_with_no_logged_attempt_is_reported_not_papered_over(
    api_harness: ApiHarness, caplog: pytest.LogCaptureFixture
) -> None:
    """落地條件 5:「K==0 於 backtest 來源不可達;可達即閘門被繞過屬 BLOCKING」.

    The import path appends the attempt before it writes the row, so this state
    means the log lost a row (b) depends on. No sentence is invented for it --
    printing "0 attempts" beside an imported pair would be a claim about a
    search history the system knows it is missing -- and the defect is logged.
    """
    with caplog.at_level("ERROR"):
        block = _disclosures(api_harness, _imported())

    assert block["k_observed"] == 0
    assert block["selection_bias"] is None
    assert "selection-bias disclosure has no attempts" in caplog.text


def test_a_manual_row_without_attempts_is_not_a_defect(
    api_harness: ApiHarness, caplog: pytest.LogCaptureFixture
) -> None:
    """The same K as above, on a source where it is the normal state."""
    with caplog.at_level("ERROR"):
        block = _disclosures(api_harness, _manual())

    assert block["selection_bias"] is None
    assert caplog.text == ""


def test_an_input_that_was_never_entered_still_discloses_its_attempts(
    api_harness: ApiHarness,
) -> None:
    """A refused import leaves a K behind and no row, and (b) outlives it.

    This is also why the endpoint answers 200 where ``GET /{symbol}`` answers
    404: "nothing stored" is a state this screen has copy for.
    """
    _attempt(api_harness)

    body = _get(api_harness)

    assert body["kelly_input"] is None
    block = body["disclosures"]
    assert block["selection_bias"] == wording.KELLY_SELECTION_BIAS_SINGLE
    assert block["freshness_badge_label"] == wording.KELLY_FRESHNESS_BADGE_ABSENT
    assert block["win_rate_disclosure"] is None
    assert block["sample_detail"] is None
    assert block["overwrite_notice"] is None


# ---------------------------------------------------------------------------
# 徽章四態（條件 47）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("age_days", "expected"),
    [
        (0, wording.KELLY_FRESHNESS_BADGE_FRESH),
        (KELLY_SOFT_NOTICE_DAYS, wording.KELLY_FRESHNESS_BADGE_AGEING),
        (KELLY_STALE_AFTER_DAYS, wording.KELLY_FRESHNESS_BADGE_EXPIRED),
    ],
)
def test_the_badge_reports_the_band_the_row_is_in(
    age_days: int, expected: str, api_harness: ApiHarness
) -> None:
    block = _disclosures(api_harness, _imported(oos_end_date=_recent(age_days)))

    assert block["freshness_badge_label"] == expected


def test_the_fourth_badge_state_is_the_absence_of_a_row(api_harness: ApiHarness) -> None:
    """條件 47 ①: "never entered" is not a freshness, and has its own label."""
    block = _get(api_harness)["disclosures"]

    assert block["freshness_badge_label"] == wording.KELLY_FRESHNESS_BADGE_ABSENT


def test_an_unanchorable_row_reports_expired_with_no_age_to_render(
    api_harness: ApiHarness,
) -> None:
    """條件 47 ②: ``age_days`` is null, so nothing may render a day count."""
    api_harness.kelly_inputs.upsert(_imported(oos_end_date=None))
    body = _get(api_harness)

    assert body["kelly_input"]["age_days"] is None
    assert body["disclosures"]["freshness_badge_label"] == (
        wording.KELLY_FRESHNESS_BADGE_EXPIRED
    )


# ---------------------------------------------------------------------------
# (a-1) 與生效上限同屏（落地條件 6/12）
# ---------------------------------------------------------------------------


def test_the_interval_sentence_is_rendered_with_fixed_percentages(
    api_harness: ApiHarness,
) -> None:
    """落地條件 12: fixed digits, never ``:g`` and never scientific notation."""
    block = _disclosures(api_harness, _imported())

    assert block["f_star_interval"] == wording.KELLY_F_STAR_INTERVAL_DISCLOSURE.format(
        f_star_ci_low_pct="5.00%", f_star_ci_high_pct="42.00%"
    )
    assert "e-" not in block["f_star_interval"]
    assert "{" not in block["f_star_interval"]


def test_the_effective_cap_is_on_the_same_screen_as_the_interval(
    api_harness: ApiHarness,
) -> None:
    """落地條件 6: ``min(max(f*, 0) x 0.25, 0.10)`` beside the un-capped f*.

    0.55/1.5 gives f* = 0.25, a quarter of which is 6.25% -- under the 10% hard
    cap, so the number shown is the fractional one and not the cap itself.
    """
    block = _disclosures(api_harness, _imported())

    assert block["effective_cap"] == {
        "label": LIMIT_NAMES["kelly_fraction"],
        "value": "6.25%",
    }


def test_the_hard_cap_wins_when_the_fraction_is_large(api_harness: ApiHarness) -> None:
    block = _disclosures(api_harness, _imported(win_rate=0.8, payoff_ratio=3.0))

    assert block["effective_cap"]["value"] == "10.00%"


def test_an_expired_row_shows_neither_the_interval_nor_a_cap(
    api_harness: ApiHarness,
) -> None:
    """落地條件 6 read the only way it can be: no cap in force, no f* shown.

    An expired pair is not used by cap 5, so there is no 生效上限 to put beside
    the interval -- and the ruling does not allow the interval alone.
    """
    block = _disclosures(api_harness, _imported(oos_end_date=_recent(KELLY_STALE_AFTER_DAYS)))

    assert block["f_star_interval"] is None
    assert block["effective_cap"] is None


@pytest.mark.parametrize("source", ["manual", "backtest_overridden"])
def test_a_hand_keyed_row_shows_no_interval(source: str, api_harness: ApiHarness) -> None:
    """The stored interval measures the imported pair, not the typed one."""
    row = _manual() if source == "manual" else _overridden()

    block = _disclosures(api_harness, row)

    assert block["f_star_interval"] is None
    assert block["effective_cap"] is None


# ---------------------------------------------------------------------------
# FR-5 明細（條件 42/43/44/45）與 (h)
# ---------------------------------------------------------------------------


def test_the_sample_detail_carries_the_frame_and_the_eleven_labels(
    api_harness: ApiHarness,
) -> None:
    """任務 3: the frame sentence, then the rows, in the approved order."""
    block = _disclosures(api_harness, _imported())
    detail = block["sample_detail"]

    assert detail["intro"] == wording.KELLY_BACKTEST_SAMPLE_DETAIL_INTRO
    assert [row["label"] for row in detail["rows"]] == [
        wording.KELLY_DETAIL_STRATEGY_LABEL,
        wording.KELLY_DETAIL_OOS_PERIOD_LABEL,
        wording.KELLY_DETAIL_ROUND_TRIPS_LABEL,
        wording.KELLY_DETAIL_WIN_TRIPS_LABEL,
        wording.KELLY_DETAIL_LOSS_TRIPS_LABEL,
        wording.KELLY_DETAIL_EXCLUDED_BOUNDARY_TRIPS_LABEL,
        wording.KELLY_DETAIL_OPEN_TRIP_AT_END_LABEL,
        wording.KELLY_DETAIL_OBSERVATIONS_LABEL,
        wording.KELLY_DETAIL_WIN_RATE_CI_LABEL,
        wording.KELLY_DETAIL_DIVIDEND_LABEL,
    ]


def test_the_sample_detail_values_are_the_stored_measurements(
    api_harness: ApiHarness,
) -> None:
    rows = _rows(_disclosures(api_harness, _imported(oos_end_date="2026-06-30")))

    assert rows[wording.KELLY_DETAIL_STRATEGY_LABEL]["value"] == "breakout"
    assert rows[wording.KELLY_DETAIL_OOS_PERIOD_LABEL]["value"] == "2025-01-02 ~ 2026-06-30"
    assert rows[wording.KELLY_DETAIL_ROUND_TRIPS_LABEL]["value"] == "24"
    assert rows[wording.KELLY_DETAIL_WIN_TRIPS_LABEL]["value"] == "13"
    assert rows[wording.KELLY_DETAIL_LOSS_TRIPS_LABEL]["value"] == "11"
    assert rows[wording.KELLY_DETAIL_EXCLUDED_BOUNDARY_TRIPS_LABEL]["value"] == "3"
    assert rows[wording.KELLY_DETAIL_OPEN_TRIP_AT_END_LABEL]["value"] == "1"
    assert rows[wording.KELLY_DETAIL_OBSERVATIONS_LABEL]["value"] == "260"
    # 分歧① required 5: a count ratio printed at the precision the count
    # supports, never ``:g``.
    assert rows[wording.KELLY_DETAIL_WIN_RATE_CI_LABEL]["value"] == "35.0% 至 73.0%"


def test_the_three_round_trip_counts_are_withheld_when_they_do_not_add_up(
    api_harness: ApiHarness,
) -> None:
    """條件 43:「n==n_win+n_loss 守門;不成立禁三欄並列」."""
    rows = _rows(_disclosures(api_harness, _imported(oos_round_trips=25)))

    assert wording.KELLY_DETAIL_ROUND_TRIPS_LABEL not in rows
    assert wording.KELLY_DETAIL_WIN_TRIPS_LABEL not in rows
    assert wording.KELLY_DETAIL_LOSS_TRIPS_LABEL not in rows
    # The rest of the detail is unaffected: the guard is about those three.
    assert wording.KELLY_DETAIL_OBSERVATIONS_LABEL in rows


def test_the_boundary_exclusion_sentence_sits_with_the_two_counts_it_explains(
    api_harness: ApiHarness,
) -> None:
    """條件 44: 欄位 6/7 與 (h) 同屏同顯著度."""
    block = _disclosures(api_harness, _imported())
    rows = _rows(block)

    assert block["boundary_exclusion"] == wording.KELLY_BOUNDARY_TRIP_EXCLUSION
    assert wording.KELLY_DETAIL_EXCLUDED_BOUNDARY_TRIPS_LABEL in rows
    assert wording.KELLY_DETAIL_OPEN_TRIP_AT_END_LABEL in rows


@pytest.mark.parametrize(
    ("rates_verified", "expected"),
    [(False, wording.KELLY_RATES_UNVERIFIED_NOTE), (True, None), (None, None)],
)
def test_the_rates_row_appears_only_for_an_explicit_false(
    rates_verified: bool | None, expected: str | None, api_harness: ApiHarness
) -> None:
    """條件 45:「綁 rates_verified is False;None 不顯示;禁 not 寫法」.

    ``None`` is "the run said nothing about its rates", which is a different
    finding with no approved sentence -- and the one a ``not rates_verified``
    test would silently merge into the other.
    """
    rows = _rows(_disclosures(api_harness, _imported(rates_verified=rates_verified)))
    row = rows.get(wording.KELLY_DETAIL_RATES_VERIFIED_LABEL)

    assert (None if row is None else row["note"]) == expected


@pytest.mark.parametrize(
    ("reason_code", "market"),
    [
        ("disabled", "TW"),
        ("never_synced", "TW"),
        ("no_events", "TW"),
        ("no_events", "US"),
        ("unusable_events", "TW"),
    ],
)
def test_the_dividend_row_carries_kellys_own_block(
    reason_code: str, market: str, api_harness: ApiHarness
) -> None:
    """條件 62: the four degraded codes take Kelly's block, not the backtester's."""
    symbol_path = "/api/kelly-inputs/2330/disclosures" + ("?market=US" if market == "US" else "")
    api_harness.kelly_inputs.upsert(
        _imported(market=market, dividend_reason_code=reason_code)
    )

    rows = _rows(_get(api_harness, symbol_path)["disclosures"])

    assert rows[wording.KELLY_DETAIL_DIVIDEND_LABEL]["note"] == wording.kelly_dividend_note(
        reason_code, market=market
    )


def test_a_restored_run_keeps_the_backtesters_own_note(api_harness: ApiHarness) -> None:
    """第六輪:「DIVIDEND_ADJUSTED_NOTE 沿用核可」, reused by the assembly point."""
    rows = _rows(_disclosures(api_harness, _imported(dividend_reason_code="adjusted")))

    assert rows[wording.KELLY_DETAIL_DIVIDEND_LABEL]["note"] == DIVIDEND_ADJUSTED_NOTE


def test_an_unknown_dividend_code_produces_no_row_at_all(api_harness: ApiHarness) -> None:
    rows = _rows(_disclosures(api_harness, _imported(dividend_reason_code="something_new")))

    assert wording.KELLY_DETAIL_DIVIDEND_LABEL not in rows


@pytest.mark.parametrize("source", ["manual", "backtest_overridden"])
def test_the_sample_detail_is_shown_for_imports_only(
    source: str, api_harness: ApiHarness
) -> None:
    """條件 42:「11 欄明細僅 source=='backtest' 顯示」.

    An overridden row showing it would put the imported sample beside hand-keyed
    effective values, which is exactly what 落地條件 21 says needs a
    distinguishing sentence of its own.
    """
    row = _manual() if source == "manual" else _overridden()

    block = _disclosures(api_harness, row)

    assert block["sample_detail"] is None
    assert block["boundary_exclusion"] is None
    assert block["walk_forward"] is None


# ---------------------------------------------------------------------------
# 原始值檢視（條件 46/54/65）
# ---------------------------------------------------------------------------


def test_an_overridden_row_shows_its_original_pair(api_harness: ApiHarness) -> None:
    """任務 7/8 + 條件 65: the distinguishing sentence, the label, the numbers."""
    block = _disclosures(api_harness, _overridden(oos_end_date="2026-06-30"))
    original = block["original_values"]

    assert original["statement"] == wording.KELLY_ORIGINAL_PAIR_DISCLOSURE
    assert original["win_rate_label"] == wording.KELLY_WIN_RATE_ROUND_TRIP_QUALIFIER
    assert original["win_rate"] == "55.0%"
    assert original["payoff_ratio"] == "1.50"
    assert original["oos_period_label"] == wording.KELLY_ORIGINAL_OOS_PERIOD_LABEL
    assert original["oos_period"] == "2025-01-02 ~ 2026-06-30"
    # 缺口: no label over the payoff ratio was ever drafted, and none is invented.
    assert original["payoff_ratio_label"] is None


def test_the_original_pair_is_the_imported_one_not_the_effective_one(
    api_harness: ApiHarness,
) -> None:
    """(任務 7) says these two numbers were never overwritten. They are not."""
    api_harness.kelly_inputs.upsert(_overridden())
    body = _get(api_harness)

    assert body["kelly_input"]["item"]["win_rate"] == 0.5
    assert body["disclosures"]["original_values"]["win_rate"] == "55.0%"


@pytest.mark.parametrize(
    "row",
    [
        _imported(),
        _manual(),
        _overridden(backtest_win_rate=None, backtest_payoff_ratio=None),
    ],
    ids=["backtest", "manual", "overridden-without-a-kept-pair"],
)
def test_the_original_values_view_is_withheld_everywhere_else(
    row: KellyInputRecord, api_harness: ApiHarness
) -> None:
    """條件 46, the four cells: only an overridden row with a kept pair shows it.

    The third case is the one worth spelling out: (任務 7) states that the two
    numbers survived the edit, so a row where they did not must not carry it.
    """
    block = _disclosures(api_harness, row)

    assert block["original_values"] is None


def test_the_original_values_view_borrows_no_label_from_the_sample_detail(
    api_harness: ApiHarness,
) -> None:
    """條件 54: FR-5 欄位 2 的字面於原始值檢視零出現，反之亦然.

    The two rows both hold an out-of-sample period and would read as the same
    row if they shared a label; 任務 8 approved a different one for this view for
    exactly that reason.
    """
    overridden = _disclosures(api_harness, _overridden())
    original = overridden["original_values"]
    forbidden = (
        wording.KELLY_DETAIL_OOS_PERIOD_LABEL,
        wording.KELLY_DETAIL_STRATEGY_LABEL,
        wording.KELLY_DETAIL_WIN_RATE_CI_LABEL,
        wording.KELLY_BACKTEST_SAMPLE_DETAIL_INTRO,
    )
    for label in forbidden:
        assert label not in str(original)

    imported = _disclosures(api_harness, _imported())
    assert wording.KELLY_ORIGINAL_OOS_PERIOD_LABEL not in str(imported["sample_detail"])


# ---------------------------------------------------------------------------
# 覆蓋前告知（條件 53/68/73）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "items"),
    [
        (
            "manual",
            (
                wording.KELLY_OVERWRITE_NOTICE_MANUAL_EFFECT,
                wording.KELLY_OVERWRITE_NOTICE_MANUAL_LOSS,
            ),
        ),
        (
            "backtest_overridden",
            (
                wording.KELLY_OVERWRITE_NOTICE_OVERRIDDEN_EFFECT,
                wording.KELLY_OVERWRITE_NOTICE_OVERRIDDEN_LOSS,
            ),
        ),
    ],
)
def test_a_hand_keyed_row_carries_its_own_overwrite_dialog(
    source: str, items: tuple[str, ...], api_harness: ApiHarness
) -> None:
    """條件 73, cells 2 and 3: each source gets its own variant, whole."""
    row = _manual() if source == "manual" else _overridden()

    notice = _disclosures(api_harness, row)["overwrite_notice"]

    assert notice["title"] == wording.KELLY_OVERWRITE_NOTICE_TITLE
    assert notice["body"] == "".join(items) + wording.KELLY_OVERWRITE_NOTICE_CHOICES
    assert notice["confirm_label"] == wording.KELLY_OVERWRITE_CONFIRM_LABEL
    assert notice["cancel_label"] == wording.KELLY_OVERWRITE_CANCEL_LABEL


def test_an_imported_row_carries_no_overwrite_dialog(api_harness: ApiHarness) -> None:
    """條件 73, cell 4: an explicit no, asserted positively.

    Re-importing over an imported row swaps one measurement for another, loses
    nothing hand-keyed, and is the action (g-3)/(g-4) instruct the user to take.
    """
    block = _disclosures(api_harness, _imported())

    assert block["overwrite_notice"] is None


def test_no_row_means_no_overwrite_dialog(api_harness: ApiHarness) -> None:
    """條件 73, cell 1: nothing stored, nothing to overwrite."""
    assert _get(api_harness)["disclosures"]["overwrite_notice"] is None


def test_the_overwrite_dialog_renders_no_measured_number(api_harness: ApiHarness) -> None:
    """條件 75: no win rate and no payoff ratio anywhere on this dialog."""
    notice = _disclosures(api_harness, _manual())["overwrite_notice"]

    for text in notice.values():
        assert not any(character.isdigit() for character in text), text


# ---------------------------------------------------------------------------
# 反向斷言：回應中的中文全部是核可字面（落地條件 3）
# ---------------------------------------------------------------------------


def _chinese_strings(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return [text for value in payload.values() for text in _chinese_strings(value)]
    if isinstance(payload, list):
        return [text for value in payload for text in _chinese_strings(value)]
    if isinstance(payload, str) and _CJK.search(payload):
        return [payload]
    return []


def _approved_texts() -> set[str]:
    """Every string this endpoint is allowed to emit, assembled ones included."""
    approved = set(wording.RISK_CONFIRMED_WORDING.values())
    approved.add(DIVIDEND_ADJUSTED_NOTE)
    approved.add(LIMIT_NAMES["kelly_fraction"])
    for code, market in (
        ("disabled", "TW"),
        ("never_synced", "TW"),
        ("no_events", "TW"),
        ("no_events", "US"),
        ("unusable_events", "TW"),
    ):
        block = wording.kelly_dividend_note(code, market=market)
        assert block is not None
        approved.add(block)
    for source in ("manual", "backtest_overridden"):
        body = wording.kelly_overwrite_notice(source)
        assert body is not None
        approved.add(body)
    # The two that interpolate a measured value, rendered as this endpoint
    # renders them (落地條件 12: fixed digits).
    approved.add(
        wording.KELLY_F_STAR_INTERVAL_DISCLOSURE.format(
            f_star_ci_low_pct="5.00%", f_star_ci_high_pct="42.00%"
        )
    )
    approved.add(wording.KELLY_SELECTION_BIAS_FULL.format(k_observed=2, k_distinct_specs=2))
    # 欄位 9's value is a range between two percentages, and the connector is the
    # one (a-1) was approved with for the same job ("{low} 至 {high}"). It is the
    # only Chinese character this endpoint puts on screen that is not itself a
    # constant, and it is listed here rather than hidden so a reviewer sees it:
    # if risk-compliance wants the range shaped differently, this is the line to
    # change. 落地條件 12 is met either way -- both ends are fixed-width.
    approved.add("35.0% 至 73.0%")
    return approved


@pytest.mark.parametrize(
    "row",
    [_imported(), _manual(), _overridden(), _imported(rates_verified=False)],
    ids=["backtest", "manual", "overridden", "unverified-rates"],
)
def test_every_chinese_string_in_the_response_is_approved_copy(
    row: KellyInputRecord, api_harness: ApiHarness
) -> None:
    """落地條件 3 as a property of the payload, not of the front end.

    If the server can only ever emit approved strings, a front end that renders
    what it is given cannot show unapproved copy -- which is the whole point of
    moving the branching here.
    """
    _attempt(api_harness, spec="spec-1")
    _attempt(api_harness, spec="spec-2")
    api_harness.kelly_inputs.upsert(row)

    body = _get(api_harness)
    approved = _approved_texts()

    unexpected = [text for text in _chinese_strings(body["disclosures"]) if text not in approved]
    assert unexpected == [], unexpected
