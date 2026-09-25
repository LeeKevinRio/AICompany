"""Point-in-time market panel types (ADR-0012 D-1, D-2, D-6).

This module is pure: pandas only, no I/O, no network, no ``app.*`` imports
beyond the standard library. It is the single contract between the market
DB store (``app.data.market_panel``, which *produces* ``PanelFrames``) and
the sector core (``app.sectors``, which only ever *consumes* a
``PointInTimePanel`` built from them).

``PanelFrames`` below is the frozen wire shape. Column names and dtypes are
part of the contract; changing them is an ADR-0012 change.

``MarketPanel`` / ``PointInTimePanel`` are implemented by dev-lead in wave 1
(ADR-0012 D-6, C-13/C-14): ``MarketPanel.as_of(t)`` is the ONLY constructor of
a ``regime="pit"`` view, keeps rows with ``session_date <= t`` AND
``recorded_at <= cutoff(t)`` (cutoff = 23:59:59 Asia/Taipei on t), and raises
on any access outside that window.

Visibility rules applied by ``as_of`` (ADR-0012 D-2):

* a row is visible only when its own ``recorded_at <= cutoff(t)`` and
  ``session_date <= t`` **and** its run is a visible ``status == "ok"`` run of
  the matching kind; ``partial`` / ``failed`` / ``quality_failed`` runs never
  feed a decision;
* bars: when several visible ok runs describe the same ``(session_date,
  symbol)``, the primary source wins (``twse_snapshot`` before ``finmind``),
  then the most recently recorded run (a correction is a new run), then
  ``run_id`` for determinism. No row is rewritten;
* listing / classification: the latest visible ok run is the snapshot in force
  (carried forward on days without a new run; the view reports how many
  sessions it has been carried);
* ex-dividend announcements: the union of every visible ok run, because
  ``TWT48U_ALL`` lists upcoming events only and drops them once they happen.

Producer contract this module relies on: every run's rows are listed under
that run's own ``run_id`` (the content-addressed ``pit_*_rows`` tables are
expanded per run by ``app.data.market_panel``), so a run's snapshot is exactly
the rows carrying its ``run_id``.

Speed (wave 3): :func:`_visible` and :func:`_resolve_bars` are the reference
definition of the rules above. ``MarketPanel`` answers ``as_of`` through
:class:`_PanelIndex` instead -- the history is sorted once with the resolution
keys, and each view is a prefix slice plus vectorised masks -- and must return
the same rows, order and dtypes (``tests/test_panel_index_equivalence.py``,
part of the NE-7 attestation set). No decision or view is cached.

The ``hindsight`` regime (ignores ``recorded_at``) exists for the biased
research package only (ADR-0012 D-14). Its entry point here is the private
``_hindsight_view``; it is not exported, nothing under ``app.sectors`` may call
it, and ``app.research.sector_biased.hindsight_view`` (wave 2) is the only
sanctioned caller. ``tests/test_research_isolation.py`` fails if it is defined
anywhere but here, referenced outside ``app/research/``, or if ``_VIEW_KEY``
(which could build such a view directly) appears outside this module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Final, Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

#: Columns of ``PanelFrames.bars`` (one row per snapshot run x symbol).
BARS_COLUMNS: tuple[str, ...] = (
    "run_id",  # str, pit_snapshot_runs.run_id
    "session_date",  # datetime.date, the trading session the row describes
    "recorded_at",  # pandas Timestamp, tz-aware UTC; store clock, never caller-supplied
    "source",  # str, e.g. "twse_snapshot" | "finmind_warmup" | "demo_synthetic"
    "symbol",  # str
    "open",  # float
    "high",  # float
    "low",  # float
    "close",  # float
    "shares",  # int, traded shares
    "traded_value",  # float, NT$
    "change",  # float | NaN, price change vs reference price
)

#: Columns of ``PanelFrames.listing`` (who was listed, as captured that day).
LISTING_COLUMNS: tuple[str, ...] = (
    "run_id",
    "session_date",
    "recorded_at",
    "symbol",
    "security_type",
)

#: Columns of ``PanelFrames.classification`` (official TWSE industry, as captured that day).
CLASSIFICATION_COLUMNS: tuple[str, ...] = (
    "run_id",
    "session_date",
    "recorded_at",
    "symbol",
    "sector_code",
    "sector_name",
)

#: Columns of ``PanelFrames.ex_dividend`` (TWT48U_ALL announcements, as captured that day).
EX_DIVIDEND_COLUMNS: tuple[str, ...] = (
    "run_id",
    "session_date",
    "recorded_at",
    "symbol",
    "ex_date",
)

#: Columns of ``PanelFrames.runs`` (one row per pit_snapshot_runs row).
RUNS_COLUMNS: tuple[str, ...] = (
    "run_id",
    "kind",  # "bars" | "listing" | "classification" | "dividend_announce"
    "session_date",
    "recorded_at",
    "source",
    "status",  # "ok" | "partial" | "failed" | "quality_failed"
    "row_count",
    "expected_count",
)


@dataclass(frozen=True)
class PanelFrames:
    """Raw append-only snapshot rows read from the market DB, un-filtered by time.

    Produced by ``app.data.market_panel`` (data-engineer). Every frame carries
    ``recorded_at`` so the point-in-time view can hide anything recorded after
    the decision cutoff. Frames may be empty but must always have exactly the
    columns declared above.
    """

    bars: pd.DataFrame
    listing: pd.DataFrame
    classification: pd.DataFrame
    ex_dividend: pd.DataFrame
    runs: pd.DataFrame


# ---------------------------------------------------------------------------
# Point-in-time views (ADR-0012 D-6, C-14)
# ---------------------------------------------------------------------------

#: The exchange's clock; ``cutoff(t)`` is 23:59:59 on ``t`` in this zone.
TAIPEI: Final = ZoneInfo("Asia/Taipei")

Regime = Literal["pit", "hindsight"]
SnapshotKind = Literal["listing", "classification"]
RunKind = Literal["bars", "listing", "classification", "dividend_announce"]

#: Bar fields a view hands out through :meth:`PointInTimePanel.field_matrix`.
BAR_FIELDS: Final[frozenset[str]] = frozenset(
    {"open", "high", "low", "close", "shares", "traded_value", "change"}
)

#: Lower is preferred when two ok runs describe the same session and symbol
#: (ADR-0012 D-2 「主來源優先」). Unknown sources rank last.
BARS_SOURCE_PRIORITY: Final[Mapping[str, int]] = {
    "twse_snapshot": 0,
    "finmind": 1,
    "finmind_warmup": 1,
}
_UNKNOWN_SOURCE_PRIORITY: Final = 9

_FRAME_COLUMNS: Final[Mapping[str, tuple[str, ...]]] = {
    "bars": BARS_COLUMNS,
    "listing": LISTING_COLUMNS,
    "classification": CLASSIFICATION_COLUMNS,
    "ex_dividend": EX_DIVIDEND_COLUMNS,
    "runs": RUNS_COLUMNS,
}

#: The run kind whose ok runs gate each row frame.
_FRAME_RUN_KIND: Final[Mapping[str, str]] = {
    "bars": "bars",
    "listing": "listing",
    "classification": "classification",
    "ex_dividend": "dividend_announce",
}


class PointInTimeViolation(LookupError):
    """A view was asked for data past its decision date (ADR-0012 C-14, T-5)."""


def cutoff(t: date) -> pd.Timestamp:
    """The last instant a row may be recorded and still inform day ``t``, in UTC."""
    local = datetime.combine(t, time(23, 59, 59), tzinfo=TAIPEI)
    return pd.Timestamp(local).tz_convert("UTC")


def _as_dates(column: pd.Series) -> pd.Series:
    if column.empty:
        return pd.Series([], dtype=object, index=column.index)
    return pd.Series(pd.to_datetime(column).dt.date, dtype=object, index=column.index)


def _as_utc(column: pd.Series, frame_name: str) -> pd.Series:
    converted = pd.to_datetime(column)
    tz = getattr(converted.dt, "tz", None)
    if tz is None:
        if not column.empty:
            # A naive timestamp would silently shift every cutoff by 8 hours.
            raise ValueError(f"{frame_name}.recorded_at must be timezone-aware")
        return converted.dt.tz_localize("UTC")
    return converted.dt.tz_convert("UTC")


def _normalise(frames: PanelFrames) -> PanelFrames:
    """Copy the frames down to the declared columns with canonical dtypes."""
    out: dict[str, pd.DataFrame] = {}
    for name, columns in _FRAME_COLUMNS.items():
        frame: pd.DataFrame = getattr(frames, name)
        missing = [column for column in columns if column not in frame.columns]
        if missing:
            raise ValueError(f"PanelFrames.{name} is missing columns {missing}")
        copy = frame.loc[:, list(columns)].copy().reset_index(drop=True)
        copy["session_date"] = _as_dates(copy["session_date"])
        copy["recorded_at"] = _as_utc(copy["recorded_at"], name)
        copy["run_id"] = copy["run_id"].astype(str)
        if name == "ex_dividend":
            copy["ex_date"] = _as_dates(copy["ex_date"])
        if "symbol" in copy.columns:
            copy["symbol"] = copy["symbol"].astype(str)
        out[name] = copy
    return PanelFrames(**out)


#: Sort keys of bar resolution: session, symbol, source priority, newest record, run id.
_RESOLVE_KEYS: Final = ["session_date", "symbol", "_priority", "recorded_at", "run_id"]
_RESOLVE_ASCENDING: Final = [True, True, True, False, True]


def _with_priority(bars: pd.DataFrame) -> pd.DataFrame:
    return bars.assign(
        _priority=[
            BARS_SOURCE_PRIORITY.get(str(source), _UNKNOWN_SOURCE_PRIORITY)
            for source in bars["source"]
        ]
    )


def _resolve_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """One row per ``(session_date, symbol)``: source priority, then latest run.

    The reference definition of bar resolution. :class:`MarketPanel` answers
    the same question through :class:`_PanelIndex` (one sort for the whole
    history instead of one per view); ``tests/test_panel_index_equivalence.py``
    holds the two bit for bit equal.
    """
    if bars.empty:
        return bars.copy()
    ranked = _with_priority(bars).sort_values(
        _RESOLVE_KEYS, ascending=_RESOLVE_ASCENDING, kind="mergesort"
    )
    resolved = ranked.drop_duplicates(["session_date", "symbol"], keep="first")
    return resolved.drop(columns="_priority").reset_index(drop=True)


#: Sorts after every real ordinal / timestamp: a missing date or record time is never visible.
_NEVER: Final = np.iinfo(np.int64).max
#: ``date(1970, 1, 1).toordinal()``: day 0 of ``datetime64[D]``.
_EPOCH_ORDINAL: Final = date(1970, 1, 1).toordinal()


def _ordinals(column: pd.Series) -> np.ndarray:
    """``date.toordinal()`` per row, vectorised; a missing date maps to :data:`_NEVER`."""
    if column.empty:
        return np.empty(0, dtype=np.int64)
    stamps = pd.to_datetime(column, errors="coerce")
    days = stamps.to_numpy().astype("datetime64[D]").astype(np.int64) + _EPOCH_ORDINAL
    days[stamps.isna().to_numpy()] = _NEVER
    return np.asarray(days, dtype=np.int64)


def _nanoseconds(column: pd.Series) -> np.ndarray:
    """UTC nanoseconds per row (``recorded_at`` is tz-aware UTC); NaT maps to :data:`_NEVER`."""
    if column.empty:
        return np.empty(0, dtype=np.int64)
    values = np.array(column.array.as_unit("ns").asi8, dtype=np.int64)
    values[column.isna().to_numpy()] = _NEVER
    return values


@dataclass(frozen=True)
class _ResolvedBars:
    """A view's resolved bars plus the keys its accessors slice by (rows sorted by session)."""

    frame: pd.DataFrame
    #: Session ordinal per row, ascending (resolution sorts by session first).
    sessions: np.ndarray
    #: Per row, a code into ``symbol_names`` (a factorisation of the symbols).
    symbol_codes: np.ndarray
    symbol_names: np.ndarray


