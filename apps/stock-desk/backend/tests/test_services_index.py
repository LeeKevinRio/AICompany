"""Index-series acquisition: mapping refusals, missing services, and disclosure.

Every path is exercised against a fake service, so the module's contract is
pinned without a network: the only thing it may ever return is either the
series the mapping named, or an empty result whose ``reason`` says which fact
is missing.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.data.interface import DataStatus
from app.data.providers.yfinance import INDEX_SYMBOL_METADATA
from app.leverage.index_mapping import INDEX_MAPPING, INDEX_SYMBOL_PREFIX, IndexRef
from app.services import index as I
from tests.api_helpers import FakePriceService, recent_bars, trending_closes

START = date(2024, 1, 1)
END = date(2026, 7, 26)


def _service(symbol: str = "^TWII", *, count: int = 30, **kwargs: object) -> FakePriceService:
    service = FakePriceService(**kwargs)  # type: ignore[arg-type]
    service.seed(
        symbol,
        recent_bars(trending_closes(count), symbol=symbol, market="TW", end=END),
    )
    return service


def _load(resolver: I.IndexServiceResolver, symbol: str) -> I.LoadedIndexBars:
    return I.load_index_bars(resolver, etf_symbol=symbol, start=START, end=END)


# --- The happy path ----------------------------------------------------------


def test_a_mapped_etf_resolves_to_its_index_series() -> None:
    service = _service()
    loaded = _load({"TW": service}, "00675L")
    assert loaded.available is True
    assert len(loaded.bars) == 30
    assert loaded.reason is None
    # The series was requested by its own code, in its own market.
    assert service.calls == [("^TWII", "TW", START, END)]
    assert loaded.ref is not None
    assert loaded.ref.series_symbol == "^TWII"


def test_a_tw_fund_on_a_us_benchmark_asks_the_us_service() -> None:
    us = _service("^NDX")
    loaded = I.load_index_bars({"US": us}, etf_symbol="00670L", start=START, end=END)
    assert loaded.available is True
    assert us.calls[0][0] == "^NDX"
    assert us.calls[0][1] == "US"


def test_a_live_index_series_is_disclosed_as_backup_never_fresh() -> None:
    loaded = _load({"TW": _service(status=DataStatus.FRESH)}, "00675L")
    # ADR-0005 decision 1.3: a non-official source is never the freshest rung.
    assert loaded.status is DataStatus.BACKUP
    assert I.UNOFFICIAL_SOURCE_NOTE in loaded.notes


def test_a_stale_cache_is_not_upgraded_into_backup() -> None:
    loaded = _load({"TW": _service(status=DataStatus.CACHED_STALE)}, "00675L")
    assert loaded.status is DataStatus.CACHED_STALE
    assert I.disclosed_status(DataStatus.UNAVAILABLE) is DataStatus.UNAVAILABLE


def test_meta_carries_the_mapping_facts_for_the_ui() -> None:
    meta = _load({"TW": _service()}, "00675L").meta()
    assert meta["series_symbol"] == "^TWII"
    assert meta["basis"] == "official_index"
    assert meta["return_basis"] == "unknown"
    assert meta["mapping_verified"] is False
    assert meta["mapping_verified_on"] is None
    assert meta["bar_count"] == 30


# --- Refusals ----------------------------------------------------------------


def test_a_symbol_with_no_mapping_row_is_refused_with_a_reason() -> None:
    loaded = _load({"TW": _service()}, "2330")
    assert loaded.ref is None
    assert loaded.bars == []
    assert loaded.status is DataStatus.UNAVAILABLE
    assert loaded.reason == I.NO_MAPPING_ROW_REASON


@pytest.mark.parametrize("symbol", ["00631L", "SOXL"])
def test_an_unmapped_row_returns_its_own_note_as_the_reason(symbol: str) -> None:
    service = _service()
    loaded = _load({"TW": service}, symbol)
    assert loaded.bars == []
    assert loaded.reason == INDEX_MAPPING[symbol].note
    # And no request was made: there is nothing to ask for.
    assert service.calls == []


def test_a_proxy_row_is_blocked_even_if_one_ever_appears() -> None:
    # No such row exists (test_leverage_index_mapping enforces that); this pins
    # the behaviour of the code path guarding it.
    proxy = IndexRef(
        etf_symbol="TQQQ",
        underlying_index_text="NASDAQ-100 Index (3x single-day)",
        basis="proxy_etf",
        series_symbol="QQQ",
        series_market="US",
        return_basis="price",
    )
    service = _service("QQQ")
    loaded = I.load_index_series({"US": service}, proxy, start=START, end=END)
    assert loaded.bars == []
    assert loaded.reason == I.PROXY_BASIS_REASON
    assert service.calls == []


def test_a_market_without_an_index_service_says_so() -> None:
    loaded = _load({}, "00675L")
    assert loaded.bars == []
    assert "^TWII" in (loaded.reason or "")
    assert "TW" in (loaded.reason or "")


def test_a_source_with_no_bars_is_reported_not_substituted() -> None:
    empty = FakePriceService()
    loaded = _load({"TW": empty}, "00675L")
    assert loaded.bars == []
    assert loaded.reason == I.NO_BARS_REASON.format(series_symbol="^TWII")
    assert loaded.status is DataStatus.UNAVAILABLE


def test_every_refusal_carries_the_unverified_mapping_disclosure() -> None:
    for symbol in ("00675L", "00631L"):
        loaded = _load({}, symbol)
        assert I.UNVERIFIED_MAPPING_NOTE in loaded.notes


def test_no_refusal_text_implies_a_temporary_technical_fault() -> None:
    reasons = [
        I.NO_MAPPING_ROW_REASON,
        I.PROXY_BASIS_REASON,
        I.NO_SERVICE_REASON,
        I.NO_BARS_REASON,
        I.NO_BENCHMARK_REASON,
    ]
    for reason in reasons:
        for phrase in ("暫時", "稍後", "重試", "故障", "維護中"):
            assert phrase not in reason


# --- The market benchmark ----------------------------------------------------


def test_every_market_benchmark_is_an_official_index_code() -> None:
    # ADR-0005 決策一: index codes only, never a tracking ETF standing in.
    for benchmark in I.MARKET_BENCHMARK.values():
        assert benchmark.series_symbol.startswith(INDEX_SYMBOL_PREFIX)
        assert benchmark.series_symbol in INDEX_SYMBOL_METADATA
        # The label names the same series the code points at.
        assert benchmark.series_symbol in benchmark.label


def test_the_tw_benchmark_is_the_taiwan_weighted_index() -> None:
    service = _service()
    loaded = I.load_market_benchmark({"TW": service}, market="TW", start=START, end=END)
    assert loaded.available is True
    assert len(loaded.bars) == 30
    assert loaded.reason is None
    assert loaded.series_symbol == "^TWII"
    assert loaded.label == I.MARKET_BENCHMARK["TW"].label
    assert service.calls == [("^TWII", "TW", START, END)]


def test_the_us_benchmark_is_the_sp500_index() -> None:
    service = _service("^GSPC")
    loaded = I.load_market_benchmark({"US": service}, market="US", start=START, end=END)
    assert loaded.available is True
    assert service.calls == [("^GSPC", "US", START, END)]


def test_a_live_benchmark_series_is_disclosed_as_backup_never_fresh() -> None:
    loaded = I.load_market_benchmark(
        {"TW": _service(status=DataStatus.FRESH)}, market="TW", start=START, end=END
    )
    assert loaded.status is DataStatus.BACKUP
    assert I.UNOFFICIAL_SOURCE_NOTE in loaded.notes
    assert I.UNVERIFIED_BENCHMARK_NOTE in loaded.notes


def test_a_benchmark_source_with_no_bars_is_reported_not_substituted() -> None:
    loaded = I.load_market_benchmark(
        {"TW": FakePriceService()}, market="TW", start=START, end=END
    )
    assert loaded.bars == []
    assert loaded.available is False
    # Which series was wanted is still stated: it is the useful half of the fact.
    assert loaded.series_symbol == "^TWII"
    assert loaded.reason == I.NO_BARS_REASON.format(series_symbol="^TWII")


def test_a_market_without_an_index_service_has_no_benchmark_and_says_so() -> None:
    loaded = I.load_market_benchmark({}, market="TW", start=START, end=END)
    assert loaded.bars == []
    assert "^TWII" in (loaded.reason or "")
    assert I.UNVERIFIED_BENCHMARK_NOTE in loaded.notes


def test_benchmark_meta_carries_the_series_and_the_reason() -> None:
    meta = I.load_market_benchmark({}, market="TW", start=START, end=END).meta()
    assert meta["series_symbol"] == "^TWII"
    assert meta["available"] is False
    assert meta["bar_count"] == 0
    assert meta["status"] == DataStatus.UNAVAILABLE.value
    assert meta["reason"]
