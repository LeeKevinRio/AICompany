"""F-9b0 commit 0-3: the service's currency lookup and scope are required and explicit.

Pinned here (ADR-0024 D-5, C-6, C-12; TA5 R-56, R-60):

* ``currency_for_market`` and ``scope`` are keyword-only with no default, and
  ``app`` holds no ``expected_currency=None`` and no construction that omits
  either (the grep half of C-6);
* every formal adapter ``deps`` builds, fed its recorded fixture, tags each bar
  with ``MARKET_CURRENCY`` of its market, so the gate cannot fire under the
  shipped configuration (C-12); yfinance does not read ``meta.currency`` before
  F-9c;
* the operator record never reaches a reader (risk-compliance, R-60 suggested).
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.api import deps
from app.data.cache import PriceBarCache
from app.data.http import RateLimitedClient
from app.data.interface import (
    DataStatus,
    Market,
    MarketDataProvider,
    PriceBar,
    ProviderResult,
)
from app.data.providers.alpha_vantage import API_KEY_ENV_VAR, AlphaVantageAdapter
from app.data.providers.finmind import TOKEN_ENV_VAR, FinMindAdapter
from app.data.providers.tpex import TpexAdapter
from app.data.providers.twse import TwseAdapter
from app.data.providers.yfinance import INDEX_SYMBOL_METADATA, YFinanceAdapter
from app.data.quota import DAILY_LIMIT_ENV_VAR, SAFETY_MARGIN_ENV_VAR, QuotaLedger
from app.data.service import (
    BLANK_CURRENCY_LOG_VALUE,
    CURRENCY_DIFFERS_LOG_PREFIX,
    EXPECTED_UNKNOWN_LOG_VALUE,
    MarketDataService,
)
from app.positions.models import MARKET_CURRENCY
from app.services.market import load_bars
from tests.market_service_helpers import equity_service

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SERVICE_LOGGER = "app.data.service"


# --- required, keyword-only, no default ------------------------------------------


@pytest.mark.parametrize("name", ["currency_for_market", "scope"])
def test_the_gate_arguments_are_keyword_only_and_have_no_default(name: str) -> None:
    parameter = inspect.signature(MarketDataService.__init__).parameters[name]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


def test_the_old_optional_currency_argument_is_gone() -> None:
    assert "expected_currency" not in inspect.signature(MarketDataService.__init__).parameters


class _Nothing(MarketDataProvider):
    source_id = "nothing"

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        return ProviderResult(
            bars=[], status=DataStatus.UNAVAILABLE, as_of=datetime.now(UTC), source="nothing"
        )


@pytest.mark.parametrize("missing", ["currency_for_market", "scope"])
def test_omitting_either_gate_argument_fails_to_construct(missing: str, tmp_path: Path) -> None:
    arguments: dict[str, Any] = {
        "primary": _Nothing(),
        "cache": PriceBarCache(db_path=tmp_path / "c.db"),
        "currency_for_market": MARKET_CURRENCY.get,
        "scope": "equity",
    }
    del arguments[missing]
    with pytest.raises(TypeError, match=missing):
        MarketDataService(**arguments)


def test_an_unknown_scope_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="scope"):
        MarketDataService(
            primary=_Nothing(),
            cache=PriceBarCache(db_path=tmp_path / "c.db"),
            currency_for_market=MARKET_CURRENCY.get,
            scope="etf",  # type: ignore[arg-type]
        )


def _construction_sites() -> list[tuple[str, ast.Call]]:
    sites: list[tuple[str, ast.Call]] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                if name == "MarketDataService":
                    sites.append((f"{path.relative_to(APP_ROOT)}:{node.lineno}", node))
    return sites


def test_production_holds_no_expected_currency_none() -> None:
    """The grep of TA5 0-3: no ``expected_currency=None`` anywhere under ``app``."""
    pattern = re.compile(r"expected_currency\s*=\s*None")
    hits = [
        f"{path.relative_to(APP_ROOT)}:{number}"
        for path in sorted(APP_ROOT.rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert hits == []


def test_every_production_construction_passes_both_gate_arguments_explicitly() -> None:
    """C-6 / R-56: the three ``deps`` construction points, each with a literal scope."""
    sites = _construction_sites()
    assert [where.split(":")[0] for where, _ in sites] == ["api/deps.py"] * 3
    scopes: list[str] = []
    for where, call in sites:
        keywords = {k.arg: k.value for k in call.keywords}
        assert None not in keywords, f"{where}: no **kwargs may hide the gate arguments"
        lookup = keywords.get("currency_for_market")
        scope = keywords.get("scope")
        assert lookup is not None and not (
            isinstance(lookup, ast.Constant) and lookup.value is None
        ), where
        assert isinstance(scope, ast.Constant) and scope.value in {"equity", "index"}, where
        scopes.append(scope.value)
    assert sorted(scopes) == ["equity", "equity", "index"]


# --- C-12: every formal adapter tags its market currency -------------------------


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _client(base_url: str, respond: Callable[[httpx.Request], dict[str, Any]]) -> RateLimitedClient:
    return RateLimitedClient(
        base_url=base_url,
        min_interval_seconds=0.0,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=respond(request))),
        sleep_fn=lambda _seconds: None,
    )


def _yfinance_on_fixtures(
    tamper: Callable[[dict[str, Any]], None] = lambda _p: None,
    served: list[dict[str, Any]] | None = None,
) -> YFinanceAdapter:
    payloads = {
        "TQQQ": _fixture("yfinance_chart_tqqq.json"),
        "TWII": _fixture("yfinance_chart_twii.json"),
        "NDX": _fixture("yfinance_chart_ndx.json"),
    }
    for payload in payloads.values():
        tamper(payload)

    def respond(request: httpx.Request) -> dict[str, Any]:
        chosen = next(
            (payload for key, payload in payloads.items() if key in request.url.path),
            payloads["NDX"],
        )
        if served is not None:
            served.append(chosen)
        return chosen

    return YFinanceAdapter(client=_client("https://query1.finance.yahoo.com", respond))


#: source_id -> (symbol, start, end) that its recorded fixture answers.
FIXTURE_REQUESTS: dict[str, tuple[str, date, date]] = {
    "twse": ("2330", date(2024, 1, 1), date(2024, 1, 31)),
    "tpex": ("6147", date(2026, 9, 1), date(2026, 9, 30)),
    "finmind": ("2330", date(2024, 1, 1), date(2024, 1, 31)),
    "alpha_vantage": ("AAPL", date(2023, 12, 29), date(2024, 1, 31)),
    "yfinance": ("TQQQ", date(2024, 1, 1), date(2024, 1, 31)),
}


@pytest.fixture
def fixture_wiring(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``deps`` with every formal adapter on its recorded fixture; no network, no real DB."""
    monkeypatch.setenv(TOKEN_ENV_VAR, "fixture-test-token-not-real")
    monkeypatch.setenv(API_KEY_ENV_VAR, "fixture-test-key-not-real")
    monkeypatch.setenv(DAILY_LIMIT_ENV_VAR, "10")
    monkeypatch.setenv(SAFETY_MARGIN_ENV_VAR, "0")
    cache = PriceBarCache(db_path=tmp_path / "wiring.db")
    ledger = QuotaLedger(db_path=tmp_path / "quota.db")
    yfinance = _yfinance_on_fixtures()
    twse = _fixture("twse_stock_day_2330_202401.json")
    tpex = _fixture("tpex_trading_stock_6147_202609.json")
    finmind = _fixture("finmind_taiwan_stock_price_2330.json")
    alpha = _fixture("alpha_vantage_daily_aapl.json")
    monkeypatch.setattr(deps, "_default_cache", lambda: cache)
    monkeypatch.setattr(deps, "_default_yfinance", lambda: yfinance)
    monkeypatch.setattr(
        deps,
        "TwseAdapter",
        lambda: TwseAdapter(client=_client("https://www.twse.com.tw", lambda _r: twse)),
    )
    monkeypatch.setattr(
        deps,
        "TpexAdapter",
        lambda: TpexAdapter(client=_client("https://www.tpex.org.tw", lambda _r: tpex)),
    )
    monkeypatch.setattr(
        deps,
        "FinMindAdapter",
        lambda: FinMindAdapter(client=_client("https://api.finmindtrade.com", lambda _r: finmind)),
    )
    monkeypatch.setattr(
        deps,
        "AlphaVantageAdapter",
        lambda: AlphaVantageAdapter(
            client=_client("https://www.alphavantage.co", lambda _r: alpha),
            ledger=ledger,
            min_interval_seconds=0.0,
        ),
    )