@dataclass(frozen=True)
class _FrameKeys:
    """Per-row visibility keys of one normalised frame, in the frame's own row order."""

    session: np.ndarray
    recorded: np.ndarray
    #: Code of the row's ``run_id`` in the panel-wide run-id factorisation.
    run: np.ndarray


def _resolution_order(bars: pd.DataFrame, keys: _FrameKeys, symbol_codes: np.ndarray) -> np.ndarray:
    """Row order of :func:`_resolve_bars`'s sort, computed from integer keys.

    Session ascending, symbol ascending (``symbol_codes`` come from a sorted
    factorisation), source priority ascending, ``recorded_at`` descending, run
    id ascending; a missing date or record time sorts last, as pandas puts
    ``NaT`` last. ``np.lexsort`` is stable, so rows equal on every key keep the
    frame's own order -- exactly what the reference's ``kind="mergesort"`` does.
    """
    if bars.empty:
        return np.empty(0, dtype=np.int64)
    priority = (
        bars["source"]
        .astype(str)
        .map(BARS_SOURCE_PRIORITY)
        .fillna(_UNKNOWN_SOURCE_PRIORITY)
        .to_numpy(dtype=np.int64)
    )
    newest_first = np.where(keys.recorded == _NEVER, _NEVER, -keys.recorded)
    run_codes, _ = pd.factorize(bars["run_id"].to_numpy(dtype=object), sort=True)
    # np.lexsort sorts by the last key first.
    return np.lexsort(
        (np.asarray(run_codes), newest_first, priority, symbol_codes, keys.session)
    ).astype(np.int64)


