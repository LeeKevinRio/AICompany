"""Market inputs: the ``^TWII`` snapshot of final bars (ADR-0030 D-1 ``inputs.py``, D-3, D-5).

The market input of the core comes from the index service only
(``app.services.index.load_market_benchmark``, ADR-0005 path, always
``backup``) and only its final bars enter a snapshot. This module turns that
service's answer into the snapshot and holds the snapshot shape rules:

* :func:`capture_market_snapshot` -- the recorder's entry. It takes the index
  service's answer and the snapshot size, keeps the bars that are final
  (``app.data.session_calendar.is_final``, ADR-0028 CS-17), and cuts the
  snapshot at the latest final bar: T is that bar's session (D-3 point 1). It
  has no T, ``as_of`` or clock parameter. Non-final bars are left out and
  listed in ``dropped``; whether a non-final latest bar means "re-fetch once,
  then ``inputs_not_ready``" (D-3 point 2) is the recorder's decision;
* :func:`_cut_snapshot` -- the one place a snapshot is cut (K-6): the bars on
  or before a session, the latest ``size`` of them. It takes the decision
  session as a parameter, so it stays private to ``app/outlook`` (risk RC-130:
  no T / ``as_of`` / clock parameter reaches the recorder's public functions);
* :func:`snapshot_view` -- the computation side's reading of a snapshot: it
  refuses any bar after T (freeze pack LA-G2-3: never silently ignored), any
  repeated or out-of-order session, and returns the closes by lag;
* :func:`late_cutoff_at` -- T's next calendar day at 00:00 Asia/Taipei (D-3
  point 3), the single definition; ``app/forecast/store.py`` uses it for
  ``late`` and the computation uses it for ``E-PIT-UNVERIFIED``.

Why the service's answer is passed in rather than fetched here: importing
``app.services.index`` would make ``app.outlook`` reach ``app.portfolio`` and
``app.positions`` (it imports ``app.portfolio.valuation.PriceService``), which
ADR-0030 K-2 and the ADR-0027 D-15 point 5 import-graph test forbid. The
answer is described by the :class:`IndexSeriesAnswer` Protocol, which
``app.services.index.LoadedBenchmark`` satisfies (tested); the caller that
holds the service passes ``load_market_benchmark(...)`` in.

Bar stamps: ``PriceBar`` carries one retrieval stamp, ``as_of`` (the adapter's
retrieval time, rewritten when a bar is fetched again). The snapshot's
``as_of`` and ``fetched_at`` are both that stamp; there is no other per-bar
fetch time on this path, and ``raw_timestamp_available`` is ``False``
(D-5 point 1).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Final, Literal, Protocol
from zoneinfo import ZoneInfo

from app.data.freshness import TW_POLICY
from app.data.interface import DataStatus, Market, PriceBar
from app.data.session_calendar import is_final

#: The market whose finality rule the TAIEX bars are judged by.
SNAPSHOT_MARKET: Final[Market] = "TW"
#: The one series of the market core (ADR-0030 D-1 point 1; ADR-0005).
SERIES_SYMBOL: Final = "^TWII"

DropReason = Literal["not_final"]


class FutureBarError(ValueError):
    """A bar after the decision session reached the computation (LA-G2-3)."""


class SnapshotShapeError(ValueError):
    """Bars that cannot form a snapshot: repeated or out-of-order sessions, wrong series."""


def late_cutoff_at(data_as_of: date) -> datetime:
    """T's next calendar day at 00:00:00 Asia/Taipei (D-3 point 3), in UTC."""
    local = datetime.combine(data_as_of + timedelta(days=1), time(0), ZoneInfo(TW_POLICY.timezone))
    return local.astimezone(UTC)


@dataclass(frozen=True)
class SnapshotBar:
    """One snapshot bar with exactly the D-5 point 1 contents."""

    session_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source: str
    as_of: datetime
    fetched_at: datetime

    def as_mapping(self) -> dict[str, object]:
        """The bar as the mapping ``app.forecast.canonical`` normalises."""
        return {
            "session_date": self.session_date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source": self.source,
            "as_of": self.as_of,
            "fetched_at": self.fetched_at,
        }


@dataclass(frozen=True)
class DroppedRow:
    """A bar the index service returned that is not in the snapshot."""

    session_date: date
    reason: DropReason


@dataclass(frozen=True)
class MarketSnapshot:
    """The snapshot of one run: final bars up to T, ascending, at most ``size`` of them."""

    bars: tuple[SnapshotBar, ...]
    source: str
    source_status: str
    staleness_minutes: int | None
    reason: str | None
    dropped: tuple[DroppedRow, ...]
    raw_timestamp_available: bool

    def __post_init__(self) -> None:
        if not self.bars:
            raise SnapshotShapeError("a snapshot holds at least one bar")

    @property
    def data_as_of(self) -> date:
        """T: the session of the snapshot's latest bar."""
        return self.bars[-1].session_date


