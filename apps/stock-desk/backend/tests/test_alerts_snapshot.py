"""Snapshot assembly, focused on the FX input the risk caps depend on.

A snapshot has no notes list, so the question these tests pin down is whether a
missing or degraded conversion still reaches the reader -- a missing one through
``price_cap_cause`` (which the engine appends to a risk-limit skip, and only
where the conversion is the cause; ``reason`` still carries it as well), an
applied one through ``fx_disclosure`` (which the engine puts in the message a
fired alert sends) -- instead of quietly turning every price-based cap into
``not_evaluable``, or quoting a converted figure with no stated provenance.

The last two tests deliberately run the whole chain (snapshot -> engine ->
``AlertEvent.message``): a disclosure that stops anywhere short of the message
is not a disclosure.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.advice.book import (
    FX_APPLIED_NOTE,
    FX_PAIR_MISMATCH_NOTE,
    FX_UNAVAILABLE_NOTE,
    NO_FX_QUOTE_NOTE,
)
from app.advice.limits import LIMIT_IDS, LIMIT_NAMES, RiskBudget, SelfReportedNetWorth
from app.alerts.engine import EvaluationResult, SymbolSnapshot, evaluate_alerts
from app.alerts.snapshot import build_snapshot
from app.alerts.store import AlertStore
from app.data.interface import DataStatus, PriceBar
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.portfolio.valuation import PositionValuator
from app.positions.models import Market, PositionInput
from app.positions.store import PositionStore
from app.services.fx import source_note
from tests.advice_helpers import reported_net_worth
from tests.alerts_helpers import (
    add_rule,
    insert_legacy_signal_rule,
    limit_rule,
    price_rule,
    signal_rule,
)
from tests.api_helpers import (
    FakePriceService,
    UnavailableFxProvider,
    position_payload,
    recent_bars,
    trending_closes,
)
from tests.conftest import ApiHarness


class StubFxProvider(FxRateProvider):
    """One flat rate, dated on the requested window's end."""

    source_id = "bank_of_taiwan"

    def __init__(self, rate: str = "31.5") -> None:
        self._rate = Decimal(rate)

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        now = datetime.now(UTC)
        return FxRateResult(
            rates=[FxRate(pair=pair, date=end, rate=self._rate, as_of=now, source=self.source_id)],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


@pytest.fixture
def store(tmp_path: Path) -> PositionStore:
    return PositionStore(db_path=tmp_path / "positions.db")


def _price_service(currency: str) -> FakePriceService:
    service = FakePriceService()
    service.seed("2330", recent_bars(trending_closes(60), symbol="2330", currency=currency))
    return service


def _hold(store: PositionStore, currency: str) -> None:
    store.create(
        PositionInput(
            symbol="2330",
            market="TW",
            quantity=Decimal(1000),
            avg_cost=Decimal(600),
            currency=currency,  # type: ignore[arg-type]
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            note=None,
        )
    )


def _snapshot(
    store: PositionStore,
    *,
    currency: str,
    fx_provider: FxRateProvider | None,
    net_worth: SelfReportedNetWorth | None = None,
) -> SymbolSnapshot:
    service = _price_service(currency)
    return build_snapshot(
        "2330",
        "TW",
        resolver={"TW": service},
        store=store,
        valuator=PositionValuator(
            market_services={"TW": service}, fx_provider=fx_provider or UnavailableFxProvider()
        ),
        budget=RiskBudget(),
        fx_provider=fx_provider,
        net_worth=net_worth,
    )


def test_the_data_layers_sentence_on_a_fresh_series_reaches_the_snapshot(
    store: PositionStore,
) -> None:
    """風控 2026-09-15 R1-a: a spliced series arrives as ``fresh``; its reason is
    kept for the fired message and still shown on a skip, not replaced by the
    layer note (which says nothing on ``fresh``)."""
    spliced = "這段日線資料由多個來源拼接（finmind、twse），每筆保留原本的來源；..."
    service = _price_service("TWD")
    service.reason = spliced
    snapshot = build_snapshot(
        "2330",
        "TW",
        resolver={"TW": service},
        store=store,
        valuator=PositionValuator(
            market_services={"TW": service}, fx_provider=UnavailableFxProvider()
        ),
        budget=RiskBudget(),
        fx_provider=None,
        net_worth=None,
    )
    assert snapshot.close is not None
    assert snapshot.data_disclosure == spliced
    assert spliced in (snapshot.reason or "")
    # 風控 R4-a: on a cached bar the layer note travels with the fired message too.
    service.status = DataStatus.CACHED_STALE
    cached = build_snapshot(
        "2330",
        "TW",
        resolver={"TW": service},
        store=store,
        valuator=PositionValuator(
            market_services={"TW": service}, fx_provider=UnavailableFxProvider()
        ),
        budget=RiskBudget(),
        fx_provider=None,
        net_worth=None,
    )
    assert cached.data_disclosure is not None
    assert cached.data_disclosure.startswith("資料來自 cached_stale 層（")
    assert cached.data_disclosure.endswith(spliced)


def test_the_exposure_cap_is_off_until_a_net_worth_reaches_the_snapshot(
    store: PositionStore,
) -> None:
    # A ``risk_limit_breach`` rule on gross exposure can only fire once the
    # denominator exists; without one the cap reports why, and the engine turns
    # that into a visible skip rather than a silent non-firing.
    _hold(store, "TWD")
    without = _snapshot(store, currency="TWD", fx_provider=None)
    assert next(c for c in without.limits if c.id == "gross_exposure").status == "not_evaluable"

    with_report = _snapshot(
        store,
        currency="TWD",
        fx_provider=None,
        net_worth=reported_net_worth(1_000_000_000.0),
    )
    assert next(c for c in with_report.limits if c.id == "gross_exposure").status == "passed"


def test_a_twd_holding_needs_no_rate_and_gains_no_extra_reason(
    store: PositionStore,
) -> None:
    _hold(store, "TWD")
    snapshot = _snapshot(store, currency="TWD", fx_provider=None)
    assert snapshot.reason is None
    weight = next(c for c in snapshot.limits if c.id == "single_position_weight")
    assert weight.status != "not_evaluable"


def test_a_foreign_holding_without_a_provider_says_the_conversion_is_missing(
    store: PositionStore,
) -> None:
    _hold(store, "USD")
    snapshot = _snapshot(store, currency="USD", fx_provider=None)
    reason = snapshot.reason or ""
    assert "無法取得匯率換算" in reason
    assert "不以 1.0 匯率代入" in reason
    weight = next(c for c in snapshot.limits if c.id == "single_position_weight")
    assert weight.status == "not_evaluable"


def test_a_foreign_holding_with_a_rate_states_the_rate_it_used(
    store: PositionStore,
) -> None:
    _hold(store, "USD")
    snapshot = _snapshot(store, currency="USD", fx_provider=StubFxProvider())
    reason = snapshot.reason or ""
    assert "USDTWD" in reason
    assert "31.5" in reason
    assert "fresh" in reason


def test_an_applied_rate_carries_its_sources_standing_disclosure(
    store: PositionStore,
) -> None:
    # ADR-0005 F-4. It is a separate field from ``reason`` on purpose: ``reason``
    # is only ever shown on a *skipped* rule, and a rate that was applied is by
    # definition on a snapshot complete enough to fire.
    _hold(store, "USD")
    snapshot = _snapshot(store, currency="USD", fx_provider=StubFxProvider())
    assert snapshot.fx_disclosure == source_note(StubFxProvider.source_id)
    assert "即期買賣中點" in (snapshot.fx_disclosure or "")


def test_a_twd_holding_is_not_given_an_fx_disclosure_it_did_not_use(
    store: PositionStore,
) -> None:
    # No conversion happened, so there is no rate methodology to disclose;
    # padding every alert with the sentence would train the reader to skip it.
    _hold(store, "TWD")
    snapshot = _snapshot(store, currency="TWD", fx_provider=StubFxProvider())
    assert snapshot.fx_disclosure is None
    assert snapshot.reason is None


def test_an_unusable_rate_says_so_without_claiming_a_methodology(
    store: PositionStore,
) -> None:
    # The disclosure qualifies a rate that was applied; when none was, nothing
    # was converted, so the reason must stay on the missing conversion instead.
    _hold(store, "USD")
    snapshot = _snapshot(store, currency="USD", fx_provider=UnavailableFxProvider())
    assert snapshot.fx_disclosure is None
    assert "無法取得匯率換算" in (snapshot.reason or "")


# --- End to end: snapshot -> engine -> the message a user receives ------------


def _fire_limit_alert(
    positions: PositionStore, alerts: AlertStore, *, currency: str, limit_id: str
) -> EvaluationResult:
    """Run a real ``risk_limit_breach`` tick over the real snapshot builder."""
    service = _price_service(currency)
    valuator = PositionValuator(market_services={"TW": service}, fx_provider=StubFxProvider())
    # A deliberately tight loss budget: the point of these two tests is the
    # wording of a *fired* message, and the cap has to breach for there to be
    # one. The default 1% happens not to be crossed by this fixture's ATR.
    budget = RiskBudget(max_loss_per_trade=0.001)
    add_rule(alerts, limit_rule(limit_id=limit_id))

    def load(symbol: str, market: Market) -> SymbolSnapshot:
        return build_snapshot(
            symbol,
            market,
            resolver={"TW": service},
            store=positions,
            valuator=valuator,
            budget=budget,
            fx_provider=StubFxProvider(),
        )

    return evaluate_alerts(alerts, load, now=datetime.now(UTC))


def test_a_fired_per_trade_loss_alert_on_a_foreign_holding_discloses_the_rate(
    store: PositionStore, tmp_path: Path
) -> None:
    # The whole chain, because the defect this pins was invisible at either end
    # alone: the snapshot carried the sentence, the engine read a different
    # field, and the message that actually reached Discord/Telegram quoted a
    # loss percentage computed through ``ctx.fx_to_twd`` with no provenance.
    _hold(store, "USD")
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    result = _fire_limit_alert(store, alerts, currency="USD", limit_id="per_trade_loss")

    assert [outcome.status for outcome in result.outcomes] == ["fired"]
    message = result.events[0].message
    assert "單筆最大可承受虧損" in message
    assert source_note(StubFxProvider.source_id) in message
    # And the same text is what the feed and the push channels read.
    assert alerts.list_events()[0].message == message


def test_a_fired_alert_on_a_twd_holding_stays_free_of_fx_wording(
    store: PositionStore, tmp_path: Path
) -> None:
    _hold(store, "TWD")
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    result = _fire_limit_alert(store, alerts, currency="TWD", limit_id="per_trade_loss")

    assert [outcome.status for outcome in result.outcomes] == ["fired"]
    message = result.events[0].message
    assert "單筆最大可承受虧損" in message
    assert "匯率" not in message


# --- An unusable latest close skips one symbol, not the whole tick -------------
#
# 2026-10-06 任務單「單一標的收盤價不合法不中斷整輪警示檢查」, 方案 A′: a latest
# bar whose close is zero or negative used to reach ``PortfolioContext.close``
# (``gt=0``) and raise, which took every rule of every symbol down with it.

BAD = "2330"
GOOD = "2317"
UNUSABLE_LATEST_CLOSES = [pytest.param(0.0, id="zero"), pytest.param(-1.0, id="negative")]

#: Existing reasons, verbatim; nothing here is new wording.
NO_CLOSE_REASON = "沒有可用的最新收盤價。"
NO_SIGNALS_REASON = "沒有可用的訊號輸出。"
#: ADR-0021 W-2 for ``beta.value``, verbatim (see test_adr0021_field_evaluability).
BETA_W2_REASON = (
    "此規則使用的 beta.value（相對指標的 beta），警示不提供作為條件。"
    "每次檢查都會略過此規則，不會觸發。可改用其他欄位的條件，或刪除此規則。"
)
#: S-B2-A, approved verbatim by risk-compliance-officer 2026-10-07: the unheld
#: symbol on A′ leaves its sector, per-trade-loss and Kelly caps unevaluated
#: while the other two pass, so its ``any`` rule is quiet with this reason --
#: and nothing about the unusable close, the data layer or FX is appended.
ANY_LIMIT_QUIET_REASON = (
    "本次有 3 條上限未評估，未納入判定：單一產業佔比上限、單筆最大可承受虧損、"
    "分數 Kelly 部位上限。其餘已評估的上限皆未違反。"
)
#: The same through the API harness, which has no net worth in settings, so
#: the gross-exposure cap is unevaluated as well.
ANY_LIMIT_QUIET_REASON_NO_NET_WORTH = (
    "本次有 4 條上限未評估，未納入判定：單一產業佔比上限、總曝險上限、"
    "單筆最大可承受虧損、分數 Kelly 部位上限。其餘已評估的上限皆未違反。"
)


def _bad_latest_bars(close: float) -> list[PriceBar]:
    closes = trending_closes(60)
    closes[-1] = close
    return recent_bars(closes, symbol=BAD)


def _two_symbol_service(bad_close: float) -> FakePriceService:
    service = FakePriceService()
    service.seed(BAD, _bad_latest_bars(bad_close))
    service.seed(GOOD, recent_bars(trending_closes(60), symbol=GOOD))
    return service


def _hold_symbol(store: PositionStore, symbol: str) -> None:
    store.create(
        PositionInput(
            symbol=symbol,
            market="TW",
            quantity=Decimal(1000),
            avg_cost=Decimal(100),
            currency="TWD",
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            note=None,
        )
    )


def _bad_symbol_rules() -> dict[str, dict[str, Any]]:
    return {
        # Would fire on a close of 0 or -1 if the price got through.
        "price": price_rule(above=False, threshold=150.0, symbol=BAD),
        # Would fire on the bad bar's drawdown (-100% or worse) if the signal
        # layer were run on it -- the reason signals are withheld, not computed.
        "signal": signal_rule(field="drawdown.current", op="lt", value=-0.5, symbol=BAD),
        "per_trade_loss": limit_rule(limit_id="per_trade_loss", symbol=BAD),
        "any_limit": limit_rule(limit_id="any", symbol=BAD),
    }


def _good_symbol_rules() -> list[dict[str, Any]]:
    return [
        price_rule(above=True, threshold=1.0, symbol=GOOD),
        signal_rule(field="rsi14.last", op="gt", value=0.0, symbol=GOOD),
        limit_rule(limit_id="any", symbol=GOOD),
    ]


def _loader_for(
    service: FakePriceService,
    positions: PositionStore,
    *,
    fx_provider: FxRateProvider | None = None,
) -> Callable[[str, Market], SymbolSnapshot]:
    valuator = PositionValuator(
        market_services={"TW": service}, fx_provider=UnavailableFxProvider()
    )

    def load(symbol: str, market: Market) -> SymbolSnapshot:
        return build_snapshot(
            symbol,
            market,
            resolver={"TW": service},
            store=positions,
            valuator=valuator,
            budget=RiskBudget(),
            fx_provider=fx_provider,
            net_worth=reported_net_worth(10_000_000.0),
        )

    return load


def _comparable(result: EvaluationResult) -> list[tuple[str, str | None, str | None]]:
    return [
        (outcome.status, outcome.reason, outcome.event.message if outcome.event else None)
        for outcome in result.outcomes
    ]


@pytest.mark.parametrize("bad_close", UNUSABLE_LATEST_CLOSES)
def test_an_unusable_latest_close_withholds_signals_and_the_price(
    store: PositionStore, monkeypatch: pytest.MonkeyPatch, bad_close: float
) -> None:
    import app.alerts.snapshot as snapshot_module

    def must_not_run(*_args: object, **_kwargs: object) -> dict[str, Any]:
        raise AssertionError("compute_signals ran on an unusable latest close")

    monkeypatch.setattr(snapshot_module, "compute_signals", must_not_run)
    _hold_symbol(store, GOOD)
    service = _two_symbol_service(bad_close)
    snap = _loader_for(service, store)(BAD, "TW")

    assert snap.signals == {}
    # Kept raw, so the engine's own guard names the price on a price rule.
    assert snap.close == bad_close
    assert snap.as_of == date.today().isoformat()
    caps = {check.id: check.status for check in snap.limits}
    # The price-based cap is not guessed; the book-level caps still answer.
    assert caps["per_trade_loss"] == "not_evaluable"
    assert caps["single_position_weight"] == "passed"


@pytest.mark.parametrize("bad_close", UNUSABLE_LATEST_CLOSES)
def test_an_unusable_latest_close_skips_that_symbol_and_spares_the_rest(
    store: PositionStore, tmp_path: Path, bad_close: float
) -> None:
    _hold_symbol(store, GOOD)
    service = _two_symbol_service(bad_close)
    load = _loader_for(service, store)
    now = datetime(2026, 10, 6, 6, 0, tzinfo=UTC)

    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    bad_ids = {name: add_rule(alerts, payload).id for name, payload in _bad_symbol_rules().items()}
    bad_ids["beta"] = insert_legacy_signal_rule(alerts.db_path, field="beta.value", symbol=BAD)
    for payload in _good_symbol_rules():
        add_rule(alerts, payload)

    result = evaluate_alerts(alerts, load, now=now)

    outcomes = {outcome.rule_id: outcome for outcome in result.outcomes}
    assert outcomes[bad_ids["price"]].status == "skipped"
    assert outcomes[bad_ids["price"]].reason == NO_CLOSE_REASON
    assert outcomes[bad_ids["signal"]].status == "skipped"
    assert outcomes[bad_ids["signal"]].reason == NO_SIGNALS_REASON
    # ADR-0021 K-6: the permanent cause still wins over the empty signal layer.
    assert outcomes[bad_ids["beta"]].status == "skipped"
    assert outcomes[bad_ids["beta"]].reason == BETA_W2_REASON
    per_trade = outcomes[bad_ids["per_trade_loss"]]
    assert per_trade.status == "skipped"
    assert (per_trade.reason or "").startswith("監看的上限（")
    assert outcomes[bad_ids["any_limit"]].status == "quiet"
    assert outcomes[bad_ids["any_limit"]].reason == ANY_LIMIT_QUIET_REASON
    assert all(event.symbol != BAD for event in result.events)

    # The healthy symbol reads exactly as it does on a tick without the bad one.
    baseline_store = AlertStore(db_path=tmp_path / "baseline.db")
    for payload in _good_symbol_rules():
        add_rule(baseline_store, payload)
    baseline = evaluate_alerts(baseline_store, load, now=now)
    good_only = EvaluationResult(
        as_of=result.as_of,
        evaluated=len(baseline.outcomes),
        events=[event for event in result.events if event.symbol == GOOD],
        outcomes=[o for o in result.outcomes if o.rule_id not in set(bad_ids.values())],
    )
    assert _comparable(good_only) == _comparable(baseline)
    assert [outcome.status for outcome in baseline.outcomes][:2] == ["fired", "fired"]


def _cached_layer(service: FakePriceService) -> None:
    service.status = DataStatus.CACHED_STALE
    service.source = "finmind"


def _data_layer_sentence(service: FakePriceService) -> None:
    service.reason = "這段日線資料由多個來源拼接（finmind、twse），每筆保留原本的來源；..."


def _foreign_currency(service: FakePriceService) -> None:
    closes = trending_closes(60)
    closes[-1] = float(service.bars[BAD][-1].close)
    service.seed(BAD, recent_bars(closes, symbol=BAD, currency="USD"))


@pytest.mark.parametrize(
    "degrade",
    [
        pytest.param(_cached_layer, id="cached-layer"),
        pytest.param(_data_layer_sentence, id="data-layer-sentence"),
        pytest.param(_foreign_currency, id="non-twd"),
    ],
)
@pytest.mark.parametrize("bad_close", UNUSABLE_LATEST_CLOSES)
def test_an_unusable_latest_close_names_no_unrelated_note_on_a_signal_rule(
    store: PositionStore,
    tmp_path: Path,
    bad_close: float,
    degrade: Callable[[FakePriceService], None],
) -> None:
    """風控 R-B1: on A′ the signals are withheld for the close, so a cache, data
    layer or FX note on the snapshot must not be read as the skip's cause."""
    _hold_symbol(store, GOOD)
    service = _two_symbol_service(bad_close)
    degrade(service)
    load = _loader_for(service, store)
    # Precondition: the snapshot does carry an unrelated note for the engine to ignore.
    assert load(BAD, "TW").reason

    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    signal = add_rule(alerts, _bad_symbol_rules()["signal"]).id
    result = evaluate_alerts(alerts, load, now=datetime(2026, 10, 6, 6, 0, tzinfo=UTC))

    [outcome] = [o for o in result.outcomes if o.rule_id == signal]
    assert outcome.status == "skipped"
    assert outcome.reason == NO_SIGNALS_REASON


@pytest.mark.parametrize("bad_close", UNUSABLE_LATEST_CLOSES)
def test_the_manual_tick_answers_200_on_an_unusable_latest_close(
    api_harness: ApiHarness, bad_close: float
) -> None:
    client = api_harness.client
    api_harness.price_service.seed(BAD, _bad_latest_bars(bad_close))
    api_harness.price_service.seed(GOOD, recent_bars(trending_closes(60), symbol=GOOD))
    assert client.post("/api/positions", json=position_payload(symbol=GOOD)).status_code == 201
    bad_ids = {
        name: client.post("/api/alerts", json=payload).json()["id"]
        for name, payload in _bad_symbol_rules().items()
    }
    bad_ids["beta"] = insert_legacy_signal_rule(
        api_harness.alerts.db_path, field="beta.value", symbol=BAD
    )
    good_ids = [
        client.post("/api/alerts", json=payload).json()["id"] for payload in _good_symbol_rules()
    ]

    response = client.post("/api/alerts/evaluate")

    assert response.status_code == 200
    outcomes = {outcome["rule_id"]: outcome for outcome in response.json()["outcomes"]}
    assert outcomes[bad_ids["price"]]["status"] == "skipped"
    assert outcomes[bad_ids["price"]]["reason"] == NO_CLOSE_REASON
    assert outcomes[bad_ids["signal"]]["status"] == "skipped"
    assert outcomes[bad_ids["beta"]]["reason"] == BETA_W2_REASON
    assert outcomes[bad_ids["per_trade_loss"]]["status"] == "skipped"
    assert outcomes[bad_ids["any_limit"]]["status"] == "quiet"
    assert outcomes[bad_ids["any_limit"]]["reason"] == ANY_LIMIT_QUIET_REASON_NO_NET_WORTH
    assert outcomes[good_ids[0]]["status"] == "fired"
    events = client.get("/api/alerts/events").json()["items"]
    assert events and all(event["symbol"] == GOOD for event in events)


def test_a_held_symbol_with_a_negative_close_is_not_a_load_failure(
    store: PositionStore, tmp_path: Path
) -> None:
    """F-1: the portfolio valuator no longer values a *held* symbol at a negative
    close -- it is unvalued, exactly like a holding with no bar -- so the
    snapshot builds and the engine's per-symbol isolation (方案 B) is not what
    keeps the tick alive any more. The rules still skip for the same reason."""
    _hold_symbol(store, BAD)
    _hold_symbol(store, GOOD)
    service = _two_symbol_service(-1.0)
    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    price = add_rule(alerts, price_rule(above=False, threshold=150.0, symbol=BAD))
    good = add_rule(alerts, price_rule(above=True, threshold=1.0, symbol=GOOD))

    result = evaluate_alerts(alerts, _loader_for(service, store), cooldown_minutes=0)

    assert result.load_failures == 0
    outcomes = {outcome.rule_id: outcome for outcome in result.outcomes}
    assert outcomes[price.id].status == "skipped"
    assert outcomes[price.id].reason == NO_CLOSE_REASON
    assert outcomes[good.id].status == "fired"


# --- risk_limit, every watched cap unevaluated: only a failed conversion follows
#
# 2026-10-07 任務單「risk_limit 全部 not_evaluable 時 skipped 句尾只接匯率失敗成因」,
# 方案 (A). Through the real snapshot builder, because the defect was the join
# ``build_snapshot`` makes: the skip used to end with all of ``reason`` (layer
# note, data-layer sentence, applied-rate note), most of which is no cause.

SPLICED = "這段日線資料由多個來源拼接（finmind、twse），每筆保留原本的來源；..."
CACHED_LAYER_NOTE = "資料來自 cached_stale 層（finmind）。"

#: The three failure sentences as ``build_book_context`` formats them for a USD
#: holding in each set-up below: ``(bar currency, fx provider, sentence)``.
FX_FAILURES = [
    pytest.param(
        "USD",
        UnavailableFxProvider(),
        FX_UNAVAILABLE_NOTE.format(
            currency="USD",
            pair="USDTWD",
            status="unavailable",
            source=UnavailableFxProvider.source_id,
            as_of="未知",
        ),
        id="no-usable-rate",
    ),
    # Bars in TWD resolve no quote at all, but the holding needs USDTWD.
    pytest.param("TWD", StubFxProvider(), NO_FX_QUOTE_NOTE.format(currency="USD"), id="no-quote"),
    pytest.param(
        "JPY",
        StubFxProvider(),
        FX_PAIR_MISMATCH_NOTE.format(currency="USD", expected="USDTWD", pair="JPYTWD"),
        id="pair-mismatch",
    ),
]

NON_PRICE_LIMIT_IDS = [
    "kelly_fraction",
    "sector_weight",
    "gross_exposure",
    "single_position_weight",
]


def _unevaluable_skip(limit_id: str) -> str:
    """The existing main sentence of an all-unevaluated skip, verbatim."""
    ids = LIMIT_IDS if limit_id == "any" else (limit_id,)
    names = "、".join(LIMIT_NAMES[i] for i in ids)
    return f"監看的上限（{names}）缺少輸入，無法判定是否違反。"


def _degraded_service(bar_currency: str) -> FakePriceService:
    """Usable bars served from a stale cache, with the data layer's own sentence."""
    service = _price_service(bar_currency)
    service.status = DataStatus.CACHED_STALE
    service.source = "finmind"
    service.reason = SPLICED
    return service


def _plain_loader(
    service: FakePriceService, positions: PositionStore, fx_provider: FxRateProvider | None
) -> Callable[[str, Market], SymbolSnapshot]:
    """No net worth, no Kelly pair, and a valuator that cannot convert USD -- so
    every cap of a USD holding is unevaluable whatever the snapshot's own rate."""
    valuator = PositionValuator(
        market_services={"TW": service}, fx_provider=UnavailableFxProvider()
    )

    def load(symbol: str, market: Market) -> SymbolSnapshot:
        return build_snapshot(
            symbol,
            market,
            resolver={"TW": service},
            store=positions,
            valuator=valuator,
            budget=RiskBudget(),
            fx_provider=fx_provider,
        )

    return load


def _limit_reason(
    alerts: AlertStore, load: Callable[[str, Market], SymbolSnapshot], limit_id: str
) -> str | None:
    rule = add_rule(alerts, limit_rule(limit_id=limit_id))
    result = evaluate_alerts(alerts, load, now=datetime(2026, 10, 7, 6, 0, tzinfo=UTC))
    [outcome] = [o for o in result.outcomes if o.rule_id == rule.id]
    assert outcome.status == "skipped"
    return outcome.reason


@pytest.mark.parametrize("limit_id", ["per_trade_loss", "any"])
@pytest.mark.parametrize(("bar_currency", "fx_provider", "failure"), FX_FAILURES)
def test_a_failed_conversion_is_the_only_tail_of_a_price_cap_skip(
    store: PositionStore,
    tmp_path: Path,
    bar_currency: str,
    fx_provider: FxRateProvider,
    failure: str,
    limit_id: str,
) -> None:
    """驗收 1: the failure sentence verbatim, and nothing of the layer note or the
    data layer's sentence that ``reason`` also carries."""
    _hold(store, "USD")
    load = _plain_loader(_degraded_service(bar_currency), store, fx_provider)
    snap = load("2330", "TW")
    # Preconditions: a usable close, every cap unevaluated, and the joined
    # ``reason`` exactly as before (K-2) -- it still holds all three parts.
    assert snap.close is not None and snap.close > 0
    assert {check.status for check in snap.limits} == {"not_evaluable"}
    assert snap.reason == f"{CACHED_LAYER_NOTE} {SPLICED} {failure}"
    assert snap.price_cap_cause == failure

    reason = _limit_reason(AlertStore(db_path=tmp_path / "alerts.db"), load, limit_id)

    assert reason == f"{_unevaluable_skip(limit_id)} {failure}"
    assert "資料來自" not in (reason or "")
    assert SPLICED not in (reason or "")


@pytest.mark.parametrize("limit_id", ["per_trade_loss", "any"])
def test_an_applied_rate_is_not_given_as_the_cause_of_a_skip(
    store: PositionStore, tmp_path: Path, limit_id: str
) -> None:
    """驗收 2 (a): the snapshot's own rate was applied (the valuator's was not,
    so the caps are still unevaluable); its sentence is no cause, nor the layer's."""
    _hold(store, "USD")
    load = _plain_loader(_degraded_service("USD"), store, StubFxProvider())
    snap = load("2330", "TW")
    assert {check.status for check in snap.limits} == {"not_evaluable"}
    assert snap.price_cap_cause is None
    applied_head = FX_APPLIED_NOTE.split("{", 1)[0]
    assert applied_head in (snap.reason or "")  # precondition: there is one to leak

    reason = _limit_reason(AlertStore(db_path=tmp_path / "alerts.db"), load, limit_id)

    assert reason == _unevaluable_skip(limit_id)
    for unwanted in (applied_head, "換算為台幣", "資料來自", SPLICED):
        assert unwanted not in (reason or "")


@pytest.mark.parametrize(
    "degrade",
    [
        pytest.param(_cached_layer, id="cached-layer"),
        pytest.param(_data_layer_sentence, id="data-layer-sentence"),
    ],
)
def test_a_twd_symbol_skip_quotes_no_data_layer_note(
    store: PositionStore, tmp_path: Path, degrade: Callable[[FakePriceService], None]
) -> None:
    """驗收 2 (b): no holdings, so no equity and every cap is unevaluable; the
    cache or splice sentence in ``reason`` is not why."""
    service = _price_service("TWD")
    degrade(service)
    load = _plain_loader(service, store, None)
    snap = load("2330", "TW")
    assert {check.status for check in snap.limits} == {"not_evaluable"}
    assert snap.reason and snap.price_cap_cause is None

    reason = _limit_reason(AlertStore(db_path=tmp_path / "alerts.db"), load, "any")

    assert reason == _unevaluable_skip("any")
    assert "資料來自" not in (reason or "")
    assert SPLICED not in (reason or "")


@pytest.mark.parametrize("limit_id", NON_PRICE_LIMIT_IDS)
@pytest.mark.parametrize(("bar_currency", "fx_provider", "failure"), FX_FAILURES)
def test_a_failed_conversion_is_not_the_cause_of_a_cap_that_reads_no_price(
    store: PositionStore,
    tmp_path: Path,
    bar_currency: str,
    fx_provider: FxRateProvider,
    failure: str,
    limit_id: str,
) -> None:
    """驗收 2 (c): the scope gate -- these caps were not left out for the rate."""
    _hold(store, "USD")
    load = _plain_loader(_degraded_service(bar_currency), store, fx_provider)
    assert load("2330", "TW").price_cap_cause == failure

    reason = _limit_reason(AlertStore(db_path=tmp_path / "alerts.db"), load, limit_id)

    assert reason == _unevaluable_skip(limit_id)
    for unwanted in ("無法取得匯率換算", "匯率", "資料來自", SPLICED):
        assert unwanted not in (reason or "")


def test_a_holding_in_two_currencies_has_no_price_cap_cause(store: PositionStore) -> None:
    # K-1: no single rate applies, and ``book.fx_note`` is None for that case.
    _hold(store, "USD")
    _hold(store, "TWD")
    snap = _snapshot(store, currency="USD", fx_provider=UnavailableFxProvider())
    assert snap.price_cap_cause is None


@pytest.mark.parametrize(
    ("currency", "fx_provider"),
    [
        pytest.param("TWD", None, id="twd"),
        pytest.param("TWD", StubFxProvider(), id="twd-with-provider"),
        pytest.param("USD", StubFxProvider(), id="usd-applied"),
    ],
)
def test_no_conversion_needed_or_one_applied_carries_no_price_cap_cause(
    store: PositionStore, currency: str, fx_provider: FxRateProvider | None
) -> None:
    # K-1: only a *failed* conversion is a cause; FX_APPLIED_NOTE never is.
    _hold(store, currency)
    assert _snapshot(store, currency=currency, fx_provider=fx_provider).price_cap_cause is None


def _fx_case(service: FakePriceService, fx: str) -> FxRateProvider | None:
    """Re-seed the unusable symbol for one currency set-up; the provider to use."""
    if fx == "twd":
        return None
    _foreign_currency(service)
    return StubFxProvider() if fx == "applied" else None


@pytest.mark.parametrize("fx", ["twd", "applied", "failed"])
@pytest.mark.parametrize("cached", [False, True], ids=["fresh", "cached"])
@pytest.mark.parametrize("bad_close", UNUSABLE_LATEST_CLOSES)
def test_an_unusable_close_keeps_every_cause_off_a_risk_limit_skip(
    store: PositionStore, tmp_path: Path, bad_close: float, cached: bool, fx: str
) -> None:
    """驗收 3: on A′ the price and ATR were withheld for the close, so neither a
    failed conversion nor any other note follows the main sentence; the other
    rule types and the S-B2 quiet read exactly as before."""
    _hold_symbol(store, GOOD)
    service = _two_symbol_service(bad_close)
    if cached:
        _cached_layer(service)
    fx_provider = _fx_case(service, fx)
    load = _loader_for(service, store, fx_provider=fx_provider)
    snap = load(BAD, "TW")
    assert snap.close == bad_close
    # Preconditions: the failed case does carry a cause for the gate to hold back.
    assert (snap.price_cap_cause is not None) == (fx == "failed")

    alerts = AlertStore(db_path=tmp_path / "alerts.db")
    ids = {name: add_rule(alerts, payload).id for name, payload in _bad_symbol_rules().items()}
    result = evaluate_alerts(alerts, load, now=datetime(2026, 10, 7, 6, 0, tzinfo=UTC))
    outcomes = {outcome.rule_id: (outcome.status, outcome.reason) for outcome in result.outcomes}

    assert outcomes[ids["per_trade_loss"]] == ("skipped", _unevaluable_skip("per_trade_loss"))
    assert outcomes[ids["price"]] == ("skipped", NO_CLOSE_REASON)
    assert outcomes[ids["signal"]] == ("skipped", NO_SIGNALS_REASON)
    assert outcomes[ids["any_limit"]] == ("quiet", ANY_LIMIT_QUIET_REASON)
    assert result.events == []
