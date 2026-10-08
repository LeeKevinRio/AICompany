"""Task RK-5, PR-RK5a: the open-date FX rate keeps its provenance.

* R5-1 / R5-10c: ``Valuation.fx_open`` is the **whole** ``FxInfo`` of the
  open-date lookup -- the second value of ``_latest_fx_on_or_before`` -- never
  a bare source id. A failed lookup is an ``UNAVAILABLE`` ``FxInfo``, not
  ``None``; only a TWD row, a row with no open date and the KX-A2 short-circuit
  carry ``None``, and none of those asks the FX source anything new.
* R5-2: the figures are untouched; the rate behind ``cost_twd`` is the one
  ``fx_open`` describes.
* R5-3 (O-5): ``fx_disclosures`` counts ``ok`` positions only, and still lists
  ``fx_now``'s sentence alone.
* R5-4: an ``ok`` position whose two rates come from two source ids logs one
  English WARNING per ``(pair, now source, open source)`` per ``build_summary``,
  naming the pair, both source ids and both rate dates -- nothing else.
* R5-10d: a currency/market mismatched row has ``fx_open=None``, never warns
  and never reaches ``fx_disclosures``.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.api.deps import get_valuator
from app.data.interface import DataStatus, Market
from app.data.providers.fx import FxRate, FxRateLadder, FxRateProvider, FxRateResult
from app.main import app
from app.portfolio import valuation
from app.portfolio.summary import build_summary, fx_disclosures_for
from app.portfolio.valuation import FxInfo, PositionValuator, Valuation
from app.positions.models import Currency, PositionInput
from app.positions.store import PositionStore
from app.services.fx_notes import SOURCE_NOTES
from tests.api_helpers import FakePriceService, recent_bars
from tests.conftest import ApiHarness

NOW = datetime(2026, 10, 8, 6, 0, tzinfo=UTC)
TODAY = NOW.date()
PAIR = "USDTWD"

#: Open dates, each landing on a different rung of a two-rung ladder.
OPEN_BANK = date(2025, 3, 3)
OPEN_BANK_LATER = date(2025, 4, 7)
OPEN_YAHOO = date(2025, 6, 2)
#: No rung publishes anything within the backtrack window of this one.
OPEN_NOWHERE = date(2024, 1, 2)

BANK = "bank_of_taiwan"
YAHOO = "yfinance_fx"
DECLINED = "此來源本次沒有這段期間的匯率。"

#: What each rung publishes: date -> rate.
BANK_DAYS = {OPEN_BANK: "30.5", OPEN_BANK_LATER: "30.75"}
YAHOO_DAYS = {TODAY: "32.1", OPEN_YAHOO: "29.8"}

LOGGER = "app.portfolio.summary"

FX_KEYS = {"pair", "as_of", "source", "data_status", "source_note", "is_within_ttl", "reason"}


class _Rung(FxRateProvider):
    """One rung of the FX ladder: answers on the days it holds, declines elsewhere."""

    source_id = "rung"
    days: Mapping[date, str] = {}

    def __init__(self) -> None:
        self.asks: list[tuple[str, date, date]] = []

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.asks.append((pair, start, end))
        rates = [
            FxRate(pair=pair, date=day, rate=Decimal(rate), as_of=NOW, source=self.source_id)
            for day, rate in sorted(self.days.items())
            if start <= day <= end
        ]
        if not rates:
            return FxRateResult(
                rates=[],
                status=DataStatus.UNAVAILABLE,
                as_of=NOW,
                source=self.source_id,
                reason=DECLINED,
            )
        return FxRateResult(rates=rates, status=DataStatus.FRESH, as_of=NOW, source=self.source_id)


class _BankRung(_Rung):
    source_id = BANK
    days = BANK_DAYS


class _YahooRung(_Rung):
    source_id = YAHOO
    days = YAHOO_DAYS


class _ByDateFx(FxRateProvider):
    """A single provider whose source id depends on the date asked about."""

    source_id = "by_date_fx"

    def __init__(self, answers: Mapping[date, tuple[str, str]]) -> None:
        self._answers = dict(answers)
        self.asks: list[tuple[str, date, date]] = []

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.asks.append((pair, start, end))
        published = sorted(day for day in self._answers if start <= day <= end)
        if not published:
            return FxRateResult(rates=[], status=DataStatus.UNAVAILABLE, as_of=NOW, source="none")
        day = published[-1]
        source, rate = self._answers[day]
        return FxRateResult(
            rates=[FxRate(pair=pair, date=day, rate=Decimal(rate), as_of=NOW, source=source)],
            status=DataStatus.FRESH,
            as_of=NOW,
            source=source,
        )


class _Ladder:
    """A real ``FxRateLadder`` over two counting rungs."""

    def __init__(self) -> None:
        self.bank = _BankRung()
        self.yahoo = _YahooRung()
        self.provider = FxRateLadder(primary=self.bank, backup=self.yahoo)


def _prices(*symbols: tuple[str, Market, str]) -> dict[Market, FakePriceService]:
    services: dict[Market, FakePriceService] = {"TW": FakePriceService(), "US": FakePriceService()}
    for symbol, market, close in symbols:
        services[market].seed(
            symbol, recent_bars([float(close)] * 5, symbol=symbol, market=market, end=TODAY)
        )
    return services


def _valuator(
    fx: FxRateProvider, services: Mapping[Market, FakePriceService] | None = None
) -> PositionValuator:
    priced = services if services is not None else _prices(("AAPL", "US", "150"))
    return PositionValuator(market_services=dict(priced), fx_provider=fx, clock=lambda: NOW)


def _hold(
    store: PositionStore,
    symbol: str = "AAPL",
    *,
    opened_at: date | None = OPEN_BANK,
    market: str = "US",
    currency: str = "USD",
    quantity: str = "10",
    avg_cost: str = "100",
) -> None:
    store.create(
        PositionInput(
            symbol=symbol,
            market=market,  # type: ignore[arg-type]
            quantity=Decimal(quantity),
            avg_cost=Decimal(avg_cost),
            currency=currency,  # type: ignore[arg-type]
            opened_at=opened_at,
            instrument_type="stock",
            note=None,
        ),
        now=NOW,
    )


def _store(tmp_path: Path, name: str = "positions.db") -> PositionStore:
    return PositionStore(db_path=tmp_path / name)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == LOGGER and record.levelno == logging.WARNING
    ]


def _mixed_line(*, open_source: str, open_as_of: date, now_source: str = YAHOO) -> str:
    return (
        "fx_now and fx_open sources differ within one book: "
        f"pair={PAIR} now_source={now_source} now_as_of={TODAY.isoformat()} "
        f"open_source={open_source} open_as_of={open_as_of.isoformat()}"
    )


# --- R5-1 / R5-10c: the whole FxInfo of the open-date lookup -----------------------


def test_r5_1_fx_open_is_the_whole_fx_info_of_the_open_date_lookup(tmp_path: Path) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, opened_at=OPEN_BANK)

    [valued] = _valuator(ladder.provider).value_all(store.list_all())

    result = valued.valuation
    assert result.status == "ok"
    assert result.fx_open == FxInfo(
        pair=PAIR,
        as_of=OPEN_BANK.isoformat(),
        source=BANK,
        data_status=DataStatus.FRESH,
        source_note=SOURCE_NOTES[BANK],
        is_within_ttl=None,
        reason=None,
    )
    # The very object the open-date lookup returns, not a reduction of it.
    oracle = _valuator(_Ladder().provider)._latest_fx_on_or_before(PAIR, OPEN_BANK)
    assert result.fx_open == oracle[1]
    assert result.fx_open is not None
    assert set(result.fx_open.model_dump()) == FX_KEYS
    # ``fx`` still describes fx_now alone, from its own lookup.
    assert result.fx is not None
    assert (result.fx.source, result.fx.as_of) == (YAHOO, TODAY.isoformat())
    assert result.fx.data_status is DataStatus.BACKUP


def test_r5_10c_a_yahoo_open_date_rate_is_labelled_backup(tmp_path: Path) -> None:
    """The ladder relabels its backup rung BACKUP (W5-T5's premise) and says why."""
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, opened_at=OPEN_YAHOO)

    [valued] = _valuator(ladder.provider).value_all(store.list_all())

    fx_open = valued.valuation.fx_open
    assert fx_open is not None
    assert fx_open.data_status is DataStatus.BACKUP
    assert (fx_open.source, fx_open.as_of) == (YAHOO, OPEN_YAHOO.isoformat())
    assert fx_open.source_note == SOURCE_NOTES[YAHOO]
    assert fx_open.reason is not None and fx_open.reason.startswith(f"主來源（{BANK}）")
    assert fx_open == _valuator(_Ladder().provider)._latest_fx_on_or_before(PAIR, OPEN_YAHOO)[1]


