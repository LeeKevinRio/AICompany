"""The biased sector-momentum study on back-filled history (methodology §5.3, §5.4).

Pipeline validation and orders of magnitude only -- **never a judgement**, never
a parameter choice (methodology §5.4: an idea born from these numbers is a new
version and counts towards m). It runs the exact same decision and label code
as the judged evaluator (``sector_eval.evaluate_views``), with one difference:
each decision reads :func:`hindsight_view` instead of ``panel.as_of``. The
regime is recorded as ``hindsight`` throughout, so nothing produced here can
become a ``sector_rank_stats`` row.

Backtest-protocol rule 3 applies in full here (unlike the forward judged data):
``walk_forward_splits(train=504, test=126, step=126)`` over the decision
sessions, in-sample and out-of-sample reported apart. There is nothing to fit,
so the split is a reporting discipline; the numbers still come with the label.

:func:`backfill_frames` turns back-filled bars plus *today's* listing and
classification into panel frames: the classic survivorship and classification
look-ahead set-up, recorded at fetch time so that no point-in-time view can
see any of it (only :func:`hindsight_view` can).

Data scope (ADR-0012 D-15, C-49; the sensitivity variants of
:mod:`.sensitivity` run through the same gate): a study reads hindsight views
only and its result must say ``regime="hindsight"``; every run in the panel is
``backfill_non_pit``; and every ``session_date`` precedes D0, which is read
from the market DB (read-only, D-12: the first session all four kinds were
``ok``; no D0 yet means no date limit). Any violation raises
:class:`BiasedScopeViolation` before anything is computed or written.
"""

from __future__ import annotations

import dataclasses
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Final, Literal

import pandas as pd

from app.backtest.costs import CostModel
from app.backtest.report import PerformanceMetrics, build_segment_report
from app.backtest.sector_eval import (
    EngineRun,
    RateSummary,
    SectorStatistics,
    Week,
    evaluate_views,
    summarise,
)
from app.backtest.splits import walk_forward_splits
from app.data.market_panel import MarketPanelReader
from app.data.panel import (
    BARS_COLUMNS,
    CLASSIFICATION_COLUMNS,
    EX_DIVIDEND_COLUMNS,
    LISTING_COLUMNS,
    RUNS_COLUMNS,
    MarketPanel,
    PanelFrames,
)
from app.research.sector_biased.hindsight import BIAS_DIRECTIONS, BIAS_LABEL, hindsight_view
from app.research.sector_biased.store import DATA_REGIME, ResearchStore
from app.sectors.definition import SectorEvalDefinition, SectorMomentumDefinition

#: Walk-forward geometry of the biased study (methodology §5.3).
TRAIN_SESSIONS: Final = 504
TEST_SESSIONS: Final = 126
BACKFILL_SOURCE: Final = "backfill_non_pit"

Segment = Literal["in_sample", "out_of_sample", "full"]

#: ``PanelFrames`` members that carry a ``session_date`` column (all checked against D0).
_DATED_FRAMES: Final = ("runs", "bars", "listing", "classification", "ex_dividend")


class BiasedScopeViolation(ValueError):
    """The biased study was handed data outside its scope (ADR-0012 D-15, C-49)."""


@dataclass(frozen=True)
class BiasedScope:
    """What :func:`admit_biased_panel` established about a panel."""

    #: D0 read from the market DB; ``None`` while there is none (no date limit).
    d0: date | None
    #: The latest ``session_date`` anywhere in the panel.
    data_end: date


