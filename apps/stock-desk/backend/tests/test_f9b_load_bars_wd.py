"""F-9b commit 1: ``load_bars`` splits on ``rejection`` three ways (W-d).

ADR-0024 D-7 (7), C-13 (pipeline part), C-18; 風控 F9W-6, F9W-22, F9W-33 (a)
(pass-through part):

(i)   bars -> the existing success path, the data layer's reason verbatim;
(ii)  no bars and a ``rejection`` -> W-d: the reason verbatim, never joined to
      ``NO_BARS_REASON``, never behind ``PROVIDER_REASON_PREFIX``;
(iii) no bars and no ``rejection`` -> the existing ``NO_BARS_REASON`` plus
      :func:`with_provider_reason`.

A fake service injects the refused answer (built with the ``ProviderResult``
constructor, so the invariant runs); no producer exists yet.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.data.interface import DataStatus, Rejection
from app.data.service import (
    COOLDOWN_NO_CACHE_REASON,
    RECENT_ATTEMPT_FAILED_REASON,
    _combine_reasons,
)
from app.positions.models import Market
from app.services.market import (
    NO_BARS_REASON,
    PROVIDER_REASON_PREFIX,
    LoadedBars,
    load_bars,
    with_provider_reason,
)
from tests.api_helpers import recent_bars, trending_closes
from tests.f9b_helpers import (
    AV_QUOTA_REASON,
    C_COOLDOWN,
    C_PRIME_COOLDOWN,
    T_15,
    W_A,
    W_B,
    W_C_PRIME_TW,
    W_C_PRIME_US,
    W_C_TW,
    W_C_US,
    CannedPriceService,
    answered,
    failed,
    refused,
)

_END = date(2026, 7, 20)
_START = _END - timedelta(days=30)

#: The base sentence (iii) would add; W-d must never contain it.
_NO_BARS_HEAD = "在指定區間內沒有可用的日線資料"

#: Every refused shape the producers will emit (C-13 (1)-(10) as far as they
#: reach ``load_bars`` without bars), each with its category.
REFUSALS = [
    pytest.param("US", "symbol_not_admitted", W_A, id="W-a"),
    pytest.param("TW", "symbol_not_admitted", W_B, id="W-b"),
    pytest.param("US", "unit_mismatch", W_C_US.format(provider="yfinance"), id="W-c-US"),
    pytest.param("TW", "unit_mismatch", W_C_TW.format(provider="finmind"), id="W-c-TW"),
    pytest.param(
        "US",
        "unit_mismatch",
        _combine_reasons([AV_QUOTA_REASON, W_C_US.format(provider="yfinance")]),
        id="W-c+AV",
    ),
    pytest.param("US", "unit_missing", W_C_PRIME_US.format(provider="yfinance"), id="W-c'-US"),
    pytest.param("TW", "unit_missing", W_C_PRIME_TW.format(provider="twse"), id="W-c'-TW"),
    pytest.param("US", "unit_mismatch", C_COOLDOWN.format(minutes=12, cooldown_hours=6), id="C"),
    pytest.param(
        "US", "unit_missing", C_PRIME_COOLDOWN.format(minutes=12, cooldown_hours=6), id="C'"
    ),
    pytest.param("TW", "cache_unit_rejected", T_15, id="T-15"),
    pytest.param(
        "US",
        "cache_unit_rejected",
        _combine_reasons([AV_QUOTA_REASON, "yfinance 連線逾時或發生錯誤，暫不可用。", T_15]),
        id="AV+yfinance+T-15",
    ),
    # C-13 (9): a live W-c' and a refused cache. The category is the producer's:
    # ``unit_missing`` outranks ``cache_unit_rejected`` (D-7 (2)); pinned against
    # the real service in test_f9b_cache_currency_gate.py::test_c13_9_w_c_prime_and_a_refused_cache.
    pytest.param(
        "US",
        "unit_missing",
        _combine_reasons([W_C_PRIME_US.format(provider="yfinance"), T_15]),
        id="W-c'+T-15",
    ),
]


def _load(service: CannedPriceService, *, market: Market, symbol: str = "X") -> LoadedBars:
    return load_bars({market: service}, symbol=symbol, market=market, start=_START, end=_END)


@pytest.mark.parametrize(("market", "rejection", "reason"), REFUSALS)
def test_a_refused_answer_carries_its_reason_verbatim(
    market: Market, rejection: Rejection, reason: str
) -> None:
    """(ii) W-d: exact equality, no ``NO_BARS_REASON``, no prefix (F9W-6, F9W-22)."""
    service = CannedPriceService(refused(rejection, reason))

    loaded = _load(service, market=market)

    assert loaded.reason == reason
    assert _NO_BARS_HEAD not in loaded.reason
    assert PROVIDER_REASON_PREFIX not in loaded.reason
    assert loaded.bars == []
    assert loaded.status is DataStatus.UNAVAILABLE
    assert loaded.meta()["reason"] == reason
    assert loaded.meta()["bar_count"] == 0
    assert loaded.trading_days_behind is None
    assert len(service.calls) == 1
    assert service.cached_calls == []


@pytest.mark.parametrize(
    "rejection", ["symbol_not_admitted", "unit_mismatch", "cache_unit_rejected"]
)
def test_a_refused_answer_without_a_sentence_stays_without_one(rejection: Rejection) -> None:
    """(ii) verbatim includes ``None``: W-d never falls back to ``NO_BARS_REASON``."""
    loaded = _load(CannedPriceService(refused(rejection, None)), market="TW")

    assert loaded.reason is None
    assert loaded.bars == []
    assert loaded.status is DataStatus.UNAVAILABLE


def test_the_refusal_category_never_reaches_the_loaded_bars() -> None:
    """C-18: ``LoadedBars`` gains no field and its ``meta()`` no key."""
    loaded = _load(CannedPriceService(refused("unit_mismatch", T_15)), market="TW")

    assert not hasattr(loaded, "rejection")
    assert "rejection" not in loaded.meta()
    assert set(loaded.meta()) == set(LoadedBars().meta())


@pytest.mark.parametrize(
    "reason",
    [
        pytest.param(None, id="silent"),
        pytest.param(AV_QUOTA_REASON, id="provider-reason"),
        pytest.param(
            COOLDOWN_NO_CACHE_REASON.format(minutes=5, cooldown_hours=6), id="R-57-cooldown"
        ),
    ],
)
def test_an_ordinary_empty_answer_keeps_the_no_bars_sentence(reason: str | None) -> None:
    """(iii) ``rejection=None`` with no bars, including ADR-0009 D-8's cooldown (TA5 R-57)."""
    service = CannedPriceService(failed(reason))

    loaded = _load(service, market="TW", symbol="2330")

    assert loaded.reason == with_provider_reason(
        NO_BARS_REASON.format(market="TW", symbol="2330"), reason
    )
    if reason is not None:
        assert loaded.reason == (
            NO_BARS_REASON.format(market="TW", symbol="2330") + PROVIDER_REASON_PREFIX + reason
        )
    assert loaded.bars == []


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        pytest.param(DataStatus.FRESH, None, id="fresh"),
        pytest.param(DataStatus.CACHED_STALE, RECENT_ATTEMPT_FAILED_REASON, id="T-17-cache"),
        pytest.param(
            DataStatus.CACHED_STALE,
            _combine_reasons([AV_QUOTA_REASON, W_C_PRIME_US.format(provider="yfinance")]),
            id="W-c'+cache",
        ),
    ],
)
def test_an_answer_with_bars_keeps_its_reason_verbatim(
    status: DataStatus, reason: str | None
) -> None:
    """(i) the success path: reason as-is, no base sentence, no prefix (C-34 (b) pass-through)."""
    bars = recent_bars(trending_closes(10), symbol="AAPL", market="US", end=_END)
    service = CannedPriceService(answered(bars, status=status, reason=reason))

    loaded = _load(service, market="US", symbol="AAPL")

    assert loaded.reason == reason
    assert loaded.status is status
    assert len(loaded.bars) == 10
    if loaded.reason is not None:
        assert _NO_BARS_HEAD not in loaded.reason
        assert PROVIDER_REASON_PREFIX not in loaded.reason
