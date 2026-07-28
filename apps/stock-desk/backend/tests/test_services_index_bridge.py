"""The index assembly seam: signature bridge, disclosure facade, whole stack.

``YFinanceAdapter.get_index_daily_bars(index_symbol, start, end)`` and the
``PriceService`` protocol ``app/services/index.py`` consumes
(``get_daily_bars(symbol, market, start, end)``) are two different shapes. What
is tested here is the join between them, and specifically that it stays a
*translation*: the symbol must reach the adapter untouched, and no rung of the
composition may promote an index series to ``fresh``.

Everything runs against fakes -- there is no adapter and no network in this
file, which is the point: the seam has to be provable offline.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, PriceBar, ProviderResult
from app.data.service import MarketDataService
from app.services import index as I
from tests.api_helpers import recent_bars, trending_closes

START = date(2024, 1, 1)
END = date(2026, 7, 26)
_NOW = datetime(2026, 7, 26, 6, 0, tzinfo=UTC)


class FakeIndexAdapter:
    """An ``IndexBarsProvider``: only the index method, exactly as yfinance has it.

    Deliberately does **not** implement ``get_daily_bars``, so a bridge that
    quietly stopped translating would fail here rather than pass by accident.
    """

    def __init__(
        self,
        bars: dict[str, list[PriceBar]] | None = None,
        *,
        status: DataStatus = DataStatus.BACKUP,
        reason: str | None = None,
    ) -> None:
        self.bars = dict(bars or {})
        self.status = status
        self.reason = reason
        #: Every symbol the adapter was asked for, verbatim.
        self.calls: list[tuple[str, date, date]] = []

    def get_index_daily_bars(
        self, index_symbol: str, start: date, end: date
    ) -> ProviderResult:
        self.calls.append((index_symbol, start, end))
        window = [bar for bar in self.bars.get(index_symbol, []) if start <= bar.date <= end]
        if not window:
            return ProviderResult(
                bars=[],
                status=DataStatus.UNAVAILABLE,
                as_of=_NOW,
                source="yfinance",
                staleness_minutes=None,
                reason=self.reason,
            )
        return ProviderResult(
            bars=window,
            status=self.status,
            as_of=_NOW,
            source="yfinance",
            staleness_minutes=0,
        )


def _index_bars(symbol: str, market: str = "TW", count: int = 30) -> list[PriceBar]:
    return recent_bars(
        trending_closes(count),
        symbol=symbol,
        market="TW" if market == "TW" else "US",
        end=END,
    )


# --- The bridge itself -------------------------------------------------------


def test_the_bridge_translates_the_call_shape() -> None:
    adapter = FakeIndexAdapter({"^TWII": _index_bars("^TWII")})
    bridge = I.IndexProviderBridge(adapter)
    result = bridge.get_daily_bars("^TWII", START, END)
    assert len(result.bars) == 30
    assert adapter.calls == [("^TWII", START, END)]


@pytest.mark.parametrize("symbol", ["^TWII", "^GSPC", "BRK.B", "not an index"])
def test_the_bridge_passes_the_symbol_through_verbatim(symbol: str) -> None:
    """No canonicalisation, no ``^`` handling, no validation of its own.

    Whether a code is a supported index is the adapter's single source of
    truth; a second opinion here would be a second table to keep in sync.
    """
    adapter = FakeIndexAdapter()
    I.IndexProviderBridge(adapter).get_daily_bars(symbol, START, END)
    assert adapter.calls[0][0] == symbol


def test_the_bridge_returns_the_adapter_status_untouched() -> None:
    adapter = FakeIndexAdapter({"^TWII": _index_bars("^TWII")}, status=DataStatus.BACKUP)
    result = I.IndexProviderBridge(adapter).get_daily_bars("^TWII", START, END)
    # ADR-0005 I-3: the adapter already downgraded this; nothing may undo it.
    assert result.status is DataStatus.BACKUP
    assert result.source == "yfinance"


def test_the_bridge_forwards_the_adapter_reason() -> None:
    adapter = FakeIndexAdapter(reason="「^SOX」目前不在本工具支援的指數範圍內。")
    result = I.IndexProviderBridge(adapter).get_daily_bars("^SOX", START, END)
    assert result.status is DataStatus.UNAVAILABLE
    assert result.reason == "「^SOX」目前不在本工具支援的指數範圍內。"


# --- The disclosure facade ---------------------------------------------------


class _FreshService:
    """A ``PriceService`` that claims ``fresh`` -- what a service ladder does."""

    def __init__(self, status: DataStatus = DataStatus.FRESH) -> None:
        self.status = status

    def get_daily_bars(
        self, symbol: str, market: str, start: date, end: date
    ) -> ProviderResult:
        return ProviderResult(
            bars=_index_bars(symbol),
            status=self.status,
            as_of=_NOW,
            source="yfinance",
            staleness_minutes=0,
            is_within_ttl=True,
            reason="上一層說了些什麼。",
        )


def test_the_facade_never_lets_an_index_series_be_fresh() -> None:
    service = I.IndexSeriesService(_FreshService())
    result = service.get_daily_bars("^TWII", "TW", START, END)
    assert result.status is DataStatus.BACKUP


@pytest.mark.parametrize(
    "status", [DataStatus.BACKUP, DataStatus.CACHED_STALE, DataStatus.UNAVAILABLE]
)
def test_the_facade_leaves_every_other_rung_alone(status: DataStatus) -> None:
    """Disclosure only ever moves pessimistically: staleness is never hidden."""
    service = I.IndexSeriesService(_FreshService(status))
    assert service.get_daily_bars("^TWII", "TW", START, END).status is status


def test_the_facade_preserves_everything_but_the_status() -> None:
    result = I.IndexSeriesService(_FreshService()).get_daily_bars("^TWII", "TW", START, END)
    assert result.source == "yfinance"
    assert result.is_within_ttl is True
    assert result.reason == "上一層說了些什麼。"
    assert len(result.bars) == 30


# --- The whole stack, as ``deps`` assembles it -------------------------------


def _stack(adapter: FakeIndexAdapter, tmp_path: Path) -> I.IndexSeriesService:
    """Exactly the composition in ``app/api/deps.py``, on a temp database."""
    return I.IndexSeriesService(
        MarketDataService(
            primary=I.IndexProviderBridge(adapter),
            cache=PriceBarCache(db_path=tmp_path / "index.db"),
            cache_first=True,
        )
    )


def test_a_mapped_etf_reaches_the_adapter_through_the_whole_stack(tmp_path: Path) -> None:
    adapter = FakeIndexAdapter({"^TWII": _index_bars("^TWII")})
    loaded = I.load_index_bars(
        {"TW": _stack(adapter, tmp_path)}, etf_symbol="00675L", start=START, end=END
    )
    assert loaded.available is True
    assert len(loaded.bars) == 30
    # The ETF symbol never leaves the mapping layer; the adapter sees the code.
    assert adapter.calls[0][0] == "^TWII"
    # And the ladder's "primary answered, therefore fresh" is undone on the way
    # out: the whole point of the facade.
    assert loaded.status is DataStatus.BACKUP


def test_an_unmapped_etf_never_reaches_the_adapter(tmp_path: Path) -> None:
    adapter = FakeIndexAdapter({"^TWII": _index_bars("^TWII")})
    loaded = I.load_index_bars(
        {"TW": _stack(adapter, tmp_path)}, etf_symbol="00631L", start=START, end=END
    )
    assert loaded.bars == []
    assert adapter.calls == []


def test_the_adapter_reason_survives_to_the_index_loader(tmp_path: Path) -> None:
    adapter = FakeIndexAdapter(reason="yfinance 連線逾時或發生錯誤，暫不可用。")
    loaded = I.load_index_bars(
        {"TW": _stack(adapter, tmp_path)}, etf_symbol="00675L", start=START, end=END
    )
    assert loaded.reason is not None
    # Both halves: which series is missing, and what the source said about it.
    assert "^TWII" in loaded.reason
    assert "yfinance 連線逾時或發生錯誤" in loaded.reason


def test_the_index_stack_serves_a_warm_cache_without_calling_the_source(
    tmp_path: Path,
) -> None:
    adapter = FakeIndexAdapter({"^TWII": _index_bars("^TWII")})
    stack = _stack(adapter, tmp_path)
    stack.get_daily_bars("^TWII", "TW", START, END)
    assert len(adapter.calls) == 1

    again = stack.get_daily_bars("^TWII", "TW", START, END)
    # cache_first layer 0: the second read is served locally, and says so.
    assert len(adapter.calls) == 1
    assert again.status is DataStatus.CACHED_STALE
    assert again.is_within_ttl is True
    assert len(again.bars) == 30