def test_r5_7_open_dates_on_different_sources_are_recorded_each(tmp_path: Path) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, "AAPL", opened_at=OPEN_BANK)
    _hold(store, "MSFT", opened_at=OPEN_YAHOO)
    services = _prices(("AAPL", "US", "150"), ("MSFT", "US", "300"))

    bank_row, yahoo_row = _valuator(ladder.provider, services).value_all(store.list_all())

    assert bank_row.valuation.fx_open is not None
    assert yahoo_row.valuation.fx_open is not None
    assert (bank_row.valuation.fx_open.source, bank_row.valuation.fx_open.data_status) == (
        BANK,
        DataStatus.FRESH,
    )
    assert (yahoo_row.valuation.fx_open.source, yahoo_row.valuation.fx_open.data_status) == (
        YAHOO,
        DataStatus.BACKUP,
    )
    # One fx_now per pass (the memo), so both rows share it.
    assert bank_row.valuation.fx == yahoo_row.valuation.fx


def test_r5_10c_a_failed_open_date_lookup_is_unavailable_not_none(tmp_path: Path) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, opened_at=OPEN_NOWHERE)

    [valued] = _valuator(ladder.provider).value_all(store.list_all())

    result = valued.valuation
    assert result.status == "insufficient_data"
    assert result.missing == ["fx_open"]
    assert result.fx_open is not None
    assert result.fx_open.data_status is DataStatus.UNAVAILABLE
    assert result.fx_open.as_of is None
    assert result.fx_open.source == "none"
    assert result.fx_open.source_note == ""
    assert result.fx_open.reason is not None
    assert (
        result.fx_open
        == _valuator(_Ladder().provider)._latest_fx_on_or_before(PAIR, OPEN_NOWHERE)[1]
    )
    assert valued.cost_twd is None