class _PanelIndex:
    """Precomputed keys that make :meth:`MarketPanel.as_of` a slice, not a re-sort.

    Built once per :class:`MarketPanel`. It is a pure acceleration of
    :func:`_visible` followed by :func:`_resolve_bars` -- the same rows, in the
    same order, with the same dtypes (``tests/test_panel_index_equivalence.py``)
    -- and holds no decision, no ranking and no per-date cache:

    * the bars are stably sorted **once** with exactly the resolution keys, so
      the rows of any view are a subsequence of that order; ``session_date <=
      t`` is then a prefix found by ``searchsorted``, and "first row per
      ``(session, symbol)``" is a comparison with the previous row;
    * ``run_id`` is factorised once across all frames, so "the run is a visible
      ok run of the matching kind" is an array lookup instead of a string
      ``isin``;
    * dates and record times are integer arrays, so the window tests are
      vectorised comparisons instead of object comparisons.
    """

    __slots__ = (
        "_bar_order",
        "_bar_symbol",
        "_frames",
        "_keys",
        "_kind",
        "_ok",
        "_run_codes",
        "_sorted",
        "_symbol_names",
    )

    def __init__(self, frames: PanelFrames) -> None:
        self._frames = frames
        names = tuple(_FRAME_COLUMNS)
        ids = [getattr(frames, name)["run_id"].to_numpy(dtype=object) for name in names]
        codes, uniques = pd.factorize(np.concatenate(ids))
        self._run_codes = len(uniques)
        bounds = np.cumsum([0, *(len(part) for part in ids)])
        self._keys: dict[str, _FrameKeys] = {}
        for position, name in enumerate(names):
            frame: pd.DataFrame = getattr(frames, name)
            self._keys[name] = _FrameKeys(
                session=_ordinals(frame["session_date"]),
                recorded=_nanoseconds(frame["recorded_at"]),
                run=np.asarray(codes[bounds[position] : bounds[position + 1]], dtype=np.int64),
            )
        runs = frames.runs
        self._ok = (runs["status"] == "ok").to_numpy(dtype=bool)
        self._kind = runs["kind"].to_numpy(dtype=object)

        bars = frames.bars
        keys = self._keys["bars"]
        # Sorted factorisation: code order == string order, as the reference sort has it.
        codes_by_symbol, symbol_names = pd.factorize(
            bars["symbol"].to_numpy(dtype=object), sort=True
        )
        symbol_codes = np.asarray(codes_by_symbol, dtype=np.int64)
        order = _resolution_order(bars, keys, symbol_codes)
        self._bar_order = order
        self._bar_symbol = symbol_codes[order]
        self._symbol_names = np.asarray(symbol_names, dtype=object)
        self._sorted = _FrameKeys(
            session=keys.session[order], recorded=keys.recorded[order], run=keys.run[order]
        )

    def _window(self, keys: _FrameKeys, t_ord: int, cut_ns: int | None) -> np.ndarray:
        mask = keys.session <= t_ord
        if cut_ns is not None:
            mask &= keys.recorded <= cut_ns
        return mask

    def visible(self, t: date, cut: pd.Timestamp | None) -> tuple[PanelFrames, _ResolvedBars]:
        """:func:`_visible` then :func:`_resolve_bars`, answered from the precomputed keys."""
        t_ord = t.toordinal()
        cut_ns = int(cut.value) if cut is not None else None
        frames = self._frames
        run_mask = self._window(self._keys["runs"], t_ord, cut_ns)
        ok_runs = run_mask & self._ok
        run_codes = self._keys["runs"].run
        ok_lookup: dict[str, np.ndarray] = {}
        for name, kind in _FRAME_RUN_KIND.items():
            lookup = np.zeros(self._run_codes, dtype=bool)
            lookup[run_codes[ok_runs & (self._kind == kind)]] = True
            ok_lookup[name] = lookup
        resolved = self._resolve(t_ord, cut_ns, ok_lookup["bars"])
        out: dict[str, pd.DataFrame] = {
            "runs": frames.runs.take(np.flatnonzero(run_mask)).reset_index(drop=True),
            "bars": resolved.frame,
        }
        for name in ("listing", "classification", "ex_dividend"):
            keys = self._keys[name]
            mask = self._window(keys, t_ord, cut_ns)
            if name == "ex_dividend":
                mask &= ok_lookup[name][keys.run]
            else:
                # Only the snapshot in force is ever read (PointInTimePanel.snapshot),
                # so keep that run's rows and nothing else.
                mask &= keys.run == self._latest_run(out["runs"], run_codes, run_mask, name)
            frame: pd.DataFrame = getattr(frames, name)
            out[name] = frame.take(np.flatnonzero(mask)).reset_index(drop=True)
        return PanelFrames(**out), resolved

    def _latest_run(
        self, visible_runs: pd.DataFrame, run_codes: np.ndarray, run_mask: np.ndarray, kind: str
    ) -> int:
        """Code of the run :meth:`PointInTimePanel.snapshot` picks for ``kind``; -1 if none."""
        codes = run_codes[run_mask]
        candidates = np.flatnonzero(
            (visible_runs["kind"] == kind).to_numpy(dtype=bool)
            & (visible_runs["status"] == "ok").to_numpy(dtype=bool)
        )
        if candidates.size == 0:
            return -1
        ordered = visible_runs.take(candidates).sort_values(
            ["session_date", "recorded_at", "run_id"], kind="mergesort"
        )
        # ``take`` keeps the row labels of ``visible_runs`` (a RangeIndex): a position.
        return int(codes[int(ordered.index[-1])])

    def _resolve(self, t_ord: int, cut_ns: int | None, ok_lookup: np.ndarray) -> _ResolvedBars:
        keys = self._sorted
        prefix = int(np.searchsorted(keys.session, t_ord, side="right"))
        mask = ok_lookup[keys.run[:prefix]]
        if cut_ns is not None:
            mask &= keys.recorded[:prefix] <= cut_ns
        rows = np.flatnonzero(mask)
        sessions = keys.session[rows]
        symbols = self._bar_symbol[rows]
        first = np.ones(rows.size, dtype=bool)
        first[1:] = (sessions[1:] != sessions[:-1]) | (symbols[1:] != symbols[:-1])
        picked = rows[first]
        frame = self._frames.bars.take(self._bar_order[picked]).reset_index(drop=True)
        return _ResolvedBars(
            frame=frame,
            sessions=keys.session[picked],
            symbol_codes=self._bar_symbol[picked],
            symbol_names=self._symbol_names,
        )


