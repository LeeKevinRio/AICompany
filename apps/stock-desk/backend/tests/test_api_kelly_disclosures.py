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
    KELLY_PAYOFF_RATIO_LABEL,
    KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE,
    KELLY_SOFT_NOTICE_DAYS,
    KELLY_STALE_AFTER_DAYS,
    KellyAttemptRecord,
    KellyInputRecord,
)
from app.positions.models import Market
from tests.api_helpers import position_payload, recent_bars, trending_closes
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


def _attempt(harness: ApiHarness, *, spec: str = "spec-1", market: Market = "TW") -> None:
    harness.kelly_attempts.append(
        KellyAttemptRecord(
            symbol="2330",
            market=market,
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
    """The disclosure block for one row, with the attempt an import would leave.

    A row with backtest provenance and no logged attempt is 條件 98's third cell
    and has a sentence of its own; it is not the state most of these tests are
    about, and in production the import appends its attempt before it writes the
    row. So one attempt is seeded here when the fixture has none, which is what
    the real path guarantees. Tests that seed their own attempts, or that are
    about the third cell itself, go through :func:`_get` directly.
    """
    if row is not None:
        harness.kelly_inputs.upsert(row)
        if row.source != "manual" and harness.kelly_attempts.k_observed(
            row.symbol, row.market
        ) == 0:
            _attempt(harness, market=row.market)
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
        (
            "backtest",
            wording.KELLY_SOURCE_BACKTEST_STATEMENT,
            wording.KELLY_SOURCE_BACKTEST_LABEL,
        ),
    ],
)
def test_the_source_sentence_and_label_travel_together(
    source: str, statement: str, label: str, api_harness: ApiHarness
) -> None:
    """任務 4 (FR-6) + 條件 84: each source has both a sentence and a label."""
    row = {"manual": _manual, "backtest_overridden": _overridden, "backtest": _imported}[
        source
    ]()

    block = _disclosures(api_harness, row)

    assert block["source_statement"] == statement
    assert block["source_label"] == label


def test_an_imported_row_states_its_own_source(api_harness: ApiHarness) -> None:
    """條件 84: the third cell, filled by the tenth round. No ``None`` fallback."""
    block = _disclosures(api_harness, _imported())

    assert block["source_statement"] == wording.KELLY_SOURCE_BACKTEST_STATEMENT
    assert block["source_label"] == wording.KELLY_SOURCE_BACKTEST_LABEL


def test_the_source_table_has_a_value_in_every_cell(api_harness: ApiHarness) -> None:
    """條件 84 as a positive assertion over all three sources.

    An empty cell and a sentence nobody has written yet look the same on a
    screen, which is why this is asserted rather than left to the field being
    optional -- it is optional only for the state where there is no row at all.
    """
    for row in (_imported(), _manual(), _overridden()):
        block = _disclosures(api_harness, row)
        assert block["source_statement"] is not None
        assert block["source_label"] is not None


def test_the_source_label_shares_no_slot_with_a_verification_claim(
    api_harness: ApiHarness,
) -> None:
    """條件 85: provenance only -- it says where the pair came from, not that it
    is sound. The rates row is a row of its own in the FR-5 detail, and never
    part of this label.
    """
    block = _disclosures(api_harness, _imported(rates_verified=False))

    assert block["source_label"] == wording.KELLY_SOURCE_BACKTEST_LABEL
    assert "查證" not in block["source_label"]
    assert "查證" not in block["source_statement"]


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


@pytest.mark.parametrize("source", ["backtest", "backtest_overridden"])
def test_a_row_that_owes_b_with_no_attempt_logged_says_the_record_is_missing(
    source: str, api_harness: ApiHarness, caplog: pytest.LogCaptureFixture
) -> None:
    """條件 96/98, cell 3: the absence of the record, stated as an absence.

    The import appends its attempt before it writes the row, so a row with
    backtest provenance and ``K == 0`` means the log is missing what (b) rests
    on -- reachable through rows written before that log existed, which is why
    it is neither a hard failure nor a silent one. The sentence refuses to read
    the missing record as a measured count, and the row is logged for an
    operator at the same time (條件 98).
    """
    row = _imported() if source == "backtest" else _overridden()
    api_harness.kelly_inputs.upsert(row)

    with caplog.at_level("ERROR"):
        block = _get(api_harness)["disclosures"]

    assert block["k_observed"] == 0
    assert block["selection_bias"] == wording.KELLY_SELECTION_BIAS_UNLOGGED
    assert "no attempt logged" in caplog.text