def test_r5_1_a_twd_position_has_no_fx_open_and_asks_nothing(tmp_path: Path) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, "2330", market="TW", currency="TWD", opened_at=OPEN_BANK, avg_cost="500")

    [valued] = _valuator(ladder.provider, _prices(("2330", "TW", "600"))).value_all(
        store.list_all()
    )

    assert valued.valuation.status == "ok"
    assert valued.valuation.fx is None
    assert valued.valuation.fx_open is None
    assert ladder.bank.asks == []
    assert ladder.yahoo.asks == []


def test_r5_1_no_open_date_means_no_fx_open_and_no_open_date_lookup(tmp_path: Path) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, opened_at=None)

    [valued] = _valuator(ladder.provider).value_all(store.list_all())

    result = valued.valuation
    assert result.status == "insufficient_data"
    assert result.missing == ["fx_open"]  # ADR-0023 Decision 4's reachable cause, unchanged
    assert result.fx_open is None
    assert result.fx is not None and result.fx.as_of == TODAY.isoformat()
    # fx_now alone was asked about; no date was invented for fx_open.
    assert [end for _, _, end in ladder.bank.asks] == [TODAY]


def test_r5_1_provider_asks_are_unchanged(tmp_path: Path) -> None:
    """One ask per (pair, date) per pass; a lone position still asks twice."""
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, "AAPL", opened_at=OPEN_BANK)
    _hold(store, "MSFT", opened_at=OPEN_BANK)
    _hold(store, "NVDA", opened_at=OPEN_YAHOO)
    _hold(store, "2330", market="TW", currency="TWD", opened_at=OPEN_BANK, avg_cost="500")
    services = _prices(
        ("AAPL", "US", "150"), ("MSFT", "US", "300"), ("NVDA", "US", "90"), ("2330", "TW", "600")
    )
    valuator = _valuator(ladder.provider, services)

    valued = valuator.value_all(store.list_all())

    assert all(item.valuation.status == "ok" for item in valued)
    assert [end for _, _, end in ladder.bank.asks] == [TODAY, OPEN_BANK, OPEN_YAHOO]
    ladder.bank.asks.clear()
    valuator.value_position(store.list_all()[0])
    assert [end for _, _, end in ladder.bank.asks] == [TODAY, OPEN_BANK]


