"""Look-ahead detection around the evaluator (ADR-0012 T-5, T-6, T-13; methodology T1, T3, T8).

* T-5 (T1) runtime half: :func:`sector_eval.future_perturbation_check` really
  perturbs what a leaking pipeline would read (teeth: a hindsight pipeline
  changes under the same noise).
* T-6 (T3a, T3b): delta_leak calibration on synthetic data -- a null market
  leaves the leaked ranking far ahead of the real one (at least twice the
  frozen margin); a leaking pipeline is flagged; the one-session lag is run
  and recorded.
* T-13 second half (T8): on data with no stock and no sector effect the
  time-shift Δ and the label-shuffle Δ are near 0; forgetting the cost on one
  side, or a structural preference for small sectors, fails the judged
  time-shift check (teeth).
"""

from __future__ import annotations

import numpy as np
import pytest

from app.backtest import sector_eval
from app.backtest.costs import CostModel
from app.data.panel import MarketPanel
from app.research.sector_biased import hindsight_view
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from tests.sector_eval_helpers import SyntheticMarket, replace_frame, synthetic_market

COST = 2 * 0.001425 + 0.003


@pytest.fixture(scope="module")
def null_market() -> SyntheticMarket:
    return synthetic_market(seed=21, forward=165, n_dividends=4)


@pytest.fixture(scope="module")
def null_run(null_market: SyntheticMarket) -> sector_eval.EngineRun:
    return sector_eval.evaluate_views(
        null_market.panel.as_of,
        null_market.panel,
        V1,
        cost_model=CostModel(),
        start=null_market.d0,
        m=1,
        seed=5,
        adjustment=sector_eval.pit_label_factors(null_market.panel),
    )


# ---------------------------------------------------------------------------
# T-5 (T1)
# ---------------------------------------------------------------------------


@pytest.mark.sector_ne7
def test_future_perturbation_check_passes_on_the_real_pipeline(
    null_market: SyntheticMarket,
) -> None:
    dates = null_market.calendar[-60::15]
    record = sector_eval.future_perturbation_check(null_market.panel, V1, dates, seed=3)
    assert record.status == "pass" and record.value == float(len(dates))


@pytest.mark.sector_ne7
def test_future_perturbation_catches_a_hindsight_pipeline(null_market: SyntheticMarket) -> None:
    """Teeth: the same noise changes the decision of a pipeline that ignores recorded_at."""
    t = null_market.calendar[-40]
    noisy = MarketPanel(
        sector_eval.perturb_future(null_market.panel.frames, t, np.random.default_rng(3))
    )
    clean = sector_eval.decision_fingerprint(
        sector_eval.decide(hindsight_view(null_market.panel, t), V1)
    )
    leaked = sector_eval.decision_fingerprint(sector_eval.decide(hindsight_view(noisy, t), V1))
    assert clean != leaked
    # ...while the point-in-time pipeline does not move.
    assert sector_eval.decision_fingerprint(
        sector_eval.decide(null_market.panel.as_of(t), V1)
    ) == sector_eval.decision_fingerprint(sector_eval.decide(noisy.as_of(t), V1))


@pytest.mark.sector_ne7
def test_an_empty_date_sample_fails_t1(null_market: SyntheticMarket) -> None:
    assert sector_eval.future_perturbation_check(null_market.panel, V1, (), seed=1).status == "fail"


@pytest.mark.sector_ne7
def test_labels_never_feed_back_into_a_decision(null_market: SyntheticMarket) -> None:
    """Scrambling every price after t+1 changes labels but not the decision of t."""
    t = null_market.calendar[-30]
    frames = null_market.panel.frames
    bars = frames.bars.copy()
    later = bars["session_date"] > t
    bars.loc[later, "close"] = bars.loc[later, "close"] * 3.0
    shocked = replace_frame(null_market.panel, bars=bars)
    before = sector_eval.decide(null_market.panel.as_of(t), V1)
    after = sector_eval.decide(shocked.as_of(t), V1)
    assert sector_eval.decision_fingerprint(before) == sector_eval.decision_fingerprint(after)


# ---------------------------------------------------------------------------
# T-6 (T3a / T3b)
# ---------------------------------------------------------------------------


@pytest.mark.sector_ne7
def test_leak_margin_calibration_on_a_null_market(null_run: sector_eval.EngineRun) -> None:
    """The frozen delta_leak (0.20) sits at most half-way to the null-market gap."""
    stats = null_run.statistics
    assert stats.main.sample_count >= 30
    assert stats.p_leak is not None and stats.main.p_net is not None
    gap = stats.p_leak - stats.main.p_net
    assert gap >= 2 * V1.gate.leak_margin
    assert sector_eval.leak_control_status(stats.main.p_net, stats.p_leak, 150, V1) == "pass"