def test_the_missing_record_sentence_renders_no_count_at_all(
    api_harness: ApiHarness,
) -> None:
    """條件 100: 渲染無「0/零/1」字面，常數無佔位符.

    A rendered zero would be the very thing the sentence denies: a count that
    was looked up and found to be none.
    """
    api_harness.kelly_inputs.upsert(_imported())

    sentence = _get(api_harness)["disclosures"]["selection_bias"]

    assert sentence == wording.KELLY_SELECTION_BIAS_UNLOGGED
    for literal in ("0", "零", "1"):
        assert literal not in sentence
    assert "{" not in sentence and "}" not in sentence


@pytest.mark.parametrize("source", ["manual", "absent"])
def test_the_fourth_cell_of_the_k_branch_stays_empty(
    source: str, api_harness: ApiHarness
) -> None:
    """條件 98/100, cell 4 and the row-less screen: no (b) of any kind.

    A typed pair with no import history is the normal state, and a screen with
    no row is not owed (b) at all -- attaching the missing-record sentence to
    either would report a defect where there is none.
    """
    if source == "manual":
        api_harness.kelly_inputs.upsert(_manual())

    block = _get(api_harness)["disclosures"]

    assert block["selection_bias"] is None
    assert wording.KELLY_SELECTION_BIAS_UNLOGGED not in str(block)


def test_the_missing_record_sentence_never_meets_the_attempt_logged_one(
    api_harness: ApiHarness,
) -> None:
    """條件 101 (E-13): the two contradict each other and may not share a screen.

    元件 B/3-B assert that an attempt *was* counted, which is K >= 1; this
    sentence says the record is absent. Both counts are read on the same call
    that reads the row, so the branch cannot be taken from a stale count -- and
    this response carries neither refusal sentence.
    """
    api_harness.kelly_inputs.upsert(_imported())

    body = _get(api_harness)

    assert body["disclosures"]["selection_bias"] == wording.KELLY_SELECTION_BIAS_UNLOGGED
    assert wording.KELLY_REFUSAL_ATTEMPT_LOGGED not in str(body)
    assert wording.KELLY_NON_FINITE_ATTEMPT_LOGGED not in str(body)


def test_one_logged_attempt_switches_to_the_short_sentence(
    api_harness: ApiHarness,
) -> None:
    """The boundary between cells 3 and 2: one attempt is a history to describe."""
    _attempt(api_harness)

    block = _disclosures(api_harness, _imported())

    assert block["selection_bias"] == wording.KELLY_SELECTION_BIAS_SINGLE


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
    _attempt(api_harness)
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


def test_the_effective_cap_uses_the_stored_risk_budget(api_harness: ApiHarness) -> None:
    """條件 87 (BLOCKING): the user's budget, never :class:`RiskBudget`'s defaults.

    The caps can only be tightened, so a default-budget figure is always greater
    than or equal to the enforced one -- the failure mode is a screen promising
    more room than cap 5 will give. 0.10/0.05 is a budget nobody would reach by
    accident: f* = 0.25 gives 2.50% here against 6.25% on the defaults.
    """
    api_harness.client.put(
        "/api/settings",
        json={"risk_budget": {"kelly_fraction_cap": 0.10, "kelly_position_cap": 0.05}},
    )

    block = _disclosures(api_harness, _imported())

    assert block["effective_cap"]["value"] == "2.50%"


