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

The ``hindsight`` regime (ignores ``recorded_at``) exists for the biased
research package only (ADR-0012 D-14). Its entry point here is the private
``_hindsight_view``; it is not exported, nothing under ``app.sectors`` may call
it, and ``app.research.sector_biased.hindsight_view`` (wave 2) is the only
sanctioned caller. ``tests/test_sectors_pit_invariance.py`` scans for it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Final, Literal
from zoneinfo import ZoneInfo

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


def _resolve_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """One row per ``(session_date, symbol)``: source priority, then latest run."""
    if bars.empty:
        return bars.copy()
    ranked = bars.assign(
        _priority=[
            BARS_SOURCE_PRIORITY.get(str(source), _UNKNOWN_SOURCE_PRIORITY)
            for source in bars["source"]
        ]
    )
    ranked = ranked.sort_values(
        ["session_date", "symbol", "_priority", "recorded_at", "run_id"],
        ascending=[True, True, True, False, True],
        kind="mergesort",
    )
    resolved = ranked.drop_duplicates(["session_date", "symbol"], keep="first")
    return resolved.drop(columns="_priority").reset_index(drop=True)


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
    ) -> None:
        if key is not _VIEW_KEY:
            raise TypeError("PointInTimePanel is built by MarketPanel.as_of() only")
        if regime not in ("pit", "hindsight"):
            raise ValueError(f"unknown regime {regime!r}")
        self._decision_date = decision_date
        self._regime: Regime = regime
        self._cutoff = cutoff_at
        self._bars = _resolve_bars(frames.bars)
        self._listing = frames.listing
        self._classification = frames.classification
        self._ex_dividend = frames.ex_dividend
        self._runs = frames.runs
        self._sessions: tuple[date, ...] = tuple(sorted(set(self._bars["session_date"])))

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
        mask = (self._bars["session_date"] >= start) & (self._bars["session_date"] <= end)
        return self._bars.loc[mask].reset_index(drop=True).copy()

    def field_matrix(
        self, field: str, days: Sequence[date], symbols: Sequence[str] | None = None
    ) -> pd.DataFrame:
        """``field`` as a ``days x symbols`` float matrix; absent bars are NaN."""
        if field not in BAR_FIELDS:
            raise KeyError(f"unknown bar field {field!r}")
        for day in days:
            self._check(day)
        wanted_days = list(days)
        rows = self._bars.loc[self._bars["session_date"].isin(set(wanted_days))]
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
        firsts = self._bars.groupby("symbol", sort=True)["session_date"].min()
        return {str(symbol): day for symbol, day in firsts.items()}

    def bars_source_on(self, day: date) -> str | None:
        """Source of the preferred resolved rows on ``day`` (the board's data source)."""
        self._check(day)
        rows = self._bars.loc[self._bars["session_date"] == day]
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

    __slots__ = ("_frames",)

    def __init__(self, frames: PanelFrames) -> None:
        self._frames = _normalise(frames)

    @property
    def frames(self) -> PanelFrames:
        """The normalised frames (results-side consumers such as labels only)."""
        return self._frames

    def as_of(self, t: date) -> PointInTimePanel:
        """The ``regime="pit"`` view of decision date ``t`` (ADR-0012 D-2, D-6)."""
        cut = cutoff(t)
        return PointInTimePanel(
            key=_VIEW_KEY,
            decision_date=t,
            regime="pit",
            cutoff_at=cut,
            frames=_visible(self._frames, t, cut),
        )


def _visible(frames: PanelFrames, t: date, cut: pd.Timestamp | None) -> PanelFrames:
    """Rows a decision on ``t`` may read; ``cut=None`` skips the recorded_at test."""

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
    return PointInTimePanel(
        key=_VIEW_KEY,
        decision_date=t,
        regime="hindsight",
        cutoff_at=None,
        frames=_visible(panel.frames, t, None),
    )