class IndexSeriesAnswer(Protocol):
    """The part of ``app.services.index.LoadedBenchmark`` this module reads."""

    @property
    def series_symbol(self) -> str | None: ...

    @property
    def bars(self) -> Sequence[PriceBar]: ...

    @property
    def status(self) -> DataStatus: ...

    @property
    def source(self) -> str: ...

    @property
    def staleness_minutes(self) -> int | None: ...

    @property
    def reason(self) -> str | None: ...


def _snapshot_bar(bar: PriceBar) -> SnapshotBar:
    return SnapshotBar(
        session_date=bar.date,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        source=bar.source,
        as_of=bar.as_of,
        fetched_at=bar.as_of,
    )


def _require_ascending(sessions: Sequence[date]) -> None:
    if any(later <= earlier for earlier, later in zip(sessions, sessions[1:], strict=False)):
        raise SnapshotShapeError("bars must be in strictly ascending session order")


def _cut_snapshot(
    bars: Sequence[SnapshotBar], decision_date: date, size: int
) -> tuple[SnapshotBar, ...]:
    """The latest ``size`` bars on or before ``decision_date``, which must be one of them.

    Bars after ``decision_date`` are not read beyond their session, so nothing a
    later bar holds (its prices, a repeated or inserted session) can reach the
    snapshot. The kept bars must be strictly ascending. Private to
    ``app/outlook``: the only callers are :func:`capture_market_snapshot` (with
    T the latest final session) and the engine's look-ahead test entry.
    """
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise ValueError("size must be a positive int")
    kept = [bar for bar in bars if bar.session_date <= decision_date]
    _require_ascending([bar.session_date for bar in kept])
    if not kept or kept[-1].session_date != decision_date:
        raise SnapshotShapeError("the decision session is not a bar of the series")
    return tuple(kept[-size:])


def capture_market_snapshot(answer: IndexSeriesAnswer, *, size: int) -> MarketSnapshot | None:
    """The snapshot of the index service's ``answer``; ``None`` when no bar is final.

    T is the latest final bar's session. Every bar must be ``^TWII`` and the
    sessions strictly ascending (refused, never reordered); non-final bars are
    left out and listed in ``dropped``.
    """
    if answer.series_symbol != SERIES_SYMBOL:
        raise SnapshotShapeError(f"the market snapshot reads {SERIES_SYMBOL} only")
    if any(bar.symbol != SERIES_SYMBOL for bar in answer.bars):
        raise SnapshotShapeError(f"a bar of another series than {SERIES_SYMBOL}")
    _require_ascending([bar.date for bar in answer.bars])
    final: list[SnapshotBar] = []
    dropped: list[DroppedRow] = []
    for price_bar in answer.bars:
        bar = _snapshot_bar(price_bar)
        if is_final(SNAPSHOT_MARKET, bar.session_date, bar.as_of, bar.fetched_at):
            final.append(bar)
        else:
            dropped.append(DroppedRow(session_date=bar.session_date, reason="not_final"))
    if not final:
        return None
    return MarketSnapshot(
        bars=_cut_snapshot(final, final[-1].session_date, size),
        source=answer.source,
        source_status=answer.status.value,
        staleness_minutes=answer.staleness_minutes,
        reason=answer.reason,
        dropped=tuple(dropped),
        raw_timestamp_available=False,
    )


@dataclass(frozen=True)
class SnapshotView:
    """A snapshot as the computation reads it: closes by lag (lag 0 is T)."""

    data_as_of: date
    #: Sessions by lag: ``sessions_by_lag[k]`` is the session of lag ``k``.
    sessions_by_lag: tuple[date, ...]
    #: Closes by lag as doubles (``float(Decimal)``, correctly rounded); NaN stays NaN.
    closes_by_lag: tuple[float, ...]
    #: ``fetched_at`` by lag (as stored).
    fetched_by_lag: tuple[datetime, ...]


def _close_value(close: Decimal) -> float:
    if not isinstance(close, Decimal):
        raise TypeError("a snapshot close must be a Decimal")
    if close.is_snan():
        return math.nan
    return float(close)


def snapshot_view(bars: Sequence[SnapshotBar], *, data_as_of: date) -> SnapshotView:
    """Read ``bars`` as the snapshot of ``data_as_of``; any bar after it raises.

    The bars must be strictly ascending and end on ``data_as_of``.
    """
    if not bars:
        raise SnapshotShapeError("a snapshot holds at least one bar")
    late = [bar.session_date for bar in bars if bar.session_date > data_as_of]
    if late:
        raise FutureBarError(f"{len(late)} bar(s) after the decision session {data_as_of}")
    sessions = [bar.session_date for bar in bars]
    _require_ascending(sessions)
    if sessions[-1] != data_as_of:
        raise SnapshotShapeError("the snapshot does not end on its decision session")
    ordered = list(reversed(bars))
    return SnapshotView(
        data_as_of=data_as_of,
        sessions_by_lag=tuple(bar.session_date for bar in ordered),
        closes_by_lag=tuple(_close_value(bar.close) for bar in ordered),
        fetched_by_lag=tuple(bar.fetched_at for bar in ordered),
    )