def test_the_effective_cap_equals_the_one_cap_5_enforces(api_harness: ApiHarness) -> None:
    """條件 87: same quantity, same number, on both screens that show it.

    Read from the two endpoints a user actually sees: this one, and cap 5's own
    row in the advice card's limits check.
    """
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.put(
        "/api/settings",
        json={"risk_budget": {"kelly_fraction_cap": 0.10, "kelly_position_cap": 0.05}},
    )
    _attempt(api_harness)
    api_harness.kelly_inputs.upsert(_imported())

    block = _get(api_harness)["disclosures"]
    limits = api_harness.client.get("/api/advice/2330").json()["advice"]["limits_check"]
    cap_5 = next(check for check in limits if check["id"] == "kelly_fraction")

    assert block["effective_cap"]["value"] == f"{cap_5['threshold'] * 100:.2f}%"
    assert cap_5["threshold"] == pytest.approx(0.025)


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


def test_the_rates_row_carries_its_sentence_when_verification_did_not_happen(
    api_harness: ApiHarness,
) -> None:
    """條件 45/91, branch 1 of 3: ``rates_verified is False`` shows the sentence."""
    rows = _rows(_disclosures(api_harness, _imported(rates_verified=False)))

    assert rows[wording.KELLY_DETAIL_RATES_VERIFIED_LABEL]["note"] == (
        wording.KELLY_RATES_UNVERIFIED_NOTE
    )
    assert rows[wording.KELLY_DETAIL_RATES_VERIFIED_LABEL]["value"] is None


@pytest.mark.parametrize("rates_verified", [True, None], ids=["verified", "unreported"])
def test_the_rates_row_is_absent_entirely_when_there_is_nothing_approved_to_say(
    rates_verified: bool | None, api_harness: ApiHarness
) -> None:
    """條件 45/91, branches 2 and 3, asserted positively.

    「已查證」 would be the system vouching for itself, which the tenth round
    refused to let anyone draft, and ``None`` ("the run said nothing about its
    rates") is a third state with no sentence of its own. Both are shown by
    **omitting the row**, never by a placeholder or an empty value.
    """
    block = _disclosures(api_harness, _imported(rates_verified=rates_verified))
    rows = _rows(block)

    assert wording.KELLY_DETAIL_RATES_VERIFIED_LABEL not in rows
    assert wording.KELLY_DETAIL_RATES_VERIFIED_LABEL not in str(block)


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
    reason_code: str, market: Market, api_harness: ApiHarness
) -> None:
    """條件 62: the four degraded codes take Kelly's block, not the backtester's."""
    symbol_path = "/api/kelly-inputs/2330/disclosures" + ("?market=US" if market == "US" else "")
    _attempt(api_harness, market=market)
    api_harness.kelly_inputs.upsert(
        _imported(market=market, dividend_reason_code=reason_code)
    )

    block = _get(api_harness, symbol_path)["disclosures"]
    assert block is not None
    rows = _rows(block)

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


def test_a_manual_row_carries_no_walk_forward_sentence(api_harness: ApiHarness) -> None:
    """(c) qualifies an out-of-sample segment, and a typed pair has none."""
    block = _disclosures(api_harness, _manual())

    assert block["walk_forward"] is None
    assert "樣本外" not in str(
        {key: value for key, value in block.items() if key != "manual_input_disclosure"}
    )


def test_an_overridden_row_names_no_segment_and_so_owes_no_walk_forward(
    api_harness: ApiHarness,
) -> None:
    """條件 92, 選項二 (tech-architect 附註二): the word is gone, so (c) is not owed.

    The obligation runs the other way from what option one assumed: 「樣本外」 on a
    screen requires (c) beside it, (c) closes by pointing at the selection-bias
    disclosure, and that would reach ``k_observed`` on a view 約束 7 keeps it off
    -- rebuilding on an overridden row the backtest surface 條件 42 bans there.
    So the period was removed instead, and nothing on this response says the
    word at all.
    """
    block = _disclosures(api_harness, _overridden())

    assert block["walk_forward"] is None
    assert "樣本外" not in str(block)