def test_r5_2_cost_is_priced_at_the_rate_fx_open_describes(tmp_path: Path) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, opened_at=OPEN_BANK, quantity="10", avg_cost="100")

    [valued] = _valuator(ladder.provider).value_all(store.list_all())

    fx_open = valued.valuation.fx_open
    fx_now = valued.valuation.fx
    assert fx_open is not None and fx_now is not None
    rate_open = Decimal(BANK_DAYS[date.fromisoformat(str(fx_open.as_of))])
    rate_now = Decimal(YAHOO_DAYS[date.fromisoformat(str(fx_now.as_of))])
    assert str(valued.cost_twd) == str(Decimal("10") * Decimal("100") * rate_open) == "30500.0"
    assert valued.market_value_twd == Decimal("10") * Decimal("150") * rate_now
    assert valued.valuation.fx_contribution_twd == Decimal("10") * Decimal("100") * (
        rate_now - rate_open
    )


def test_r5_10c_the_summary_json_carries_fx_open_and_its_data_status(
    api_harness: ApiHarness,
) -> None:
    ladder = _Ladder()
    services = _prices(("AAPL", "US", "150"), ("MSFT", "US", "300"), ("2330", "TW", "600"))
    app.dependency_overrides[get_valuator] = lambda: _valuator(ladder.provider, services)
    store = api_harness.positions
    _hold(store, "AAPL", opened_at=OPEN_BANK)
    _hold(store, "MSFT", opened_at=OPEN_YAHOO)
    _hold(store, "2330", market="TW", currency="TWD", opened_at=OPEN_BANK, avg_cost="500")

    response = api_harness.client.get("/api/portfolio/summary")

    assert response.status_code == 200
    rows = {row["symbol"]: row["valuation"] for row in response.json()["positions"]}
    assert set(rows["AAPL"]["fx_open"]) == FX_KEYS
    assert rows["AAPL"]["fx_open"]["data_status"] == "fresh"
    assert rows["AAPL"]["fx_open"]["source"] == BANK
    assert rows["AAPL"]["fx_open"]["as_of"] == OPEN_BANK.isoformat()
    assert rows["MSFT"]["fx_open"]["data_status"] == "backup"
    assert rows["MSFT"]["fx_open"]["source"] == YAHOO
    assert rows["2330"]["fx_open"] is None


# --- R5-3 (O-5): only ok positions are disclosed, fx_now's sentence only ------------


def _fx_info(source: str) -> FxInfo:
    return FxInfo(
        pair=PAIR,
        as_of=TODAY.isoformat(),
        source=source,
        data_status=DataStatus.FRESH,
        source_note=SOURCE_NOTES[source],
    )