@dataclass(frozen=True)
class Snapshot:
    """The listing or classification snapshot in force on the decision date."""

    run_id: str
    session_date: date
    recorded_at: pd.Timestamp
    #: Visible sessions after the snapshot's own session, up to the decision
    #: date: 0 when captured that day, >0 when carried forward (D-2).
    carried_sessions: int
    rows: pd.DataFrame

    @property
    def carried_forward(self) -> bool:
        return self.carried_sessions > 0


_VIEW_KEY: Final = object()


class PointInTimePanel:
    """What was knowable at the close of ``decision_date`` -- and nothing else.

    Instances come from :meth:`MarketPanel.as_of` (``regime="pit"``); direct
    construction raises. Every accessor that takes a date refuses one past the
    decision date with :class:`PointInTimeViolation`, and the frames held here
    were filtered before the view existed, so there is no later row to leak.
    Accessors return copies.
    """

    __slots__ = (
        "_bar_sessions",
        "_bar_symbols",
        "_bars",
        "_classification",
        "_cutoff",
        "_decision_date",
        "_ex_dividend",
        "_listing",
        "_regime",
        "_runs",
        "_sessions",
    )

    def __init__(
        self,
        *,
        key: object,
        decision_date: date,
        regime: Regime,
        cutoff_at: pd.Timestamp | None,
        frames: PanelFrames,
        resolved: _ResolvedBars | None = None,
    ) -> None:
        if key is not _VIEW_KEY:
            raise TypeError("PointInTimePanel is built by MarketPanel.as_of() only")
        if regime not in ("pit", "hindsight"):
            raise ValueError(f"unknown regime {regime!r}")
        self._decision_date = decision_date
        self._regime: Regime = regime
        self._cutoff = cutoff_at
        if resolved is None:
            # Reference path: resolve the visible rows here (the indexed path
            # hands in the identical result, already resolved).
            bars = _resolve_bars(frames.bars)
            codes, names = pd.factorize(bars["symbol"].to_numpy(dtype=object))
            resolved = _ResolvedBars(
                frame=bars,
                sessions=_ordinals(bars["session_date"]),
                symbol_codes=np.asarray(codes, dtype=np.int64),
                symbol_names=np.asarray(names, dtype=object),
            )
        self._bars = resolved.frame
        self._bar_sessions = resolved.sessions
        self._bar_symbols = (resolved.symbol_codes, resolved.symbol_names)
        self._listing = frames.listing
        self._classification = frames.classification
        self._ex_dividend = frames.ex_dividend
        self._runs = frames.runs
        self._sessions: tuple[date, ...] = tuple(
            date.fromordinal(int(ordinal)) for ordinal in np.unique(self._bar_sessions)
        )

    def _session_rows(self, first: date, last: date) -> slice:
        """Row positions of resolved bars with ``first <= session_date <= last``."""
        low = int(np.searchsorted(self._bar_sessions, first.toordinal(), side="left"))
        high = int(np.searchsorted(self._bar_sessions, last.toordinal(), side="right"))
        return slice(low, max(low, high))

    # -- identity -----------------------------------------------------------

    @property
    def decision_date(self) -> date:
        return self._decision_date

    @property
    def regime(self) -> Regime:
        return self._regime

    @property
    def cutoff(self) -> pd.Timestamp | None:
        """``cutoff(decision_date)`` for ``pit``; ``None`` for ``hindsight``."""
        return self._cutoff

    # -- guards --------------------------------------------------------------

    def _check(self, day: date) -> None:
        if day > self._decision_date:
            raise PointInTimeViolation(
                f"{day.isoformat()} is after the decision date "
                f"{self._decision_date.isoformat()} of this view"
            )

    # -- bars ----------------------------------------------------------------

    @property
    def sessions(self) -> tuple[date, ...]:
        """Visible trading sessions (dates with at least one resolved bar), ascending."""
        return self._sessions

    def sessions_before(self, day: date, count: int) -> tuple[date, ...]:
        """Up to ``count`` visible sessions strictly before ``day``, ascending."""
        self._check(day)
        if count <= 0:
            return ()
        earlier = [session for session in self._sessions if session < day]
        return tuple(earlier[-count:])

    def bars(self, start: date, end: date) -> pd.DataFrame:
        """Resolved bar rows with ``start <= session_date <= end``."""
        self._check(end)
        return self._bars.iloc[self._session_rows(start, end)].reset_index(drop=True).copy()

    def field_matrix(
        self, field: str, days: Sequence[date], symbols: Sequence[str] | None = None
    ) -> pd.DataFrame:
        """``field`` as a ``days x symbols`` float matrix; absent bars are NaN."""
        if field not in BAR_FIELDS:
            raise KeyError(f"unknown bar field {field!r}")
        for day in days:
            self._check(day)
        wanted_days = list(days)
        # Rows of each wanted session are one contiguous block (resolution sorts
        # by session first); taking the blocks in session order keeps the rows
        # in the frame's own order, exactly as a boolean ``isin`` mask would.
        blocks = [
            np.arange(block.start, block.stop)
            for day in sorted(set(wanted_days))
            if (block := self._session_rows(day, day)).stop > block.start
        ]
        positions = np.concatenate(blocks) if blocks else np.empty(0, dtype=np.int64)
        rows = self._bars.iloc[positions]
        if symbols is not None:
            rows = rows.loc[rows["symbol"].isin(set(symbols))]
        values = pd.to_numeric(rows[field], errors="coerce").astype(float)
        matrix = (
            pd.DataFrame(
                {"session_date": rows["session_date"], "symbol": rows["symbol"], "v": values}
            )
            .pivot(index="session_date", columns="symbol", values="v")
            .reindex(index=wanted_days)
        )
        if symbols is not None:
            matrix = matrix.reindex(columns=list(symbols))
        return matrix.astype(float)

    def first_bar_sessions(self) -> dict[str, date]:
        """The earliest visible session each symbol has a bar on."""
        if self._bars.empty:
            return {}
        # Rows are sorted by session, so a symbol's first row is its earliest session.
        codes, names = self._bar_symbols
        present, first_rows = np.unique(codes, return_index=True)
        sessions = self._bars["session_date"].to_numpy(dtype=object)
        firsts = {
            str(names[code]): sessions[row] for code, row in zip(present, first_rows, strict=True)
        }
        return {symbol: firsts[symbol] for symbol in sorted(firsts)}

    def bars_source_on(self, day: date) -> str | None:
        """Source of the preferred resolved rows on ``day`` (the board's data source)."""
        self._check(day)
        rows = self._bars.iloc[self._session_rows(day, day)]
        if rows.empty:
            return None
        counts = rows["source"].astype(str).value_counts()
        ordered = sorted(
            counts.index,
            key=lambda source: (
                BARS_SOURCE_PRIORITY.get(source, _UNKNOWN_SOURCE_PRIORITY),
                -int(counts[source]),
                source,
            ),
        )
        return str(ordered[0])

    # -- snapshots -----------------------------------------------------------

    def snapshot(self, kind: SnapshotKind) -> Snapshot | None:
        """The latest visible ok listing / classification snapshot, or ``None``."""
        runs = self._runs.loc[(self._runs["kind"] == kind) & (self._runs["status"] == "ok")]
        if runs.empty:
            return None
        latest = runs.sort_values(["session_date", "recorded_at", "run_id"], kind="mergesort").iloc[
            -1
        ]
        frame = self._listing if kind == "listing" else self._classification
        rows = frame.loc[frame["run_id"] == latest["run_id"]].reset_index(drop=True).copy()
        run_session: date = latest["session_date"]
        carried = sum(1 for session in self._sessions if run_session < session)
        return Snapshot(
            run_id=str(latest["run_id"]),
            session_date=run_session,
            recorded_at=latest["recorded_at"],
            carried_sessions=carried,
            rows=rows,
        )

    def ex_dividend_announcements(self) -> pd.DataFrame:
        """Distinct ``(symbol, ex_date)`` pairs announced in any visible ok run."""
        rows = self._ex_dividend.loc[:, ["symbol", "ex_date"]].drop_duplicates()
        return rows.sort_values(["symbol", "ex_date"], kind="mergesort").reset_index(drop=True)

    def ok_run_sessions(self, kind: RunKind) -> frozenset[date]:
        """Session dates that have a visible ``ok`` run of ``kind``."""
        runs = self._runs.loc[(self._runs["kind"] == kind) & (self._runs["status"] == "ok")]
        return frozenset(runs["session_date"])

    def visible_runs(self) -> pd.DataFrame:
        """Every visible run, whatever its status (provenance and diagnostics)."""
        return self._runs.copy()