def test_the_original_values_view_carries_no_out_of_sample_field(
    api_harness: ApiHarness,
) -> None:
    """條件 92 反向斷言: no ``oos_*`` field survives on this view.

    Not only the rendered label: the period must not travel in the payload
    either, or a front end could put it back on the screen without any backend
    change and without any of the sentences it obliges.
    """
    original = _disclosures(api_harness, _overridden(oos_end_date="2026-06-30"))[
        "original_values"
    ]

    assert [key for key in original if key.startswith("oos")] == []
    assert set(original) == {
        "statement",
        "win_rate_label",
        "win_rate",
        "payoff_ratio_label",
        "payoff_ratio",
    }
    # 第十三輪 E-12: the three literals this view may not carry. The label was a
    # 定稿 until that round revoked it, so it is retyped here rather than
    # imported -- there is no constant left to import.
    for literal in ("樣本外", "最近一次", "原始回測的樣本外期間"):
        assert literal not in str(original), literal
    assert "2026-06-30" not in str(original)


@pytest.mark.parametrize("source", ["backtest", "manual", "backtest_overridden"])
def test_no_response_carries_the_revoked_period_label(
    source: str, api_harness: ApiHarness
) -> None:
    """第十三輪: the (任務 8) label was **revoked**, not shelved (E-12).

    With the view narrowed there is no surface for it, so the approval was
    withdrawn and the constant deleted; keeping one "for later" is a wording
    waiting for the next reader to render it. The literal is retyped here
    because nothing in the application defines it any more.

    「最近一次」 is checked with it and for a reason of its own: an ordinal implies
    an orderable set of earlier runs, and this system stores none.
    """
    rows = {"backtest": _imported, "manual": _manual, "backtest_overridden": _overridden}

    block = _disclosures(api_harness, rows[source]())

    for literal in ("原始回測的樣本外期間", "最近一次"):
        assert literal not in str(block), literal


# ---------------------------------------------------------------------------
# 原始值檢視（條件 46/54/65）
# ---------------------------------------------------------------------------


def test_an_overridden_row_shows_its_original_pair(api_harness: ApiHarness) -> None:
    """任務 7 + 條件 65/92: the distinguishing sentence, the labels, the numbers."""
    block = _disclosures(api_harness, _overridden(oos_end_date="2026-06-30"))
    original = block["original_values"]

    assert original["statement"] == wording.KELLY_ORIGINAL_PAIR_DISCLOSURE
    assert original["win_rate_label"] == wording.KELLY_WIN_RATE_ROUND_TRIP_QUALIFIER
    assert original["win_rate"] == "55.0%"
    assert original["payoff_ratio"] == "1.50"
    # 條件 86: the label the range refusal names this field by, from its single
    # definition in ``app/kelly/models.py``.
    assert original["payoff_ratio_label"] == KELLY_PAYOFF_RATIO_LABEL
    assert original["payoff_ratio_label"] in KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE


def test_the_original_pair_is_the_imported_one_not_the_effective_one(
    api_harness: ApiHarness,
) -> None:
    """(任務 7) says these two numbers were never overwritten. They are not."""
    _attempt(api_harness)
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
    assert "原始回測的樣本外期間" not in str(imported["sample_detail"])


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
    # 條件 93: three paragraphs, in order, delivered separately.
    assert notice["body"] == [*items, wording.KELLY_OVERWRITE_NOTICE_CHOICES]
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
    rendered = [*notice["body"], notice["title"], notice["confirm_label"], notice["cancel_label"]]

    for text in rendered:
        assert not any(character.isdigit() for character in text), text


def test_only_two_connector_shapes_are_used_and_neither_crosses_over(
    api_harness: ApiHarness,
) -> None:
    """條件 90:「限「 至 」「 ~ 」二形狀二用途，第三形狀或跨用途即紅燈」.

    出處: 「 至 」 is (a-1)'s own connector between two percentages; 「 ~ 」 is the
    one ``suggest_quantity_range`` already prints a numeric range with. Dates
    take the second, percentages the first, and neither takes the other's job.
    Since 條件 92 the date form has one remaining use, FR-5 欄位 2.
    """
    detail = _rows(_disclosures(api_harness, _imported(oos_end_date="2026-06-30")))
    dates = detail[wording.KELLY_DETAIL_OOS_PERIOD_LABEL]["value"]
    percentages = detail[wording.KELLY_DETAIL_WIN_RATE_CI_LABEL]["value"]

    assert dates == "2025-01-02 ~ 2026-06-30"
    assert percentages == "35.0% 至 73.0%"
    assert " 至 " not in dates
    assert " ~ " not in percentages
    # No third shape anywhere in the block: an en dash, a full-width tilde or a
    # 「到」 would each be a new connector nobody approved.
    for character in ("—", "〜", "～", "到", "–"):
        assert character not in str(detail), character