def _row(status: str, fx: FxInfo | None, fx_open: FxInfo | None = None) -> Valuation:
    ok = status == "ok"
    return Valuation(
        status="ok" if ok else "insufficient_data",
        missing=[] if ok else ["price"],
        price=None,
        fx=fx,
        fx_open=fx_open,
        pnl_original=None,
        pnl_twd=Decimal(0) if ok else None,
        asset_contribution_twd=Decimal(0) if ok else None,
        fx_contribution_twd=Decimal(0) if ok else None,
    )


def test_r5_3_an_unvalued_position_contributes_no_sentence() -> None:
    rows = [_row("insufficient_data", _fx_info(YAHOO)), _row("ok", _fx_info(BANK))]
    assert fx_disclosures_for(rows) == [SOURCE_NOTES[BANK]]


def test_r5_3_o5_a_pair_with_no_ok_position_discloses_nothing(tmp_path: Path) -> None:
    """O-5: the rate was found, but it went into no figure, so no sentence."""
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, "AAPL", opened_at=OPEN_BANK)
    _hold(store, "MSFT", opened_at=OPEN_YAHOO)
    services = _prices()  # no US price at all: every USD row is insufficient

    summary = build_summary(store, _valuator(ladder.provider, services))

    assert [row.valuation.status for row in summary.positions] == ["insufficient_data"] * 2
    assert all(row.valuation.fx is not None for row in summary.positions)
    assert summary.fx_disclosures == []


def test_r5_3_the_overview_still_lists_fx_now_only(tmp_path: Path) -> None:
    """PR-RK5a adds no fx_open sentence; that union is PR-RK5b's (R5-8)."""
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, opened_at=OPEN_BANK)

    summary = build_summary(store, _valuator(ladder.provider))

    assert summary.positions[0].valuation.status == "ok"
    assert summary.fx_disclosures == [SOURCE_NOTES[YAHOO]]
    assert fx_disclosures_for([_row("ok", _fx_info(YAHOO), _fx_info(BANK))]) == [
        SOURCE_NOTES[YAHOO]
    ]


# --- R5-4: one mixed-source WARNING per combination per build_summary ---------------


def test_r5_4_a_mixed_book_logs_one_line_per_combination(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, "AAPL", opened_at=OPEN_BANK)
    _hold(store, "MSFT", opened_at=OPEN_BANK_LATER)  # same combination, another date
    _hold(store, "NVDA", opened_at=OPEN_YAHOO)  # both rates from Yahoo: not mixed
    services = _prices(("AAPL", "US", "150"), ("MSFT", "US", "300"), ("NVDA", "US", "90"))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        summary = build_summary(store, _valuator(ladder.provider, services))

    assert [row.valuation.status for row in summary.positions] == ["ok"] * 3
    # First-seen dates of the combination; no symbol, id, amount or rate.
    assert _warnings(caplog) == [_mixed_line(open_source=BANK, open_as_of=OPEN_BANK)]


