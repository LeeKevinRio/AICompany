"""B-16: an empty book with a usable net worth reports cap 3 ``not_evaluable``.

The overview (``GET /api/portfolio/limits``) already withheld cap 3 on an empty
book with :data:`app.advice.limits.EMPTY_BOOK_DETAIL` (風控 2026-08-09, route
(a)); the advice card computed a 0% ``passed`` against the reported net worth.
Since B-16 the check lives in :func:`app.advice.limits._check_gross_exposure`
itself, keyed on ``PortfolioContext.book_holding_count``, so both surfaces give
the same answer. 風控 2026-10-16 conditions: the approved sentence verbatim with
``{name}`` from ``LIMIT_NAMES``; no action or share range changes; no alert
event (so nothing reads as a risk being cleared).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.advice import book_limits
from app.advice import limits as limits_module
from app.advice.book import build_book_context, build_book_level_context
from app.advice.engine import build_advice
from app.advice.limits import (
    EMPTY_BOOK_DETAIL,
    LIMIT_NAMES,
    NET_WORTH_STALE_AFTER_DAYS,
    NO_NET_WORTH_DETAIL,
    LimitCheck,
    PortfolioContext,
    RiskBudget,
    evaluate_limits,
    limit_status_after,
    notional_caps,
    project_position,
    suggest_quantity_range,
)
from app.alerts.engine import evaluate_alerts
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.portfolio.valuation import PositionValuator
from app.positions.store import PositionStore
from app.settings.models import NetWorthSettings
from tests.advice_helpers import (
    book_position,
    book_summary,
    reported_net_worth,
    uptrend_signals,
)
from tests.alerts_helpers import RecordingLoader, add_rule, limit_rule, snapshot
from tests.api_helpers import FakePriceService, UnavailableFxProvider, recent_bars, trending_closes
from tests.conftest import ApiHarness

BUDGET = RiskBudget()
APPROVED = EMPTY_BOOK_DETAIL.format(name=LIMIT_NAMES["gross_exposure"])
NET_WORTH_TWD = 9_000_000.0


def _gross(ctx: PortfolioContext) -> LimitCheck:
    return next(check for check in evaluate_limits(BUDGET, ctx) if check.id == "gross_exposure")


def _empty_card_context(net_worth: Any = None) -> PortfolioContext:
    """The advice card's context for a candidate on an empty book."""
    return build_book_context(
        book_summary(), symbol="2330", close=110.0, currency="TWD", atr=2.0, net_worth=net_worth
    ).context


# --- the builders fill the count ---------------------------------------------------


def test_both_builders_count_an_empty_book_as_zero() -> None:
    assert _empty_card_context().book_holding_count == 0
    assert build_book_level_context(book_summary()).context.book_holding_count == 0


def test_the_count_is_per_symbol_and_market_like_the_overview() -> None:
    summary = book_summary(
        book_position(1, "2330"),
        book_position(2, "2330"),  # a second lot of the same holding
        book_position(3, "2454"),
    )
    assert build_book_level_context(summary).context.book_holding_count == 2
    card = build_book_context(summary, symbol="2330", close=600.0, currency="TWD")
    assert card.context.book_holding_count == 2
    assert len(book_limits._group_positions(summary)) == 2


# --- the approved sentence ---------------------------------------------------------


def test_the_approved_sentence_is_unchanged_and_shared() -> None:
    assert EMPTY_BOOK_DETAIL == (
        "帳本內沒有任何持倉，{name}沒有可評估的部位，本次不計算，回報 not_evaluable。"
    )
    assert book_limits.EMPTY_BOOK_DETAIL is limits_module.EMPTY_BOOK_DETAIL


def test_an_empty_book_with_a_usable_net_worth_withholds_cap_3() -> None:
    cap = _gross(_empty_card_context(reported_net_worth(NET_WORTH_TWD)))
    assert cap.status == "not_evaluable"
    assert cap.observed is None
    # The approved sentence alone: no disclosure sentence is appended to it.
    assert cap.detail == APPROVED