@pytest.mark.usefixtures("fixture_wiring")
@pytest.mark.parametrize("market", sorted(MARKET_CURRENCY))
def test_every_formal_equity_adapter_tags_its_market_currency(market: Market) -> None:
    """C-12: the W-c verdict cannot fire for any adapter ``deps`` wires today."""
    service = deps._default_resolver.__wrapped__()[market]  # bypass lru_cache
    providers = [service._primary, *service._backups]  # type: ignore[attr-defined]
    seen: list[str] = []
    for provider in providers:
        symbol, start, end = FIXTURE_REQUESTS[provider.source_id]
        result = provider.get_daily_bars(symbol, start, end)
        assert result.bars, provider.source_id
        assert {bar.market for bar in result.bars} == {market}, provider.source_id
        assert {bar.currency for bar in result.bars} == {MARKET_CURRENCY[market]}, (
            provider.source_id
        )
        seen.append(provider.source_id)
    assert seen  # every rung was exercised, none silently skipped
    assert len(seen) == len(providers)


@pytest.mark.usefixtures("fixture_wiring")
def test_every_wired_adapter_has_a_fixture_request() -> None:
    """A new adapter in ``deps`` must come with its fixture here (C-12)."""
    resolver = deps._default_resolver.__wrapped__()  # bypass lru_cache
    wired = {
        provider.source_id
        for service in resolver.values()
        for provider in (service._primary, *service._backups)  # type: ignore[attr-defined]
    }
    assert wired == set(FIXTURE_REQUESTS)