def test_r5_4_each_combination_once_in_every_build_summary(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    fx = _ByDateFx(
        {
            TODAY: (YAHOO, "32.1"),
            OPEN_BANK: (BANK, "30.5"),
            OPEN_YAHOO: ("other_fx", "29.8"),
            OPEN_BANK_LATER: (BANK, "30.75"),
        }
    )
    store = _store(tmp_path)
    _hold(store, "AAPL", opened_at=OPEN_BANK)
    _hold(store, "MSFT", opened_at=OPEN_YAHOO)
    _hold(store, "NVDA", opened_at=OPEN_BANK_LATER)
    services = _prices(("AAPL", "US", "150"), ("MSFT", "US", "300"), ("NVDA", "US", "90"))
    valuator = _valuator(fx, services)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        build_summary(store, valuator)
        build_summary(store, valuator)

    once = [
        _mixed_line(open_source=BANK, open_as_of=OPEN_BANK),
        _mixed_line(open_source="other_fx", open_as_of=OPEN_YAHOO),
    ]
    assert _warnings(caplog) == once + once


def test_r5_4_the_line_names_no_symbol_amount_or_rate(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, "AAPL", opened_at=OPEN_BANK, quantity="7", avg_cost="123")

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        build_summary(store, _valuator(ladder.provider))

    [line] = _warnings(caplog)
    assert line == _mixed_line(open_source=BANK, open_as_of=OPEN_BANK)
    assert "AAPL" not in line and "id=" not in line
    # Beyond the two rate dates, not one digit: no quantity, cost, amount or rate.
    stripped = line.replace(TODAY.isoformat(), "").replace(OPEN_BANK.isoformat(), "")
    assert not any(char.isdigit() for char in stripped)


def test_r5_4_two_sources_sharing_one_sentence_are_still_two(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Risk S-1: compared by source id, not by sentence (both get GENERIC_SOURCE_NOTE)."""
    fx = _ByDateFx({TODAY: ("alpha_fx", "32.1"), OPEN_BANK: ("beta_fx", "30.5")})
    store = _store(tmp_path)
    _hold(store, opened_at=OPEN_BANK)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        summary = build_summary(store, _valuator(fx))

    [row] = summary.positions
    assert row.valuation.fx is not None and row.valuation.fx_open is not None
    assert row.valuation.fx.source_note == row.valuation.fx_open.source_note
    assert _warnings(caplog) == [
        _mixed_line(now_source="alpha_fx", open_source="beta_fx", open_as_of=OPEN_BANK)
    ]


@pytest.mark.parametrize(
    ("opened_at", "us_priced"),
    [
        pytest.param(OPEN_YAHOO, True, id="same-source"),
        pytest.param(OPEN_BANK, False, id="mixed-but-unvalued"),
        pytest.param(None, True, id="no-open-date"),
        pytest.param(OPEN_NOWHERE, True, id="open-date-rate-failed"),
    ],
)
def test_r5_4_no_line_unless_an_ok_position_mixes(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    opened_at: date | None,
    us_priced: bool,
) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, opened_at=opened_at)
    _hold(store, "2330", market="TW", currency="TWD", opened_at=OPEN_BANK, avg_cost="500")
    services = (
        _prices(("AAPL", "US", "150"), ("2330", "TW", "600"))
        if us_priced
        else _prices(("2330", "TW", "600"))
    )

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        build_summary(store, _valuator(ladder.provider, services))

    assert _warnings(caplog) == []


# --- R5-10d: the KX-A2 short-circuit ------------------------------------------------


def test_r5_10d_the_short_circuit_spells_out_fx_open_none() -> None:
    """Greppable on purpose (R5-10d), not left to the field's default."""
    assert "fx_open=None" in inspect.getsource(valuation._currency_market_mismatch)
    assert valuation._currency_market_mismatch().valuation.fx_open is None


@pytest.mark.parametrize(
    ("symbol", "market", "currency"),
    [
        pytest.param("AAPL", "US", "TWD", id="type-A"),
        pytest.param("2330", "TW", "USD", id="type-B"),
    ],
)
def test_r5_10d_a_mismatched_row_never_warns_nor_discloses(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    symbol: str,
    market: str,
    currency: Currency,
) -> None:
    ladder = _Ladder()
    store = _store(tmp_path)
    _hold(store, symbol, market=market, currency=currency, opened_at=OPEN_BANK)
    services = _prices(("AAPL", "US", "150"), ("2330", "TW", "600"))

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        summary = build_summary(store, _valuator(ladder.provider, services))

    [row] = summary.positions
    assert row.valuation.missing == [valuation.CURRENCY_MARKET_MISMATCH]
    assert row.valuation.fx_open is None
    assert summary.fx_disclosures == []
    assert _warnings(caplog) == []
    assert ladder.bank.asks == [] and ladder.yahoo.asks == []
