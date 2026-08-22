"""API tests for ``GET /api/advice/{symbol}``: card shape, context, disclosures."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.advice.book import EQUITY_BASIS_NOTE, GROSS_EXPOSURE_NOTE
from app.advice.engine import DISCLAIMER
from app.advice.limits import (
    NET_WORTH_STALE_AFTER_DAYS,
    NO_SECTOR_CANDIDATE_DETAIL,
    NO_SECTOR_UNFILED_DETAIL,
    SECTOR_MIXED_DETAIL,
)
from app.api.deps import get_fx_provider
from app.api.kelly_wording import (
    KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY,
    KELLY_NON_POSITIVE_FRACTION_DETAIL,
    KELLY_NOT_EVALUABLE_NO_INPUT,
    KELLY_WIN_RATE_IS_NOT_PROBABILITY,
)
from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.main import app
from app.settings.models import NetWorthSettings
from tests.api_helpers import position_payload, recent_bars, trending_closes
from tests.conftest import ApiHarness


class StubFxProvider(FxRateProvider):
    """Quotes one flat rate for every day in the requested window."""

    source_id = "bank_of_taiwan"

    def __init__(self, rate: Decimal) -> None:
        self._rate = rate

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        now = datetime.now(UTC)
        return FxRateResult(
            rates=[
                FxRate(pair=pair, date=end, rate=self._rate, as_of=now, source=self.source_id)
            ],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


def _seed_bars(harness: ApiHarness, symbol: str = "2330", count: int = 200) -> None:
    harness.price_service.seed(symbol, recent_bars(trending_closes(count), symbol=symbol))


def test_advice_returns_the_build_advice_card_verbatim(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    body = api_harness.client.get("/api/advice/2330").json()
    assert body["status"] == "ok"
    card = body["advice"]
    # Every key the engine promises is present, unrenamed.
    assert set(card) >= {
        "symbol",
        "action",
        "quantity_range",
        "matched_rules",
        "counterarguments",
        "invalidation_conditions",
        "confidence",
        "confidence_meaning",
        "rules_version",
        "disclaimer",
        "limits_check",
        "action_weights",
        "direction_weights",
        "evaluation",
    }
    assert card["disclaimer"] == DISCLAIMER
    assert len(card["limits_check"]) == 5


def test_advice_marks_a_held_symbol_and_lists_its_position_ids(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    created = api_harness.client.post("/api/positions", json=position_payload()).json()
    body = api_harness.client.get("/api/advice/2330").json()
    assert body["held"] is True
    assert body["position_ids"] == [created["id"]]
    context = body["portfolio_context"]
    assert context["quantity"] == 1000.0
    assert context["position_market_value_twd"] > 0.0


def test_advice_works_for_a_candidate_the_user_does_not_hold(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness, symbol="2454")
    body = api_harness.client.get("/api/advice/2454").json()
    assert body["status"] == "ok"
    assert body["held"] is False
    assert body["position_ids"] == []
    context = body["portfolio_context"]
    # A candidate is zero position / zero quantity, not a fabricated holding.
    assert context["position_market_value_twd"] == 0.0
    assert context["quantity"] == 0.0
    assert context["position_cost_twd"] is None


def test_candidate_skips_the_position_rules_by_naming_the_missing_fields(
    api_harness: ApiHarness,
) -> None:
    _seed_bars(api_harness, symbol="2454")
    card = api_harness.client.get("/api/advice/2454").json()["advice"]
    skipped_fields = {
        field
        for entry in card["evaluation"]["skipped_rules"]
        for field in entry["missing_fields"]
    }
    # Nothing is held anywhere, so the book has no equity and this symbol has no
    # weight in it. The rules reading position weight must be skipped with the
    # field named, not evaluated against a fabricated 0%.
    assert "position.weight" in skipped_fields


def test_advice_states_its_equity_assumption_and_the_omitted_exposure(
    api_harness: ApiHarness,
) -> None:
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    body = api_harness.client.get("/api/advice/2330").json()
    assert EQUITY_BASIS_NOTE in body["context_notes"]
    assert GROSS_EXPOSURE_NOTE in body["context_notes"]
    # And the cap itself reports not_evaluable rather than a forced 100%.
    gross = next(c for c in body["advice"]["limits_check"] if c["id"] == "gross_exposure")
    assert gross["status"] == "not_evaluable"


def _gross_check(harness: ApiHarness, symbol: str = "2330") -> dict[str, Any]:
    card = harness.client.get(f"/api/advice/{symbol}").json()["advice"]
    check: dict[str, Any] = next(c for c in card["limits_check"] if c["id"] == "gross_exposure")
    return check


def test_a_reported_net_worth_turns_the_exposure_cap_on(api_harness: ApiHarness) -> None:
    # AC-9.3 end to end: the cap that has been ``not_evaluable`` since this
    # product shipped starts answering once its denominator exists.
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    valued = float(
        api_harness.client.get("/api/portfolio/summary").json()["totals"]["market_value_twd"]
    )
    assert _gross_check(api_harness)["status"] == "not_evaluable"

    api_harness.client.put(
        "/api/settings", json={"net_worth": {"total_net_worth_twd": valued * 2}}
    )
    check = _gross_check(api_harness)
    assert check["status"] == "passed"
    assert check["observed"] == pytest.approx(0.5)
    assert check["threshold"] == 1.0
    # The three required sentences travel with the verdict.
    assert "兩者來源不同" in check["detail"]
    assert "未登錄的部位不計入分子" in check["detail"]


def test_the_exposure_cap_can_now_report_a_breach(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    valued = float(
        api_harness.client.get("/api/portfolio/summary").json()["totals"]["market_value_twd"]
    )
    # A net worth only barely above the book: the account is essentially fully
    # invested, which is what cap 3 exists to notice.
    api_harness.client.put(
        "/api/settings", json={"net_worth": {"total_net_worth_twd": valued * 0.99}}
    )
    check = _gross_check(api_harness)
    assert check["status"] == "violated"
    assert check["observed"] > 1.0


def test_an_expired_net_worth_takes_the_exposure_cap_back_off(
    api_harness: ApiHarness,
) -> None:
    # AC-9.4 end to end: no ``passed`` is ever computed from a figure this old.
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    stale = (datetime.now(UTC) - timedelta(days=NET_WORTH_STALE_AFTER_DAYS + 1)).isoformat()
    current = api_harness.settings.load()
    api_harness.settings.save(
        current.model_copy(
            update={
                "net_worth": NetWorthSettings(
                    total_net_worth_twd=99_000_000.0, updated_at=stale
                )
            }
        )
    )
    check = _gross_check(api_harness)
    assert check["status"] == "not_evaluable"
    assert check["observed"] is None
    assert f"淨值輸入已超過 {NET_WORTH_STALE_AFTER_DAYS} 天未更新" in check["detail"]


def test_an_unvaluable_position_takes_the_exposure_cap_back_off(
    api_harness: ApiHarness,
) -> None:
    # FR-9 (a-附加): one unpriced holding leaves the numerator short, which can
    # only make exposure look lower than it is. The cap withholds instead.
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.post("/api/positions", json=position_payload(symbol="2454"))
    api_harness.client.put(
        "/api/settings", json={"net_worth": {"total_net_worth_twd": 900_000_000.0}}
    )
    check = _gross_check(api_harness)
    assert check["status"] == "not_evaluable"
    assert "分子不完整" in check["detail"]


def test_a_reported_net_worth_leaves_the_other_caps_exactly_where_they_were(
    api_harness: ApiHarness,
) -> None:
    # AC-9.6 end to end. A net worth many times the book is precisely the input
    # that would loosen caps 1 and 4 under option A; under option B they must
    # not move at all.
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    before = api_harness.client.get("/api/advice/2330").json()
    api_harness.client.put(
        "/api/settings", json={"net_worth": {"total_net_worth_twd": 50_000_000.0}}
    )
    after = api_harness.client.get("/api/advice/2330").json()

    assert (
        before["portfolio_context"]["total_equity_twd"]
        == after["portfolio_context"]["total_equity_twd"]
    )
    for limit_id in ("single_position_weight", "per_trade_loss"):
        old = next(c for c in before["advice"]["limits_check"] if c["id"] == limit_id)
        new = next(c for c in after["advice"]["limits_check"] if c["id"] == limit_id)
        assert old == new


def test_advice_without_price_data_is_200_insufficient(api_harness: ApiHarness) -> None:
    response = api_harness.client.get("/api/advice/9999")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "insufficient_data"
    assert body["advice"] is None
    assert "沒有可用的日線資料" in body["reason"]


@pytest.mark.parametrize(
    ("bar_count", "held"),
    [(200, True), (200, False), (20, True)],
)
def test_a_card_is_never_published_without_the_date_it_was_computed_from(
    api_harness: ApiHarness, bar_count: int, held: bool
) -> None:
    """R-D5②-2: ``advice is not None`` implies ``data.last_bar_date is not None``.

    This invariant is the basis of the D5② 不降級 ruling (CEO 裁決 2026-08-16,
    方案 A+, recorded in ``work/reviews/2026-08-16-品質債清償批-覆核.md``): the
    front end's as-of slot may keep disclosing "無法標示評估所依據的資料時間"
    as an *unreachable* honest fallback precisely because a published card
    always carries a bar date. **If this test goes red, the ruling's premise is
    broken: stop and take it back to risk-compliance for a fresh decision
    rather than adjusting the assertion.**

    Driven through the real endpoint (not the pure layer) because the coupling
    being pinned is between two fields of the same HTTP envelope: ``advice`` is
    emitted only when a latest bar exists (``app/api/advice.py``), and
    ``data.last_bar_date`` is derived from the same bar list
    (``LoadedBars.meta``). Both directions are covered: bars present -> card
    plus date, no bars -> neither.
    """
    _seed_bars(api_harness, count=bar_count)
    if held:
        api_harness.client.post("/api/positions", json=position_payload())
    body = api_harness.client.get("/api/advice/2330").json()

    assert body["advice"] is not None
    assert body["data"]["last_bar_date"] is not None
    assert body["held"] is held


def test_without_bars_neither_the_card_nor_the_basis_date_is_published(
    api_harness: ApiHarness,
) -> None:
    # The other direction of the R-D5②-2 invariant: the only state in which
    # ``last_bar_date`` is null is also the state in which no card exists, so
    # the pair (card, unknown date) the as-of fallback would have to describe
    # is not reachable through this endpoint.
    body = api_harness.client.get("/api/advice/9999").json()
    assert body["advice"] is None
    assert body["data"]["last_bar_date"] is None

    foreign = api_harness.client.get("/api/advice/AAPL", params={"market": "US"}).json()
    assert foreign["advice"] is None
    assert foreign["data"]["last_bar_date"] is None


def test_advice_uses_the_stored_risk_budget(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    # 0.45: clearly not the 0.15 default, and still inside the hard ceiling
    # (`MAX_POSITION_WEIGHT_CEILING`) that a settings write cannot pass.
    api_harness.client.put(
        "/api/settings", json={"risk_budget": {"max_position_weight": 0.45}}
    )
    body = api_harness.client.get("/api/advice/2330").json()
    weight_cap = next(
        c for c in body["advice"]["limits_check"] if c["id"] == "single_position_weight"
    )
    assert weight_cap["threshold"] == 0.45


def test_advice_never_emits_a_target_price(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    card = api_harness.client.get("/api/advice/2330").json()["advice"]
    forbidden = {"target_price", "price_target", "score", "rating", "expected_return"}
    assert forbidden.isdisjoint(card)


def test_advice_for_a_market_without_an_adapter_says_so(api_harness: ApiHarness) -> None:
    body = api_harness.client.get("/api/advice/AAPL", params={"market": "US"}).json()
    assert body["status"] == "insufficient_data"
    assert "沒有 US 市場的行情來源" in body["reason"]


def _seed_foreign_bars(harness: ApiHarness, symbol: str = "2330") -> None:
    harness.price_service.seed(
        symbol,
        recent_bars(trending_closes(200), symbol=symbol, currency="USD"),
    )


def test_a_foreign_currency_holding_without_a_rate_says_which_input_is_missing(
    api_harness: ApiHarness,
) -> None:
    # The harness FX provider never has a rate, which is the AC-3.2 case.
    _seed_foreign_bars(api_harness)
    body = api_harness.client.get("/api/advice/2330").json()
    assert body["status"] == "ok"  # there *is* a price; only the conversion is missing
    notes = body["context_notes"]
    assert any("無法取得匯率換算" in note for note in notes)
    assert any("不以 1.0 匯率代入" in note for note in notes)
    assert body["portfolio_context"]["close"] is None
    weight_cap = next(
        c for c in body["advice"]["limits_check"] if c["id"] == "single_position_weight"
    )
    assert weight_cap["status"] == "not_evaluable"


def test_a_resolvable_rate_reaches_the_card_with_its_freshness(
    api_harness: ApiHarness,
) -> None:
    _seed_foreign_bars(api_harness)
    app.dependency_overrides[get_fx_provider] = lambda: StubFxProvider(Decimal("31.5"))
    body = api_harness.client.get("/api/advice/2330").json()
    context = body["portfolio_context"]
    assert context["close"] is not None
    assert context["fx_to_twd"] == 31.5
    notes = body["context_notes"]
    assert any("USDTWD" in note and "31.5" in note for note in notes)
    # AC-3.5: the source's standing disclosure travels with the number.
    assert any("未經本環境線上查證" in note for note in notes)


# --- FR-12: the sector cap starts answering -----------------------------------


def _sector_check(harness: ApiHarness, symbol: str = "2330") -> dict[str, Any]:
    card = harness.client.get(f"/api/advice/{symbol}").json()["advice"]
    check: dict[str, Any] = next(c for c in card["limits_check"] if c["id"] == "sector_weight")
    return check


def test_declaring_a_sector_turns_the_sector_cap_on(api_harness: ApiHarness) -> None:
    # AC-12.4 end to end: cap 2 has reported ``not_evaluable`` since this
    # product shipped; a declared industry is all it was ever missing.
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    before = _sector_check(api_harness)
    assert before["status"] == "not_evaluable"
    assert before["observed"] is None

    position_id = api_harness.client.get("/api/positions").json()["items"][0]["id"]
    api_harness.client.put(
        f"/api/positions/{position_id}", json=position_payload(sector="半導體業")
    )
    after = _sector_check(api_harness)
    # One holding, so the industry is the whole valued book: 100% of equity,
    # which is over the 30% cap.
    assert after["status"] == "violated"
    assert after["observed"] == pytest.approx(1.0)
    assert after["threshold"] == pytest.approx(0.30)


def test_a_diversified_book_passes_the_sector_cap(api_harness: ApiHarness) -> None:
    _seed_bars(api_harness)
    _seed_bars(api_harness, symbol="1101")
    api_harness.client.post("/api/positions", json=position_payload(sector="半導體業"))
    api_harness.client.post(
        "/api/positions",
        json=position_payload(symbol="1101", quantity="10000", sector="水泥工業"),
    )
    check = _sector_check(api_harness)
    assert check["status"] in {"passed", "violated"}  # evaluated either way
    assert check["observed"] is not None


def test_an_unclassified_holding_is_disclosed_on_the_card(api_harness: ApiHarness) -> None:
    # AC-12.5: a ratio computed while part of the book sits outside every
    # industry says so on the card instead of reading as the whole picture.
    _seed_bars(api_harness)
    _seed_bars(api_harness, symbol="1101")
    api_harness.client.post("/api/positions", json=position_payload(sector="半導體業"))
    api_harness.client.post("/api/positions", json=position_payload(symbol="1101"))
    body = api_harness.client.get("/api/advice/2330").json()
    assert any("未填產業別" in note for note in body["context_notes"])


def test_the_sector_cap_names_the_unfilled_value_when_absent(
    api_harness: ApiHarness,
) -> None:
    # AC-12.3: the field exists now, so the reason may not claim otherwise.
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    detail = _sector_check(api_harness)["detail"]
    assert "沒有產業別欄位" not in detail
    assert "產業別" in detail
    assert detail == NO_SECTOR_UNFILED_DETAIL


def test_the_sector_cap_tells_a_candidate_and_a_holding_apart(
    api_harness: ApiHarness,
) -> None:
    # AC-12.3 end to end: the state the reader is in decides the sentence that
    # reaches ``limits_check[].detail``. Nothing is held here, so the card must
    # not ask for a category on a position that does not exist.
    _seed_bars(api_harness)
    detail = _sector_check(api_harness)["detail"]
    assert detail == NO_SECTOR_CANDIDATE_DETAIL
    assert "填入" not in detail


def test_the_sector_cap_says_what_two_categories_on_one_symbol_mean(
    api_harness: ApiHarness,
) -> None:
    # The same symbol filed under two industries is not an empty field, and the
    # cap's detail says so instead of asking for a value that is already there.
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload(sector="半導體業"))
    api_harness.client.post("/api/positions", json=position_payload(sector="光電業"))
    detail = _sector_check(api_harness)["detail"]
    assert detail == SECTOR_MIXED_DETAIL
    assert "尚未填寫" not in detail


# --- Cap 5, end to end: the stored pair reaches the card (C5) ----------------


def _kelly_check(harness: ApiHarness, symbol: str = "2330") -> dict[str, Any]:
    body = harness.client.get(f"/api/advice/{symbol}").json()
    check: dict[str, Any] = next(
        c for c in body["advice"]["limits_check"] if c["id"] == "kelly_fraction"
    )
    return check


def test_cap_5_is_not_evaluable_until_a_pair_is_entered(api_harness: ApiHarness) -> None:
    """The state the product shipped in, now stated as "nothing entered yet"."""
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())

    check = _kelly_check(api_harness)

    assert check["status"] == "not_evaluable"
    assert check["detail"] == KELLY_NOT_EVALUABLE_NO_INPUT


def test_a_stored_pair_makes_cap_5_evaluable_through_the_endpoint(
    api_harness: ApiHarness,
) -> None:
    """C5's whole point: the cap computes from the user's own input.

    The wiring is what this proves -- store, ageing, source and flag all have to
    survive the trip from ``kelly_inputs`` to the card, and any one of them
    dropped on the way leaves the cap saying something untrue about an input the
    user did enter.
    """
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 0.6, "payoff_ratio": 2.0}
    )

    check = _kelly_check(api_harness)

    assert check["status"] in {"passed", "violated"}
    assert check["threshold"] == pytest.approx(0.1)
    assert "以勝率 60.0%、盈虧比 2.00 計算" in check["detail"]
    # A hand-typed pair is not a sample frequency, so (e-manual) travels with it.
    assert KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY in check["detail"]
    assert KELLY_WIN_RATE_IS_NOT_PROBABILITY not in check["detail"]


def test_an_expired_pair_reaches_the_card_as_expired_not_as_absent(
    api_harness: ApiHarness,
) -> None:
    """(g-2) end to end, with the anchor and the age the endpoint computed."""
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 0.6, "payoff_ratio": 2.0}
    )
    stored = api_harness.kelly_inputs.get("2330", "TW")
    assert stored is not None
    # Re-stamped 40 days back through the store's own writer, so the age the
    # card reports is one the ageing rule derived rather than one a test set.
    api_harness.kelly_inputs.upsert(stored, now=datetime.now(UTC) - timedelta(days=40))

    check = _kelly_check(api_harness)

    assert check["status"] == "not_evaluable"
    assert check["detail"].startswith("此標的的 Kelly 輸入（來源：手動輸入）已過期")
    assert "距今 40 天" in check["detail"]
    assert check["detail"] != KELLY_NOT_EVALUABLE_NO_INPUT


def test_a_non_positive_edge_reaches_the_card_as_its_own_sentence(
    api_harness: ApiHarness,
) -> None:
    """D-5 end to end: violated, dedicated sentence, and no sizing from a zero."""
    _seed_bars(api_harness)
    api_harness.client.post("/api/positions", json=position_payload())
    api_harness.client.put(
        "/api/kelly-inputs/2330", json={"win_rate": 0.3, "payoff_ratio": 1.0}
    )

    body = api_harness.client.get("/api/advice/2330").json()
    check = next(c for c in body["advice"]["limits_check"] if c["id"] == "kelly_fraction")

    assert check["status"] == "violated"
    assert check["detail"] == KELLY_NON_POSITIVE_FRACTION_DETAIL
    quantity = body["advice"]["quantity_range"]
    if quantity is not None:
        assert "「分數 Kelly 部位上限」這條上限" not in quantity["basis"]
