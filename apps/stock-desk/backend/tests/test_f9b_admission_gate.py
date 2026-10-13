"""F-9b commit 7: symbol admission at both service entries, and Alpha Vantage's own check.

ADR-0024 D-4; C-4, C-6 (admission and wording), C-7, C-13 (1)(2), C-15, C-16,
C-17 (grep half), C-19 (admission, live and cache-only, end to end);
TA5 section 2 test 7; 風控 F9W-1, F9W-2, F9W-6, F9W-7, F9W-8, F9W-9.
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.api import deps
from app.data import gate_wording
from app.data.admission import admit_any_shape, admit_equity_daily_bars
from app.data.cache import CacheReadResult, PriceBarCache
from app.data.gate_wording import (
    EQUITY_GATE_WORDING,
    SYMBOL_NOT_ADMITTED_REASON_TW,
    SYMBOL_NOT_ADMITTED_REASON_US,
)
from app.data.http import RateLimitedClient
from app.data.interface import DataStatus, Market, MarketDataProvider, PriceBar, ProviderResult
from app.data.providers.alpha_vantage import API_KEY_ENV_VAR, AlphaVantageAdapter
from app.data.quota import DAILY_LIMIT_ENV_VAR, SAFETY_MARGIN_ENV_VAR, QuotaLedger
from app.data.service import CURRENCY_DIFFERS_LOG_PREFIX, MarketDataService
from app.portfolio.valuation import SYMBOL_OR_UNIT_REJECTED, PositionValuator, PriceMode
from app.positions.models import Position
from app.services.market import PROVIDER_REASON_PREFIX, load_bars
from tests.market_service_helpers import equity_service, index_service

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
FIXTURES = Path(__file__).parent / "fixtures"
RULING_1 = Path(__file__).resolve().parents[4] / (
    "work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md"
)
SERVICE_LOGGER = "app.data.service"
NOW = datetime(2024, 1, 3, 8, 0, tzinfo=UTC)
START, END = date(2024, 1, 1), date(2024, 1, 2)


def _bar(symbol: str, market: Market) -> PriceBar:
    return PriceBar(
        symbol=symbol,
        market=market,
        date=END,
        open=Decimal("10"),
        high=Decimal("10"),
        low=Decimal("10"),
        close=Decimal("10"),
        volume=1,
        currency="TWD" if market == "TW" else "USD",
        as_of=NOW,
        source="stub",
    )


class _Rung(MarketDataProvider):
    source_id = "stub"

    def __init__(self, market: Market) -> None:
        self.market = market
        self.asked: list[str] = []

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        self.asked.append(symbol)
        return ProviderResult(
            bars=[_bar(symbol, self.market)],
            status=DataStatus.FRESH,
            as_of=NOW,
            source="stub",
            staleness_minutes=0,
        )


class _Cache(PriceBarCache):
    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path=db_path)
        self.gets = 0

    def get(
        self,
        symbol: str,
        market: Market,
        start: date,
        end: date,
        *,
        now: datetime | None = None,
    ) -> CacheReadResult | None:
        self.gets += 1
        return super().get(symbol, market, start, end, now=now)


def _service(tmp_path: Path, market: Market) -> tuple[_Cache, _Rung, MarketDataService]:
    cache = _Cache(tmp_path / f"{market}.db")
    rung = _Rung(market)
    return (
        cache,
        rung,
        equity_service(primary=rung, cache=cache, clock=lambda: NOW, cache_first=True),
    )


# --- The approved constants ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("constant", "line"), [(SYMBOL_NOT_ADMITTED_REASON_US, 20), (SYMBOL_NOT_ADMITTED_REASON_TW, 23)]
)
def test_w_a_and_w_b_are_the_approved_wording_verbatim(constant: str, line: int) -> None:
    approved = RULING_1.read_text(encoding="utf-8").splitlines()[line - 1].removeprefix("> ")
    assert constant == approved
    assert "{" not in constant


def test_the_equity_wording_names_w_a_for_us_and_w_b_for_tw() -> None:
    assert dict(EQUITY_GATE_WORDING.symbol_not_admitted) == {
        "US": SYMBOL_NOT_ADMITTED_REASON_US,
        "TW": SYMBOL_NOT_ADMITTED_REASON_TW,
    }


# --- C-13 (1)(2): exact, through load_bars --------------------------------------------------


@pytest.mark.parametrize(
    ("market", "symbol", "expected"),
    [
        pytest.param("US", "TSCO.LON", SYMBOL_NOT_ADMITTED_REASON_US, id="W-a"),
        pytest.param("TW", "00679K", SYMBOL_NOT_ADMITTED_REASON_TW, id="W-b"),
    ],
)
def test_c13_1_2_a_refused_symbol_states_w_a_or_w_b_alone(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, market: Market, symbol: str, expected: str
) -> None:
    _cache, rung, service = _service(tmp_path, market)

    with caplog.at_level(logging.INFO, logger=SERVICE_LOGGER):
        loaded = load_bars({market: service}, symbol=symbol, market=market, start=START, end=END)
    result = service.get_daily_bars(symbol, market, START, END)

    assert loaded.reason == expected
    assert PROVIDER_REASON_PREFIX not in expected
    assert loaded.bars == []
    assert result.rejection == "symbol_not_admitted"
    assert rung.asked == []
    # TA5 section 2 test 7: an admission refusal is not a currency event.
    assert not any(r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX) for r in caplog.records)


# --- C-4: no cache, no source, no quota, no attempt log -------------------------------------


def _alpha_vantage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[AlphaVantageAdapter, QuotaLedger, list[httpx.Request]]:
    monkeypatch.setenv(API_KEY_ENV_VAR, "fixture-test-key-not-real")
    monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
    monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "0")
    payload: dict[str, Any] = json.loads(
        (FIXTURES / "alpha_vantage_daily_aapl.json").read_text(encoding="utf-8")
    )
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    client = RateLimitedClient(
        base_url="https://www.alphavantage.co",
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(respond),
        sleep_fn=lambda _seconds: None,
    )
    adapter = AlphaVantageAdapter(client=client, ledger=ledger, min_interval_seconds=0.0)
    return adapter, ledger, requests


@pytest.mark.parametrize("entry", ["get_daily_bars", "get_cached_bars"])
def test_c4_a_refused_symbol_touches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    adapter, ledger, requests = _alpha_vantage(tmp_path, monkeypatch)
    cache = _Cache(tmp_path / "c.db")
    cache.put([_bar("TSCO.LON", "US")], source="stub", fetched_at=NOW)  # would be served
    cache.gets = 0
    service = equity_service(primary=adapter, cache=cache, clock=lambda: NOW, cache_first=True)

    result = getattr(service, entry)("TSCO.LON", "US", START, END)

    assert result.bars == []
    assert result.reason == SYMBOL_NOT_ADMITTED_REASON_US
    assert result.rejection == "symbol_not_admitted"
    assert requests == []  # transport: zero calls
    assert ledger.status("alpha_vantage") is None  # quota: nothing reserved
    assert cache.last_attempt_at("TSCO.LON", "US") is None  # no attempt log
    assert cache.gets == 0  # no cache read


# --- C-7, C-16: who is asked about ----------------------------------------------------------

ADMITTED = [
    ("US", "BRK.B"),
    ("US", "BF.B"),
    ("US", "BRK-B"),
    ("US", "AAPL"),
    ("US", "aapl.us"),  # judged canonical, handed on as typed (D-4)
    ("TW", "00679B"),
    ("TW", "00631L"),
    ("TW", "00632R"),
    ("TW", "00635U"),
    ("TW", "0050"),
    ("TW", "2330"),
]
REFUSED = [
    ("US", "TSCO.LON"),
    ("US", "RY.TO"),
    ("US", "7203.T"),
    ("US", "^GSPC"),
    ("TW", "00679K"),
    ("TW", "00680K"),
    ("TW", "1234K"),
    ("TW", "2330k"),
]


@pytest.mark.parametrize(("market", "symbol"), ADMITTED)
def test_c7_admitted_symbols_reach_the_source_unchanged(
    tmp_path: Path, market: Market, symbol: str
) -> None:
    _cache, rung, service = _service(tmp_path, market)
    result = service.get_daily_bars(symbol, market, START, END)
    assert rung.asked == [symbol]
    assert result.rejection is None


@pytest.mark.parametrize(("market", "symbol"), REFUSED)
def test_c16_refused_symbols_never_reach_the_source(
    tmp_path: Path, market: Market, symbol: str
) -> None:
    _cache, rung, service = _service(tmp_path, market)
    result = service.get_daily_bars(symbol, market, START, END)
    assert rung.asked == []
    assert result.rejection == "symbol_not_admitted"
    assert result.reason == EQUITY_GATE_WORDING.symbol_not_admitted[market]
    assert result.reason is not None and result.reason.strip()  # qa non-blocking (1)


def test_the_index_ladder_checks_no_shape(tmp_path: Path) -> None:
    rung = _Rung("US")
    service = index_service(primary=rung, cache=PriceBarCache(db_path=tmp_path / "i.db"))
    result = service.get_daily_bars("^GSPC", "US", START, END)
    assert rung.asked == ["^GSPC"]
    assert result.rejection is None


# --- Alpha Vantage's own check (D-4 defence in depth, C-15, F9W-7) --------------------------


def test_alpha_vantage_refuses_before_reserving_quota_and_states_no_w_a(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, ledger, requests = _alpha_vantage(tmp_path, monkeypatch)

    refused = adapter.get_daily_bars("TSCO.LON", START, END)

    assert refused.status is DataStatus.UNAVAILABLE
    assert refused.bars == []
    assert refused.reason is None
    assert requests == []
    assert ledger.status("alpha_vantage") is None

    admitted = adapter.get_daily_bars("BRK.B", date(2023, 12, 29), date(2024, 1, 31))
    assert len(requests) == 1  # an admitted symbol is asked, as before
    assert admitted.source == "alpha_vantage"


def test_c15_the_alpha_vantage_path_never_names_w_a_or_w_b() -> None:
    source = (APP_ROOT / "data" / "providers" / "alpha_vantage.py").read_text(encoding="utf-8")
    for name in ("gate_wording", "SYMBOL_NOT_ADMITTED", "EQUITY_GATE_WORDING"):
        assert name not in source
    for sentence in (SYMBOL_NOT_ADMITTED_REASON_US, SYMBOL_NOT_ADMITTED_REASON_TW):
        assert sentence[:20] not in source


# --- C-19: the valuator, live and cache-only, end to end -----------------------------------


class _NoFx:
    calls = 0

    def get_daily_rates(self, pair: str, start: date, end: date) -> object:
        _NoFx.calls += 1
        raise AssertionError("a refused row asks no FX (F9W-18)")


@pytest.mark.parametrize("mode", ["live", "cache_only"])
@pytest.mark.parametrize(
    ("market", "symbol", "currency"), [("US", "TSCO.LON", "USD"), ("TW", "00679K", "TWD")]
)
def test_c19_an_unadmitted_holding_gets_the_refused_answer_token(
    tmp_path: Path, mode: PriceMode, market: Market, symbol: str, currency: str
) -> None:
    _cache, rung, service = _service(tmp_path, market)
    valuator = PositionValuator(
        market_services={market: service},
        fx_provider=_NoFx(),  # type: ignore[arg-type]
        clock=lambda: NOW,
        price_mode=mode,
    )
    position = Position(
        id=1,
        symbol=symbol,
        market=market,
        quantity=Decimal(1),
        avg_cost=Decimal(1),
        currency=currency,  # type: ignore[arg-type]
        opened_at=START,
        instrument_type="stock",
        note=None,
        created_at=NOW,
        updated_at=NOW,
    )

    valuation = valuator.value_position(position).valuation

    assert valuation.missing == [SYMBOL_OR_UNIT_REJECTED]
    assert valuation.fx is None and valuation.fx_open is None
    assert rung.asked == []


# --- C-6, C-17: the assembly layer passes admission and wording explicitly ------------------


def _construction_sites() -> list[tuple[str, ast.Call]]:
    tree = ast.parse((APP_ROOT / "api" / "deps.py").read_text(encoding="utf-8"))
    sites: list[tuple[str, ast.Call]] = []
    for function in ast.walk(tree):
        if isinstance(function, ast.FunctionDef):
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Call)
                    and getattr(node.func, "id", "") == "MarketDataService"
                ):
                    sites.append((function.name, node))
    return sites


def test_c6_every_construction_passes_admission_and_wording_explicitly() -> None:
    seen: list[tuple[str, str, str]] = []
    for function, call in _construction_sites():
        keywords = {k.arg: k.value for k in call.keywords}
        assert None not in keywords
        scope = keywords["scope"]
        admission = keywords["admission"]
        wording = keywords["wording"]
        assert isinstance(scope, ast.Constant)
        assert isinstance(admission, ast.Name)
        seen.append((str(scope.value), admission.id, ast.unparse(wording)))
        if function == "_default_index_resolver":
            assert (scope.value, admission.id) == ("index", "admit_any_shape")
            assert isinstance(wording, ast.Constant) and wording.value is None
    assert sorted(seen) == [
        ("equity", "admit_equity_daily_bars", "EQUITY_GATE_WORDING"),
        ("equity", "admit_equity_daily_bars", "EQUITY_GATE_WORDING"),
        ("index", "admit_any_shape", "None"),
    ]


def test_c17_the_index_construction_names_no_equity_wording() -> None:
    source = inspect.getsource(deps._default_index_resolver)
    for name in vars(gate_wording):
        if name.isupper():
            assert name not in source


def test_the_shipped_wiring_matches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(deps, "_default_cache", lambda: PriceBarCache(db_path=tmp_path / "w.db"))
    monkeypatch.setattr(deps, "_default_yfinance", lambda: _Rung("US"))
    for name, market in (
        ("TwseAdapter", "TW"),
        ("TpexAdapter", "TW"),
        ("FinMindAdapter", "TW"),
        ("AlphaVantageAdapter", "US"),
    ):
        monkeypatch.setattr(deps, name, lambda market=market: _Rung(market))
    resolver = deps._default_resolver.__wrapped__()  # bypass lru_cache
    index = deps._default_index_resolver.__wrapped__()
    markets: tuple[Market, ...] = ("TW", "US")
    for market in markets:
        service = resolver[market]
        assert service._admission is admit_equity_daily_bars  # type: ignore[attr-defined]
        assert service._wording is EQUITY_GATE_WORDING  # type: ignore[attr-defined]
    inner = index["US"]._inner  # type: ignore[attr-defined]
    assert inner._admission is admit_any_shape
    assert inner._wording is None