@pytest.mark.sector_ne7
def test_a_leaking_pipeline_is_flagged(null_run: sector_eval.EngineRun) -> None:
    """Teeth: rank on the future close(t) -> close(t+H) and score it like the real one."""
    valid = [week for week in null_run.weeks[0] if week.valid]
    p_leak, chosen = sector_eval.leak_control_rate(valid)
    assert p_leak is not None
    leaky_hits = [week.net_beats()[code] for week, code in zip(valid, chosen, strict=True) if code]
    p_real_leaky = sum(leaky_hits) / len(leaky_hits)
    assert p_leak - p_real_leaky < V1.gate.leak_margin
    assert sector_eval.leak_control_status(p_real_leaky, p_leak, len(valid), V1) == "fail"


@pytest.mark.sector_ne7
def test_the_one_session_lag_is_run_and_recorded(null_run: sector_eval.EngineRun) -> None:
    assert null_run.statistics.p_lag is not None
    assert 0.0 <= null_run.statistics.p_lag <= 1.0


# ---------------------------------------------------------------------------
# T-13 (T8): placebos
# ---------------------------------------------------------------------------


@pytest.mark.sector_ne7
def test_placebos_are_near_zero_without_any_effect(null_run: sector_eval.EngineRun) -> None:
    stats = null_run.statistics
    assert stats.time_shift is not None and stats.time_shift.median is not None
    assert abs(stats.time_shift.median) < V1.gate.placebo_shift_tolerance
    assert stats.delta_shuffle is not None and abs(stats.delta_shuffle) < 5.0


def _random_labels(
    rng: np.random.Generator, weeks: int, sizes: list[int], small_edge: float = 0.0
) -> tuple[list[dict[str, float]], list[str]]:
    """Weekly net excess per sector: noise, minus cost, plus an optional small-sector edge."""
    codes = [f"{i:02d}" for i in range(len(sizes))]
    labels = []
    for _ in range(weeks):
        week = {}
        for code, size in zip(codes, sizes, strict=True):
            edge = small_edge if size <= 5 else 0.0
            week[code] = float(rng.normal(-COST + edge, 0.02 / np.sqrt(size / 5)))
        labels.append(week)
    return labels, codes


@pytest.mark.sector_ne7
def test_time_shift_is_near_zero_for_an_unrelated_choice() -> None:
    rng = np.random.default_rng(1)
    labels, codes = _random_labels(rng, 200, [5, 8, 12, 20, 30, 6, 9, 15])
    beats = [{c: v > 0.0 for c, v in week.items()} for week in labels]
    chosen: list[str | None] = [str(rng.choice(codes)) for _ in labels]
    result = sector_eval.time_shift_placebo(chosen, beats, beats)
    assert result.median is not None and abs(result.median) < V1.gate.placebo_shift_tolerance
    assert set(result.deltas) == set(range(4, 200 - 4 + 1))
    assert sector_eval.time_shift_status(result.median, 200, V1) == "pass"


@pytest.mark.sector_ne7
def test_time_shift_catches_a_forgotten_cost() -> None:
    """Teeth: p scored gross, q scored net -> the placebo is far from 0."""
    rng = np.random.default_rng(2)
    labels, codes = _random_labels(rng, 200, [5, 8, 12, 20, 30, 6, 9, 15])
    net = [{c: v > 0.0 for c, v in week.items()} for week in labels]
    gross = [{c: v + COST > 0.0 for c, v in week.items()} for week in labels]
    chosen: list[str | None] = [str(rng.choice(codes)) for _ in labels]
    result = sector_eval.time_shift_placebo(chosen, gross, net)
    assert result.median is not None and result.median >= V1.gate.placebo_shift_tolerance
    assert sector_eval.time_shift_status(result.median, 200, V1) == "fail"


@pytest.mark.sector_ne7
def test_time_shift_catches_a_structural_small_sector_preference() -> None:
    """Teeth: a ranking that always favours the small sector, which structurally beats."""
    rng = np.random.default_rng(3)
    sizes = [5, 8, 12, 20, 30, 9, 15, 25]
    labels, codes = _random_labels(rng, 200, sizes, small_edge=0.02)
    beats = [{c: v > 0.0 for c, v in week.items()} for week in labels]
    chosen: list[str | None] = [codes[0]] * len(labels)
    result = sector_eval.time_shift_placebo(chosen, beats, beats)
    assert result.median is not None and result.median >= V1.gate.placebo_shift_tolerance
    assert sector_eval.time_shift_status(result.median, 200, V1) == "fail"


@pytest.mark.sector_ne7
def test_the_full_pipeline_flags_a_structural_small_sector_drift() -> None:
    """Teeth on real plumbing: small sectors drift up every day, momentum keeps picking them."""
    market = synthetic_market(
        seed=4,
        forward=165,
        n_dividends=0,
        delist=False,
        reclassify=False,
        small_sector_drift=0.004,
    )
    run = sector_eval.evaluate_views(
        market.panel.as_of,
        market.panel,
        V1,
        cost_model=CostModel(),
        start=market.d0,
        m=1,
        seed=6,
    )
    stats = run.statistics
    assert stats.main.sample_count >= 30
    assert stats.time_shift is not None
    median = stats.time_shift.median
    assert median is not None and median >= V1.gate.placebo_shift_tolerance
    assert sector_eval.time_shift_status(median, stats.main.sample_count, V1) == "fail"