def test_an_empty_book_without_a_net_worth_keeps_the_net_worth_reason() -> None:
    cap = _gross(_empty_card_context())
    assert cap.status == "not_evaluable"
    assert cap.detail == NO_NET_WORTH_DETAIL


def test_an_empty_book_with_an_expired_net_worth_keeps_the_expiry_reason() -> None:
    expired = reported_net_worth(NET_WORTH_TWD, age_days=NET_WORTH_STALE_AFTER_DAYS + 1)
    cap = _gross(_empty_card_context(expired))
    assert cap.status == "not_evaluable"
    assert "未更新" in cap.detail
    assert "帳本內沒有任何持倉" not in cap.detail


# --- a count other than zero changes nothing ---------------------------------------


@pytest.mark.parametrize("count", [None, 1])
def test_a_count_other_than_zero_leaves_cap_3_as_it_was(count: int | None) -> None:
    ctx = PortfolioContext(
        symbol="2330",
        gross_exposure_twd=0.0,
        net_worth=reported_net_worth(NET_WORTH_TWD),
        book_fully_valued=True,
        book_holding_count=count,
    )
    cap = _gross(ctx)
    assert cap.status == "passed"
    assert cap.observed == 0.0


def test_a_held_book_is_unaffected() -> None:
    summary = book_summary(book_position(1, "2330"), book_position(2, "2454"))
    ctx = build_book_context(
        summary,
        symbol="2330",
        close=600.0,
        currency="TWD",
        atr=3.0,
        net_worth=reported_net_worth(NET_WORTH_TWD),
    ).context
    assert ctx.book_holding_count == 2
    before = ctx.model_copy(update={"book_holding_count": None})
    assert evaluate_limits(BUDGET, ctx) == evaluate_limits(BUDGET, before)


# --- the card and the overview agree -----------------------------------------------


def _set_net_worth(harness: ApiHarness, state: str) -> None:
    if state == "absent":
        return
    age = timedelta(days=NET_WORTH_STALE_AFTER_DAYS + 1) if state == "expired" else timedelta(0)
    current = harness.settings.load()
    harness.settings.save(
        current.model_copy(
            update={
                "net_worth": NetWorthSettings(
                    total_net_worth_twd=NET_WORTH_TWD,
                    updated_at=(datetime.now(UTC) - age).isoformat(),
                )
            }
        )
    )


@pytest.mark.parametrize("state", ["absent", "valid", "expired"])
def test_the_card_and_the_overview_give_the_same_answer(
    api_harness: ApiHarness, state: str
) -> None:
    _set_net_worth(api_harness, state)
    api_harness.price_service.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    overview = next(
        check
        for check in api_harness.client.get("/api/portfolio/limits").json()["limits"]
        if check["limit_id"] == "gross_exposure"
    )
    body = api_harness.client.get("/api/advice/2330").json()
    assert body["portfolio_context"]["book_holding_count"] == 0
    card = next(c for c in body["advice"]["limits_check"] if c["id"] == "gross_exposure")
    for key in ("status", "observed", "detail", "threshold"):
        assert card[key] == overview[key], key
    assert card["status"] == "not_evaluable"
    if state == "valid":
        assert card["detail"] == APPROVED


# --- no action or share range changes (風控 condition 4) ---------------------------

#: The action each scenario produces on an empty book, before and after B-16.
_EXPECTED_ACTION = {"add": "add", "defensive": "stop_loss"}


@pytest.mark.parametrize("scenario", ["add", "defensive"])
def test_the_card_changes_only_cap_3s_entry(scenario: str) -> None:
    signals = (
        uptrend_signals()
        if scenario == "add"
        # A deep current drawdown fires the stop-loss rule.
        else uptrend_signals(max_drawdown=-0.4, current_drawdown=-0.35)
    )
    after_ctx = _empty_card_context(reported_net_worth(NET_WORTH_TWD))
    before_ctx = after_ctx.model_copy(update={"book_holding_count": None})
    before = build_advice(
        budget_from_default=False, symbol="2330", signals=signals, portfolio=before_ctx
    )
    after = build_advice(
        budget_from_default=False, symbol="2330", signals=signals, portfolio=after_ctx
    )

    assert {k: v for k, v in before.items() if k != "limits_check"} == {
        k: v for k, v in after.items() if k != "limits_check"
    }
    changed = [
        (old["id"], old["status"], new["status"])
        for old, new in zip(before["limits_check"], after["limits_check"], strict=True)
        if old != new
    ]
    assert changed == [("gross_exposure", "passed", "not_evaluable")]
    assert after["action"] == _EXPECTED_ACTION[scenario]
    assert after["quantity_range"] is None