class MarketPanel:
    """The full append-only snapshot history, un-filtered by time.

    Holding a ``MarketPanel`` is holding the future; the pure sector core never
    receives one (C-14). Decisions go through :meth:`as_of`.
    """

    __slots__ = ("_frames", "_index")

    def __init__(self, frames: PanelFrames) -> None:
        self._frames = _normalise(frames)
        self._index = _PanelIndex(self._frames)

    @property
    def frames(self) -> PanelFrames:
        """The normalised frames (results-side consumers such as labels only)."""
        return self._frames

    def as_of(self, t: date) -> PointInTimePanel:
        """The ``regime="pit"`` view of decision date ``t`` (ADR-0012 D-2, D-6)."""
        cut = cutoff(t)
        frames, resolved = self._index.visible(t, cut)
        return PointInTimePanel(
            key=_VIEW_KEY,
            decision_date=t,
            regime="pit",
            cutoff_at=cut,
            frames=frames,
            resolved=resolved,
        )


def _visible(frames: PanelFrames, t: date, cut: pd.Timestamp | None) -> PanelFrames:
    """Rows a decision on ``t`` may read; ``cut=None`` skips the recorded_at test.

    The reference definition of visibility; :class:`_PanelIndex` answers the
    same question for :meth:`MarketPanel.as_of` and must stay bit-identical to
    it (``tests/test_panel_index_equivalence.py``).
    """

    def in_window(frame: pd.DataFrame) -> pd.Series:
        mask = frame["session_date"] <= t
        if cut is not None:
            mask &= frame["recorded_at"] <= cut
        return mask

    runs = frames.runs.loc[in_window(frames.runs)].reset_index(drop=True)
    ok_runs = runs.loc[runs["status"] == "ok"]
    out: dict[str, pd.DataFrame] = {"runs": runs.copy()}
    for name, kind in _FRAME_RUN_KIND.items():
        frame: pd.DataFrame = getattr(frames, name)
        ok_ids = set(ok_runs.loc[ok_runs["kind"] == kind, "run_id"])
        mask = in_window(frame) & frame["run_id"].isin(ok_ids)
        out[name] = frame.loc[mask].reset_index(drop=True).copy()
    return PanelFrames(**out)


def _hindsight_view(panel: MarketPanel, t: date) -> PointInTimePanel:
    """Biased view that ignores ``recorded_at`` -- research package ONLY (D-14).

    Private on purpose: the sanctioned caller is
    ``app.research.sector_biased.hindsight_view`` (wave 2). Anything else that
    reaches for it is a look-ahead leak; the source scan in
    ``tests/test_sectors_pit_invariance.py`` fails if it appears outside this
    module and ``app/research/``.
    """
    frames, resolved = panel._index.visible(t, None)
    return PointInTimePanel(
        key=_VIEW_KEY,
        decision_date=t,
        regime="hindsight",
        cutoff_at=None,
        frames=frames,
        resolved=resolved,
    )