def admit_biased_panel(panel: MarketPanel, market_db: MarketPanelReader) -> BiasedScope:
    """The panel is back-filled history from before D0, or :class:`BiasedScopeViolation`.

    * every run's ``source`` (and every bar's) is ``backfill_non_pit``;
    * every ``session_date`` is strictly before D0, D0 being read from the
      market DB through the read-only reader (a missing file raises, since
      "no D0" would lift the limit).
    """
    frames = panel.frames
    if frames.runs.empty:
        raise BiasedScopeViolation("the panel has no runs: nothing shows it is back-filled")
    sources = set(_texts(frames.runs["source"])) | set(_texts(frames.bars["source"]))
    foreign = sorted(sources - {BACKFILL_SOURCE})
    if foreign:
        raise BiasedScopeViolation(
            f"the biased study reads {BACKFILL_SOURCE} runs only; found sources {foreign}"
        )
    sessions = [
        day for name in _DATED_FRAMES for day in getattr(frames, name)["session_date"].dropna()
    ]
    if not sessions:
        raise BiasedScopeViolation("the panel has no dated rows")
    data_end = max(pd.Timestamp(day).date() for day in sessions)
    d0 = market_db.first_all_kinds_ok_session()
    if d0 is not None and data_end >= d0:
        raise BiasedScopeViolation(
            f"the panel reaches {data_end.isoformat()}, on or after D0 {d0.isoformat()}; "
            "the biased study and its sensitivity variants stay before D0 (ADR-0012 C-49)"
        )
    return BiasedScope(d0=d0, data_end=data_end)


def _texts(column: pd.Series) -> list[str]:
    return [str(value) for value in column.to_numpy(dtype=object)]


def require_before_d0(d0: date | None, data_end: date) -> None:
    """The write-side repeat of the D0 check, on what a report says about itself."""
    if d0 is not None and data_end >= d0:
        raise BiasedScopeViolation(
            f"research data reaching {data_end.isoformat()} is not before D0 {d0.isoformat()}"
        )


def backfill_frames(
    bars: pd.DataFrame,
    *,
    listing: Sequence[str],
    classification: Mapping[str, tuple[str, str]],
    fetched_at: datetime,
) -> PanelFrames:
    """Panel frames for a hindsight study: every session gets *today's* universe.

    ``bars`` has ``symbol, session_date, open, high, low, close, shares,
    traded_value`` (``change`` unknown). Every row is recorded at
    ``fetched_at`` -- the real time it was obtained -- so a point-in-time view
    of any earlier session sees nothing.
    """
    if fetched_at.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware")
    recorded = pd.Timestamp(fetched_at).tz_convert("UTC")
    sessions = sorted(set(pd.to_datetime(bars["session_date"]).dt.date))
    runs: list[dict[str, object]] = []
    listing_parts: list[pd.DataFrame] = []
    class_parts: list[pd.DataFrame] = []
    bar_frame = bars.assign(
        session_date=pd.to_datetime(bars["session_date"]).dt.date,
        recorded_at=recorded,
        source=BACKFILL_SOURCE,
        change=math.nan,
    )
    run_of_session: dict[date, str] = {}
    listed = sorted(listing)
    classified = sorted(symbol for symbol in listed if symbol in classification)
    for index, session in enumerate(sessions):
        # ``dividend_announce`` runs are empty: back-filled history has no
        # ex-dividend record, so no lookback window is excluded and no label is
        # restored -- the "unrestored dividends" bias the label discloses.
        for kind in ("bars", "listing", "classification", "dividend_announce"):
            run_id = f"bf-{kind}-{index:06d}"
            runs.append(
                {
                    "run_id": run_id,
                    "kind": kind,
                    "session_date": session,
                    "recorded_at": recorded,
                    "source": BACKFILL_SOURCE,
                    "status": "ok",
                    "row_count": None,
                    "expected_count": None,
                }
            )
            if kind == "bars":
                run_of_session[session] = run_id
        listing_parts.append(
            pd.DataFrame(
                {
                    "run_id": f"bf-listing-{index:06d}",
                    "session_date": [session] * len(listed),
                    "recorded_at": recorded,
                    "symbol": listed,
                    "security_type": "common_stock",
                }
            )
        )
        class_parts.append(
            pd.DataFrame(
                {
                    "run_id": f"bf-classification-{index:06d}",
                    "session_date": [session] * len(classified),
                    "recorded_at": recorded,
                    "symbol": classified,
                    "sector_code": [classification[s][0] for s in classified],
                    "sector_name": [classification[s][1] for s in classified],
                }
            )
        )
    bar_frame["run_id"] = [run_of_session[day] for day in bar_frame["session_date"]]
    return PanelFrames(
        bars=bar_frame.loc[:, list(BARS_COLUMNS)].reset_index(drop=True),
        listing=pd.concat(listing_parts, ignore_index=True).loc[:, list(LISTING_COLUMNS)]
        if listing_parts
        else pd.DataFrame(columns=list(LISTING_COLUMNS)),
        classification=pd.concat(class_parts, ignore_index=True).loc[
            :, list(CLASSIFICATION_COLUMNS)
        ]
        if class_parts
        else pd.DataFrame(columns=list(CLASSIFICATION_COLUMNS)),
        ex_dividend=pd.DataFrame(columns=list(EX_DIVIDEND_COLUMNS)),
        runs=pd.DataFrame(runs, columns=list(RUNS_COLUMNS)),
    )