# ---------------------------------------------------------------------------
# 觸發按鈕標籤（第十二輪 條件 102-105）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source", ["absent", "manual", "backtest", "backtest_overridden"]
)
def test_the_import_trigger_label_is_present_in_all_four_cells(
    source: str, api_harness: ApiHarness
) -> None:
    """條件 103: 恆有值欄位，四格皆回同一常數，正向斷言.

    It may not hang off ``overwrite_notice``: two of the four cells have no
    dialog at all, and the control that opens one still needs a name on every
    screen that offers an import.
    """
    rows = {"manual": _manual, "backtest": _imported, "backtest_overridden": _overridden}
    if source == "absent":
        block = _get(api_harness)["disclosures"]
    else:
        block = _disclosures(api_harness, rows[source]())

    assert block["import_trigger_label"] == wording.KELLY_IMPORT_BACKTEST_TRIGGER_LABEL
    assert block["import_trigger_label"] == "執行回測並帶入"


def test_the_trigger_label_stands_apart_from_the_dialog(api_harness: ApiHarness) -> None:
    """條件 102/103: the trigger names the action; the dialog states its cost.

    Both are present for a hand-keyed row and neither is the other -- the label
    is not one of the dialog's four strings, and it survives the two cells where
    the dialog is ``None``.
    """
    block = _disclosures(api_harness, _manual())
    notice = block["overwrite_notice"]

    assert block["import_trigger_label"] not in notice["body"]
    assert block["import_trigger_label"] != notice["confirm_label"]
    assert block["import_trigger_label"] != notice["title"]

    imported = _disclosures(api_harness, _imported())
    assert imported["overwrite_notice"] is None
    assert imported["import_trigger_label"] == wording.KELLY_IMPORT_BACKTEST_TRIGGER_LABEL


def test_the_trigger_label_promises_no_stored_result_and_no_earlier_run(
    api_harness: ApiHarness,
) -> None:
    """條件 104: neither refused candidate may come back.

    One read as fetching a result this system does not keep (runs are not
    stored; every import spends a data-source call), the other presupposed an
    earlier run, which is false for a symbol nobody has imported.
    """
    label = _get(api_harness)["disclosures"]["import_trigger_label"]

    assert "帶入回測結果" not in label
    assert "重新" not in label
    assert "最近一次" not in label


def test_a_screen_with_no_import_yet_claims_no_imported_source(
    api_harness: ApiHarness,
) -> None:
    """條件 105 (禁樂觀狀態): 「來源：回測帶入」 only after one has succeeded.

    The trigger being on screen is not the import having happened. A row that
    was typed by hand, and a screen with no row at all, carry the label that
    offers the action and no claim that it was taken.
    """
    absent = _get(api_harness)["disclosures"]
    manual = _disclosures(api_harness, _manual())

    for block in (absent, manual):
        assert block["import_trigger_label"] == wording.KELLY_IMPORT_BACKTEST_TRIGGER_LABEL
        assert "來源：回測帶入" not in str(block)


