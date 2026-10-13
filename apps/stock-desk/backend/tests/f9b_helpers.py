"""Shared fixtures for the F-9b consumer-side tests (ADR-0024 D-7 (7), D-7 (3)).

The consumers (``load_bars``'s W-d branch, the valuator's new token, the book's
cause group) land before any producer writes ``ProviderResult.rejection``
(TA5 section 3: consumers first), so these tests feed a refused answer through
a canned service built with the ``ProviderResult`` constructor -- never
``model_copy(update=...)``, which would skip the invariant validator.

The reason strings below are the risk-approved wording, so the pass-through is
checked against the real sentences (longest first: W-a alt-1). Each one is the
``app`` constant that owns it once its producer has landed (F-9b commits 5-7,
which carry the approval citations); until then it is copied verbatim as test
data. C and C' stay test data (their producer is F-9b2). Sources:

* W-a (alt-1), W-b (alt-2), W-c, W-c', C:
  ``work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md``
* T-13 (C'), T-15:
  ``work/reviews/2026-10-12-F-9-第二批字面逐字審-F9W-17至F9W-29-風控.md``
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.data.gate_wording import (
    CACHE_UNIT_REJECTED_REASON,
    SYMBOL_NOT_ADMITTED_REASON_TW,
    SYMBOL_NOT_ADMITTED_REASON_US,
    UNIT_MISMATCH_REASON_TW,
    UNIT_MISMATCH_REASON_US,
    UNIT_MISSING_REASON_TW,
    UNIT_MISSING_REASON_US,
)
from app.data.interface import DataStatus, Market, PriceBar, ProviderResult, Rejection

AS_OF = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)

# W-a / W-b are the app's own constants since F-9b commit 7 (verbatim against the
# ruling in ``test_f9b_admission_gate.py``).
W_A = SYMBOL_NOT_ADMITTED_REASON_US
W_B = SYMBOL_NOT_ADMITTED_REASON_TW
# W-c / W-c' are the app's own constants since F-9b commit 5 (verbatim against the
# ruling in ``test_f9b_live_currency_gate.py``).
W_C_US = UNIT_MISMATCH_REASON_US
W_C_TW = UNIT_MISMATCH_REASON_TW
W_C_PRIME_US = UNIT_MISSING_REASON_US
W_C_PRIME_TW = UNIT_MISSING_REASON_TW
C_COOLDOWN = (
    "本機尚無此標的可採用的日線資料。最近一次向來源取得的日線，標示的價格單位與市場所用的單位不同，"
    "已於約 {minutes} 分鐘前整段不採用；冷卻期為 {cooldown_hours} 小時，冷卻期內系統不會自動重試；"
    "冷卻期結束後的下一次查詢才會重新向來源取得。"
)
C_PRIME_COOLDOWN = (
    "本機尚無此標的可採用的日線資料。最近一次向來源取得的日線沒有標示價格單位，"
    "已於約 {minutes} 分鐘前整段不採用；冷卻期為 {cooldown_hours} 小時，冷卻期內系統不會自動重試；"
    "冷卻期結束後的下一次查詢才會重新向來源取得。"
)
# T-15 is the app's constant since F-9b commit 6 (verbatim against the ruling in
# ``test_f9b_cache_currency_gate.py``).
T_15 = CACHE_UNIT_REJECTED_REASON
#: An Alpha Vantage sentence as it reaches ``_combine_reasons`` (C-13 (4), (8)).
AV_QUOTA_REASON = "Alpha Vantage 今日查詢額度已用罄，本次不呼叫主來源，請由備援來源接手。"


def refused(rejection: Rejection, reason: str | None, *, source: str = "none") -> ProviderResult:
    """A refused answer, built through the constructor so the invariant runs."""
    return ProviderResult(
        bars=[],
        status=DataStatus.UNAVAILABLE,
        as_of=AS_OF,
        source=source,
        staleness_minutes=None,
        reason=reason,
        rejection=rejection,
    )


def failed(reason: str | None) -> ProviderResult:
    """An ordinary empty answer: ``UNAVAILABLE``, no bars, ``rejection=None`` (TA5 R-57)."""
    return ProviderResult(
        bars=[],
        status=DataStatus.UNAVAILABLE,
        as_of=AS_OF,
        source="none",
        staleness_minutes=None,
        reason=reason,
    )


class CannedPriceService:
    """A ``PriceService`` that answers every ask with one canned result.

    ``live`` answers ``get_daily_bars`` and ``cached`` answers
    ``get_cached_bars`` (defaulting to ``live``); each call is recorded so a
    test can tell which path was taken.
    """

    def __init__(self, live: ProviderResult, *, cached: ProviderResult | None = None) -> None:
        self.live = live
        self.cached = live if cached is None else cached
        self.calls: list[tuple[str, Market, date, date]] = []
        self.cached_calls: list[tuple[str, Market, date, date]] = []

    def get_daily_bars(self, symbol: str, market: Market, start: date, end: date) -> ProviderResult:
        self.calls.append((symbol, market, start, end))
        return self.live

    def get_cached_bars(
        self, symbol: str, market: Market, start: date, end: date
    ) -> ProviderResult:
        self.cached_calls.append((symbol, market, start, end))
        return self.cached


def answered(bars: list[PriceBar], *, status: DataStatus, reason: str | None) -> ProviderResult:
    """An answer with bars (``rejection`` is necessarily ``None``)."""
    return ProviderResult(
        bars=bars,
        status=status,
        as_of=AS_OF,
        source=bars[0].source if bars else "none",
        staleness_minutes=0,
        reason=reason,
    )