@dataclass(frozen=True)
class BiasedSegment:
    segment: Segment
    summary: RateSummary
    #: Strategy-layer metrics of the rank-1 basket over the segment's sessions.
    metrics: PerformanceMetrics | None
    #: Equal-weight benchmark path over the same sessions (gross; the comparator).
    benchmark_metrics: PerformanceMetrics | None
    sample_start: date | None
    sample_end: date | None


@dataclass(frozen=True)
class BiasedStudyReport:
    """A labelled, hindsight-only study. Never an input to any gate."""

    study_id: str
    bias_label: str
    bias_directions: Mapping[str, str]
    method_version: str
    regime: Literal["hindsight"]
    data_regime: Literal["backfill_non_pit"]
    segments: tuple[BiasedSegment, ...]
    statistics: SectorStatistics
    #: Walk-forward folds as ``(train_start, train_stop, test_start, test_stop)`` session dates.
    folds: tuple[tuple[date, date, date, date], ...]
    #: D0 when the study ran (``None``: none yet) and the panel's last session (C-49).
    d0: date | None
    data_end: date

    def segment(self, name: Segment) -> BiasedSegment:
        for item in self.segments:
            if item.segment == name:
                return item
        raise KeyError(name)


def _metrics_between(
    run: EngineRun, first: date, last: date
) -> tuple[PerformanceMetrics | None, PerformanceMetrics | None]:
    result = run.basket_result.run
    dates = result.dates
    start = next((i for i, day in enumerate(dates) if day >= first.isoformat()), None)
    stop = next((i for i, day in enumerate(dates) if day > last.isoformat()), len(dates))
    if start is None or stop - start < 2:
        return None, None
    report = build_segment_report(result, label="biased", start=start, stop=stop)
    return report.strategy, report.buy_and_hold


def run_biased_study(
    panel: MarketPanel,
    definition: SectorMomentumDefinition,
    *,
    market_db: MarketPanelReader,
    cost_model: CostModel,
    start: date,
    seed: int,
    calendar: Sequence[date] | None = None,
    train_sessions: int = TRAIN_SESSIONS,
    test_sessions: int = TEST_SESSIONS,
) -> BiasedStudyReport:
    """The judged pipeline on hindsight views, split in-sample / out-of-sample.

    ``m`` is 1: this data precedes D0 and never overlaps the judged data, so it
    does not count towards the judged m (methodology §3.2) -- but a version
    proposed *after* reading this report does (ADR-0012 D-14).

    ``market_db`` is the read-only market DB D0 is read from; the panel must
    pass :func:`admit_biased_panel` first (C-49).
    """
    scope = admit_biased_panel(panel, market_db)
    return study_on_hindsight(
        panel,
        definition,
        scope=scope,
        cost_model=cost_model,
        start=start,
        seed=seed,
        calendar=calendar,
        train_sessions=train_sessions,
        test_sessions=test_sessions,
    )