# ---------------------------------------------------------------------------
# 刪除確認（第十五輪 條件 110-114）與檢視兩控制項（條件 116/117）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "scope"),
    [
        ("manual", wording.KELLY_DELETE_NOTICE_SCOPE),
        ("backtest", wording.KELLY_DELETE_NOTICE_SCOPE),
        ("backtest_overridden", wording.KELLY_DELETE_NOTICE_SCOPE_OVERRIDDEN),
    ],
)
def test_every_stored_row_carries_its_own_delete_dialog(
    source: str, scope: str, api_harness: ApiHarness
) -> None:
    """條件 111: 三格互斥窮盡、正向斷言、禁 default，段序凍結、分段交付.

    Only the first paragraph differs. The overridden one names the two value
    sets it is about to remove, because (任務 7) and (fr6-overridden) told the
    user the imported pair is kept -- and the thirteenth round let those stand
    on the premise that the dialog at the moment of the action takes the belief
    back.
    """
    rows = {"manual": _manual, "backtest": _imported, "backtest_overridden": _overridden}

    notice = _disclosures(api_harness, rows[source]())["delete_notice"]

    assert notice["title"] == wording.KELLY_DELETE_NOTICE_TITLE
    assert notice["body"] == [
        scope.format(symbol="2330", market="TW"),
        wording.KELLY_DELETE_NOTICE_NO_RECOVERY,
        wording.KELLY_DELETE_NOTICE_SCOPE_AND_AFTERMATH,
        wording.KELLY_DELETE_NOTICE_CHOICES,
    ]
    assert notice["confirm_label"] == wording.KELLY_DELETE_CONFIRM_LABEL
    assert notice["cancel_label"] == wording.KELLY_OVERWRITE_CANCEL_LABEL


def test_only_the_overridden_row_names_the_kept_pair(api_harness: ApiHarness) -> None:
    """條件 111, the other direction: the variant belongs to one cell only."""
    for row in (_manual(), _imported()):
        notice = _disclosures(api_harness, row)["delete_notice"]
        assert "原本保留的那組原始回測值" not in str(notice)


def test_no_row_means_no_delete_dialog(api_harness: ApiHarness) -> None:
    """Nothing stored, nothing to delete, and so nothing to confirm."""
    assert _get(api_harness)["disclosures"]["delete_notice"] is None


def test_the_delete_dialog_names_the_row_it_will_remove(api_harness: ApiHarness) -> None:
    """條件 113: 僅兩佔位符，server 端插值，渲染沿現行「2330（TW）」形.

    The digits in the rendered paragraph are the symbol's own and nothing else:
    the guard excludes the interpolation itself, which is what the draft's own
    交接 note asked for, and then leaves no other number standing.
    """
    api_harness.kelly_inputs.upsert(_manual(symbol="2330", market="TW"))
    _attempt(api_harness)

    first, *rest = _get(api_harness)["disclosures"]["delete_notice"]["body"]

    assert "2330（TW）" in first
    assert "{" not in first and "}" not in first
    assert [character for character in first if character.isdigit()] == list("2330")
    # 條件 113 again, from the template side: two placeholders, no more.
    assert set(re.findall(r"\{([a-z_]+)\}", wording.KELLY_DELETE_NOTICE_SCOPE)) == {
        "symbol",
        "market",
    }
    # And the interpolation is confined to 段一.
    for paragraph in rest:
        assert "2330" not in paragraph


def test_the_delete_dialog_carries_none_of_the_struck_wordings(
    api_harness: ApiHarness,
) -> None:
    """條件 111 零出現, over what this endpoint actually ships.

    Each was struck for its own reason: the universal that is false of the
    attempt log, the question form that builds dread into the button's context,
    the proceed-anyway framing, the cancel label that prices the two outcomes
    unevenly, the definite claim that presupposes records exist, and the word
    that is meaningless for a symbol whose count is already zero.
    """
    struck = (
        "此動作無法復原",
        "確定刪除",
        "仍要刪除",
        "取消，保留目前資料",
        "嘗試紀錄仍會保留",
        "歸零",
    )

    for row in (_manual(), _imported(), _overridden()):
        notice = str(_disclosures(api_harness, row)["delete_notice"])
        for literal in struck:
            assert literal not in notice, literal