def test_an_empty_book_sizes_nothing_either_way() -> None:
    ctx = _empty_card_context(reported_net_worth(NET_WORTH_TWD))
    # Equity is 0 on an empty book, so no cap yields a ceiling at all.
    assert notional_caps(BUDGET, ctx) == {}
    for action in ("add", "stop_loss"):
        assert suggest_quantity_range(BUDGET, ctx, action=action) is None


def test_a_projected_trade_on_an_empty_book_stays_not_evaluable() -> None:
    # qa-reviewer L1: the projection does not update the holding count, so an
    # empty-book projection stays ``not_evaluable`` on cap 3 -- the
    # conservative direction -- rather than turning into a pass.
    ctx = _empty_card_context(reported_net_worth(NET_WORTH_TWD))
    projected = project_position(ctx, share_delta=1000.0)
    assert projected.book_holding_count == 0
    assert projected.gross_exposure_twd is not None and projected.gross_exposure_twd > 0.0
    cap = _gross(projected)
    assert cap.status == "not_evaluable"
    assert cap.observed is None
    assert (
        limit_status_after(BUDGET, ctx, limit_id="gross_exposure", share_delta=1000.0)
        == "not_evaluable"
    )
    # Auxiliary only: equity is 0 here, so no range is offered either way.
    assert suggest_quantity_range(BUDGET, ctx, action="add") is None
    assert suggest_quantity_range(BUDGET, projected, action="add") is None


# --- alerts: no event, nothing reads as cleared (風控 condition 3) -----------------


def test_the_flip_raises_no_alert_event(tmp_path: Path) -> None:
    store = AlertStore(db_path=tmp_path / "alerts.db")
    gross_rule = add_rule(store, limit_rule(limit_id="gross_exposure"))
    any_rule = add_rule(store, limit_rule(limit_id="any"))
    after_ctx = _empty_card_context(reported_net_worth(NET_WORTH_TWD))
    before_ctx = after_ctx.model_copy(update={"book_holding_count": None})

    outcomes: list[dict[int, str]] = []
    for ctx, minute in ((before_ctx, 0), (after_ctx, 1)):
        result = evaluate_alerts(
            store,
            RecordingLoader(snapshot(context=ctx, budget=BUDGET)),
            cooldown_minutes=0,
            now=datetime(2026, 10, 17, 1, minute, tzinfo=UTC),
        )
        assert result.events == []
        outcomes.append({outcome.rule_id: outcome.status for outcome in result.outcomes})
    assert store.list_events() == []
    assert outcomes[0] == {gross_rule.id: "quiet", any_rule.id: "quiet"}
    # After: cap 3 is no longer called evaluated-and-within; it is skipped.
    assert outcomes[1] == {gross_rule.id: "skipped", any_rule.id: "skipped"}


def test_the_alert_snapshot_reports_the_approved_sentence(tmp_path: Path) -> None:
    prices = FakePriceService()
    prices.seed("2330", recent_bars(trending_closes(200), symbol="2330"))
    snap = build_snapshot(
        "2330",
        "TW",
        resolver={"TW": prices},
        store=PositionStore(db_path=tmp_path / "positions.db"),
        valuator=PositionValuator(
            market_services={"TW": prices}, fx_provider=UnavailableFxProvider()
        ),
        budget=BUDGET,
        net_worth=reported_net_worth(NET_WORTH_TWD),
    )
    cap = next(check for check in snap.limits if check.id == "gross_exposure")
    assert cap.status == "not_evaluable"
    assert cap.observed is None
    assert cap.detail == APPROVED