def study_on_hindsight(
    panel: MarketPanel,
    definition: SectorEvalDefinition,
    *,
    scope: BiasedScope,
    cost_model: CostModel,
    start: date,
    seed: int,
    calendar: Sequence[date] | None,
    train_sessions: int,
    test_sessions: int,
) -> BiasedStudyReport:
    """One study on an admitted panel (shared by :func:`run_biased_study` and the sensitivity).

    Raises :class:`BiasedScopeViolation` when the engine did not read hindsight
    views -- the only views this package may study (C-49).
    """
    run = evaluate_views(
        lambda t: hindsight_view(panel, t),
        panel,
        definition,
        cost_model=cost_model,
        start=start,
        m=1,
        seed=seed,
        calendar=calendar,
    )
    if run.regime != "hindsight":
        raise BiasedScopeViolation(
            f"the biased study read {run.regime!r} views; it reads hindsight views only"
        )
    main: tuple[Week, ...] = run.weeks[0] if run.weeks else ()
    sessions = [day for day in run.calendar if day >= start]
    folds = walk_forward_splits(
        len(sessions), train_size=train_sessions, test_size=test_sessions, step=test_sessions
    )
    fold_dates = tuple(
        (
            sessions[fold.train_start],
            sessions[fold.train_stop - 1],
            sessions[fold.test_start],
            sessions[fold.test_stop - 1],
        )
        for fold in folds
    )
    if folds:
        # Session geometry decides membership; a week belongs where it is decided.
        is_first, is_last = sessions[folds[0].train_start], sessions[folds[0].train_stop - 1]
        oos_first, oos_last = sessions[folds[0].test_start], sessions[folds[-1].test_stop - 1]
        in_sample = [w for w in main if is_first <= w.decision_date <= is_last]
        out_of_sample = [w for w in main if oos_first <= w.decision_date <= oos_last]
    else:
        # Too short for one fold: everything is reported as in-sample, nothing as OOS.
        in_sample, out_of_sample = list(main), []

    def segment(name: Segment, weeks: Sequence[Week]) -> BiasedSegment:
        valid = [week for week in weeks if week.valid]
        first = valid[0].decision_date if valid else None
        last = valid[-1].window.exit_date if valid else None
        metrics = benchmark = None
        if first is not None and last is not None:
            metrics, benchmark = _metrics_between(run, first, last)
        return BiasedSegment(
            segment=name,
            summary=summarise(weeks, definition),
            metrics=metrics,
            benchmark_metrics=benchmark,
            sample_start=first,
            sample_end=last,
        )

    return BiasedStudyReport(
        study_id=f"biased-{uuid.uuid4().hex[:12]}",
        bias_label=BIAS_LABEL,
        bias_directions=BIAS_DIRECTIONS,
        method_version=definition.method_version,
        regime="hindsight",
        data_regime="backfill_non_pit",
        segments=(
            segment("in_sample", in_sample),
            segment("out_of_sample", out_of_sample),
            segment("full", main),
        ),
        statistics=run.statistics,
        folds=fold_dates,
        d0=scope.d0,
        data_end=scope.data_end,
    )


def jsonable(value: object) -> object:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    if isinstance(value, Mapping | MappingProxyType):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, date):
        return value.isoformat()
    return value


def save_study(report: BiasedStudyReport, store: ResearchStore) -> str:
    """Write every segment of ``report`` to the research DB (and nowhere else)."""
    if report.data_regime != DATA_REGIME or report.bias_label != BIAS_LABEL:
        raise ValueError("research rows must be labelled backfill_non_pit with the bias label")
    if report.regime != "hindsight":
        raise BiasedScopeViolation("research rows come from hindsight views only")
    require_before_d0(report.d0, report.data_end)
    created = datetime.now(UTC)
    for item in report.segments:
        store.save_study_segment(
            study_id=report.study_id,
            segment=item.segment,
            method_version=report.method_version,
            created_at=created,
            sample_start=item.sample_start,
            sample_end=item.sample_end,
            sample_count=item.summary.sample_count,
            beat_count_net=item.summary.beat_count_net,
            beat_count_gross=item.summary.beat_count_gross,
            base_rate_net=item.summary.q_net,
            base_rate_gross=item.summary.q_gross,
            report={
                "segment": jsonable(item),
                "folds": jsonable(report.folds),
                "seeds": jsonable(report.statistics.seeds),
                "delta_real": report.statistics.delta_real,
                "delta_shuffle": report.statistics.delta_shuffle,
            },
        )
    return report.study_id