@pytest.mark.parametrize("symbol", sorted(INDEX_SYMBOL_METADATA))
def test_the_index_role_tags_its_market_currency(symbol: str) -> None:
    """C-12 for yfinance role 2 (a written-in assumption, D-6)."""
    result = _yfinance_on_fixtures().get_index_daily_bars(
        symbol, date(2024, 1, 1), date(2024, 1, 31)
    )
    market, _currency = INDEX_SYMBOL_METADATA[symbol]
    assert result.bars
    assert {(bar.market, bar.currency) for bar in result.bars} == {
        (market, MARKET_CURRENCY[market])
    }


def _set_meta_currency(value: str | None) -> Callable[[dict[str, Any]], None]:
    def tamper(payload: dict[str, Any]) -> None:
        meta = payload["chart"]["result"][0]["meta"]
        if value is None:
            meta.pop("currency", None)
        else:
            meta["currency"] = value

    return tamper


@pytest.mark.parametrize("declared", ["GBP", "", None])
def test_yfinance_does_not_read_meta_currency_before_f9c(declared: str | None) -> None:
    """C-12: role 1 and role 2 still write the market currency, whatever ``meta`` says."""
    served: list[dict[str, Any]] = []
    adapter = _yfinance_on_fixtures(_set_meta_currency(declared), served)
    security = adapter.get_daily_bars("TQQQ", date(2024, 1, 1), date(2024, 1, 31))
    index = adapter.get_index_daily_bars("^TWII", date(2024, 1, 1), date(2024, 1, 31))
    assert security.bars and index.bars
    assert {bar.currency for bar in security.bars} == {"USD"}
    assert {bar.currency for bar in index.bars} == {"TWD"}
    # Not vacuous: the adapter really was handed the tampered ``meta``.
    assert len(served) == 2
    assert all(p["chart"]["result"][0]["meta"].get("currency") == declared for p in served)


# --- the operator record stays with the operator ---------------------------------


class _Offbeat(MarketDataProvider):
    source_id = "twse"

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        bar = PriceBar(
            symbol=symbol,
            market="TW",
            date=date(2024, 1, 2),
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            volume=1,
            currency="XQZ",
            as_of=datetime(2024, 1, 2, tzinfo=UTC),
            source="twse",
        )
        return ProviderResult(
            bars=[bar], status=DataStatus.FRESH, as_of=bar.as_of, source="twse", staleness_minutes=0
        )


def test_the_record_never_reaches_the_answer_or_meta(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Risk-compliance R-60 suggested: the record (``observed`` too) stays with the operator."""
    service = equity_service(primary=_Offbeat(), cache=PriceBarCache(db_path=tmp_path / "c.db"))
    with caplog.at_level(logging.WARNING, logger=SERVICE_LOGGER):
        loaded = load_bars(
            {"TW": service},
            symbol="2330",
            market="TW",
            start=date(2024, 1, 1),
            end=date(2024, 1, 31),
        )
    records = [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith(CURRENCY_DIFFERS_LOG_PREFIX)
    ]
    assert len(records) == 1 and " observed=XQZ " in records[0]  # precondition
    published = json.dumps(loaded.meta(), ensure_ascii=False, default=str)
    for fragment in (CURRENCY_DIFFERS_LOG_PREFIX, "observed=", "verdict=", "scope=", records[0]):
        assert fragment not in published
        assert fragment not in (loaded.reason or "")


@pytest.mark.parametrize(
    "name",
    ["CURRENCY_DIFFERS_LOG_PREFIX", "BLANK_CURRENCY_LOG_VALUE", "EXPECTED_UNKNOWN_LOG_VALUE"],
)
def test_the_record_constants_are_used_only_by_the_service(name: str) -> None:
    """No other module of ``app`` can forward the record's wording to a response."""
    users = sorted(
        str(path.relative_to(APP_ROOT))
        for path in APP_ROOT.rglob("*.py")
        if name in path.read_text(encoding="utf-8")
    )
    assert users == ["data/service.py"]


def test_the_record_markers_are_not_reader_wording() -> None:
    assert BLANK_CURRENCY_LOG_VALUE == "<blank>"
    assert EXPECTED_UNKNOWN_LOG_VALUE == "<none>"
