"""Tests for the shared market-aware bar loader (``app/services/market.py``)."""

from __future__ import annotations

from datetime import date, timedelta

from app.data.interface import DataStatus
from app.services.market import load_bars
from tests.api_helpers import FakePriceService, recent_bars, trending_closes

_END = date(2026, 7, 20)
_START = _END - timedelta(days=100)


def _service() -> FakePriceService:
    return FakePriceService({"2330": recent_bars(trending_closes(50), end=_END)})


def test_bars_are_returned_with_their_provenance() -> None:
    loaded = load_bars(
        {"TW": _service()}, symbol="2330", market="TW", start=_START, end=_END
    )
    assert len(loaded.bars) == 50
    assert loaded.status is DataStatus.FRESH
    assert loaded.source == "fake"
    assert loaded.reason is None


def test_meta_block_summarises_the_window() -> None:
    meta = load_bars(
        {"TW": _service()}, symbol="2330", market="TW", start=_START, end=_END
    ).meta()
    assert meta["bar_count"] == 50
    assert meta["last_bar_date"] == _END.isoformat()
    assert meta["first_bar_date"] == (_END - timedelta(days=49)).isoformat()


def test_a_market_without_an_adapter_is_explained_not_raised() -> None:
    loaded = load_bars({"TW": _service()}, symbol="AAPL", market="US", start=_START, end=_END)
    assert loaded.bars == []
    assert loaded.status is DataStatus.UNAVAILABLE
    assert loaded.reason is not None
    assert "沒有 US 市場的行情來源" in loaded.reason


def test_an_empty_provider_result_is_explained() -> None:
    loaded = load_bars(
        {"TW": _service()}, symbol="9999", market="TW", start=_START, end=_END
    )
    assert loaded.bars == []
    assert loaded.reason is not None
    assert "沒有可用的日線資料" in loaded.reason
    assert loaded.meta()["first_bar_date"] is None


def test_a_degraded_rung_is_reported_verbatim() -> None:
    service = _service()
    service.status = DataStatus.BACKUP
    service.source = "finmind"
    service.staleness_minutes = None
    loaded = load_bars({"TW": service}, symbol="2330", market="TW", start=_START, end=_END)
    assert loaded.status is DataStatus.BACKUP
    assert loaded.meta()["source"] == "finmind"