def test_the_delete_dialog_states_the_scope_the_store_actually_has(
    api_harness: ApiHarness,
) -> None:
    """條件 114 (後端半邊): 段三 is a behaviour claim, so it is checked as one.

    The sentence says the attempt log and its count are outside the delete's
    reach. That is 約束 35's design and it is asserted here against the real
    stores rather than trusted: rows and ``k_observed()`` both stand after the
    row is gone.
    """
    _attempt(api_harness, spec="spec-1")
    _attempt(api_harness, spec="spec-2")
    api_harness.kelly_inputs.upsert(_imported())
    before = api_harness.kelly_attempts.k_observed("2330", "TW")

    assert api_harness.client.delete("/api/kelly-inputs/2330").status_code == 204

    assert api_harness.kelly_inputs.get("2330", "TW") is None
    assert api_harness.kelly_attempts.k_observed("2330", "TW") == before == 2
    assert api_harness.kelly_attempts.k_distinct_specs("2330", "TW") == 2
    # And the screen the user lands on is the one 段三 describes: nothing
    # entered, and (b) still standing on the attempts that survived.
    after = _get(api_harness)
    assert after["kelly_input"] is None
    assert after["disclosures"]["freshness_badge_label"] == (
        wording.KELLY_FRESHNESS_BADGE_ABSENT
    )
    assert after["disclosures"]["selection_bias"] == (
        wording.KELLY_SELECTION_BIAS_FULL.format(k_observed=2, k_distinct_specs=2)
    )


def test_the_original_values_controls_track_the_view_they_lead_to(
    api_harness: ApiHarness,
) -> None:
    """條件 116/117: 兩按鈕後端常數，且與 original_values 同真值.

    The entry control's wording is (fr6-overridden)'s own promise ("可以查看")
    made into a control, which is the chain E-5 follows; a control offered where
    the view does not exist would be a promise with nothing behind it.
    """
    overridden = _disclosures(api_harness, _overridden())

    assert overridden["original_values"] is not None
    assert overridden["original_values_entry_label"] == "查看原始回測值"
    assert overridden["original_values_return_label"] == "返回"

    without_a_kept_pair = _overridden(backtest_win_rate=None, backtest_payoff_ratio=None)
    for row in (_manual(), _imported(), without_a_kept_pair):
        block = _disclosures(api_harness, row)
        assert block["original_values"] is None
        assert block["original_values_entry_label"] is None
        assert block["original_values_return_label"] is None


def test_the_view_controls_are_not_folded_into_the_closed_view_contents(
    api_harness: ApiHarness,
) -> None:
    """第十三輪 required: the view's contents stay two numbers, two labels, one
    sentence. The controls are chrome and live beside it, not in it.
    """
    block = _disclosures(api_harness, _overridden())

    assert set(block["original_values"]) == {
        "statement",
        "win_rate_label",
        "win_rate",
        "payoff_ratio_label",
        "payoff_ratio",
    }


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
        approved.update(body)
    approved.add(KELLY_PAYOFF_RATIO_LABEL)
    approved.add(wording.KELLY_SELECTION_BIAS_UNLOGGED)
    approved.add(wording.KELLY_IMPORT_BACKTEST_TRIGGER_LABEL)
    approved.add(wording.KELLY_ORIGINAL_VALUES_ENTRY_LABEL)
    approved.add(wording.KELLY_ORIGINAL_VALUES_BACK_LABEL)
    for source in ("manual", "backtest", "backtest_overridden"):
        paragraphs = wording.kelly_delete_notice(source, symbol="2330", market="TW")
        assert paragraphs is not None
        approved.update(paragraphs)
    # The two that interpolate a measured value, rendered as this endpoint
    # renders them (落地條件 12: fixed digits).
    approved.add(
        wording.KELLY_F_STAR_INTERVAL_DISCLOSURE.format(
            f_star_ci_low_pct="5.00%", f_star_ci_high_pct="42.00%"
        )
    )
    approved.add(wording.KELLY_SELECTION_BIAS_FULL.format(k_observed=2, k_distinct_specs=2))
    # 條件 90: 欄位 9's value is a range between two percentages, joined with the
    # connector (a-1) was approved with for that exact job (出處: (a-1) 定稿,
    # "{f_star_ci_low_pct} 至 {f_star_ci_high_pct}"). It is the only Chinese
    # character this endpoint puts on screen that is not itself a constant, and
    # it is listed here rather than hidden. 落地條件 12 holds either way: both
    # ends are fixed-width.
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
    """落地條件 3 as a property of the **GET disclosures** payload.

    Scope is this endpoint's response. The 422 import body is covered
    field by field in ``tests/test_api_kelly_import.py``, where each of its
    three sentences is compared against the constant it must equal -- an
    equivalent guard reached from the other direction.

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
