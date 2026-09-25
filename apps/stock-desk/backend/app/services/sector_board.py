"""Sector card orchestration and its two CLIs (ADR-0012 D-1, D-5, D-8, D-12, C-31, C-36).

``refresh`` is the scheduler's ``sector_board_refresh`` job:

1. **D0** -- once the four snapshot kinds have first been ``ok`` on the same
   session, write it to ``sector_method_registry.accumulation_start`` (D-12;
   once, never changed).
2. **Board** -- for the latest session with an ``ok`` bars run: read the market
   DB, build ``MarketPanel.as_of(t)``, run the sector core -- the very function
   objects :func:`calculation_set` and :func:`rank_sectors` the evaluator calls
   (T-15) -- and write ``sector_board`` / ``_members`` / ``_excluded`` to the
   main DB. A board is written only when it differs from the last one stored
   for that session, so re-running after every capture (17:30 / 19:30 / 21:30)
   leaves the session's final board equal to what ``as_of(t)`` shows at its
   cutoff -- the board T9 replays.
3. **Evaluation** -- whenever a new non-overlapping H-session sample has
   completed since D0, run :func:`app.backtest.sector_eval.evaluate` on the
   forward point-in-time data, with the stored boards projected to
   :class:`BoardFingerprint` for T9 (no boards -> T9 fails closed, NE-7), the
   judge-time attestation check of C-36, and append one ``sector_rank_stats``
   row. A ``BiasedDataRejected`` aborts the judgement and writes nothing
   (T-22). An evaluation failure never touches the board (D-5).

This module decides nothing about ``gate_status`` (C-20): it writes the
evaluator's candidate and the provenance the read-time gate needs.

CLI (C-31; the operator and document checks are a speed bump, not an
enforcement boundary -- ADR-0007; the rule's force is norm and review)::

    python -m app.services.sector_board approve --kind {first_transition_risk|quarterly_qa} \\
        --run-id RUN --operator {ceo|dev-lead} --reviewer NAME --review-doc PATH
    python -m app.services.sector_board register-version --operator {ceo|dev-lead} \\
        --review-doc PATH [--method-version VERSION] [--counts-toward-m]

``first_transition_risk`` is run by the CEO or dev-lead on risk-compliance-officer's
written APPROVE; ``quarterly_qa`` by dev-lead on qa-reviewer's written
confirmation. Read-only roles and every other agent never write approvals, and
nobody writes one without the written record.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import logging
import sqlite3
import sys
import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Final, get_args

import pandas as pd

from app.backtest import sector_eval
from app.backtest.costs import CostModel
from app.backtest.sector_eval import BoardFingerprint, BoardRow
from app.data.market_panel import MarketPanelStore
from app.data.panel import MarketPanel, PointInTimePanel
from app.sectors import coverage, index
from app.sectors.definition import SECTOR_MOMENTUM_V1, SectorMomentumDefinition
from app.sectors.gate import PitStatus, judged_window
from app.sectors.models import ApprovalKind, ApprovalOperator, ApprovalRecord
from app.sectors.ranking import SectorRanking, rank_sectors
from app.sectors.store import (
    BiasedDataRejected,
    BoardProvenance,
    SectorApprovalStore,
    SectorBoardStore,
    SectorMethodRegistry,
    SectorStatsRepository,
    StoredBoard,
    StoredConstituent,
    StoredExcludedSector,
    StoredRankedSector,
)
from app.sectors.universe import CalculationSet, calculation_set
from app.services import sector_attestation
from app.services.sector_attestation import BACKEND_ROOT, AttestationCheck, GitProbe
from app.services.sector_runtime import runtime_from_check

logger = logging.getLogger(__name__)

# T-15: boards are built with the very function objects ``calculation_set`` and
# ``rank_sectors`` imported above -- the ones the evaluator's replay calls
# (tests/test_sector_eval.py asserts the identity).

#: The repository root (review documents must live inside it, C-31).
REPO_ROOT: Final = BACKEND_ROOT.parents[2]
#: Calendar days of history loaded for one day's board: covers the 60-session
#: listing age, the 20-session liquidity window and the lookback with room to spare.
BOARD_HISTORY_CALENDAR_DAYS: Final = 200
#: The evaluator reads the whole stored history (warm-up included).
EVALUATION_HISTORY_START: Final = date(1900, 1, 1)
#: ``running_commit`` when git could not say (the row is NE-7 anyway).
UNKNOWN_COMMIT: Final = "unknown"

#: Method versions this build can register (only frozen definitions belong here).
KNOWN_DEFINITIONS: Final[Mapping[str, SectorMomentumDefinition]] = {
    SECTOR_MOMENTUM_V1.method_version: SECTOR_MOMENTUM_V1,
}

#: Symbol -> display name for the listed constituents (display only).
NameLookup = Callable[[Collection[str]], Mapping[str, str]]
#: ``(window start, t) -> TAIEX close-to-close return`` for the 「詳細」 reference (D-9).
TaiexReturn = Callable[[date, date], float | None]


def _no_names(symbols: Collection[str]) -> Mapping[str, str]:
    return {}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class MarketRunIdVerifier:
    """``RunIdVerifier`` over :meth:`MarketPanelStore.existing_run_ids` (D-14, C-27).

    ``app.sectors`` may not import the market-DB store (C-1), so the main-DB
    repository reaches it through this adapter, injected here.
    """

    def __init__(self, store: MarketPanelStore) -> None:
        self._store = store

    def existing_run_ids(self, run_ids: Collection[str]) -> frozenset[str]:
        return frozenset(self._store.existing_run_ids(run_ids))


# ---------------------------------------------------------------------------
# One day's board
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BoardComputation:
    """Everything the core produced for ``t`` plus what the view says about its sources."""

    calc: CalculationSet
    ranking: SectorRanking
    turnover: Mapping[str, float | None]
    data_source: str
    bars_run_id: str | None
    bars_recorded_at: datetime | None
    ex_dividend_feed_covered: bool
    source_run_ids: tuple[str, ...]


def compute_board(
    view: PointInTimePanel, definition: SectorMomentumDefinition
) -> BoardComputation | None:
    """The board of ``view.decision_date``; ``None`` when that session has no visible bars."""
    t = view.decision_date
    data_source = view.bars_source_on(t) if t in view.sessions else None
    if data_source is None:
        return None
    calc = calculation_set(view, definition)
    ranking = rank_sectors(calc, definition)
    turnover = {
        row.sector_code: index.turnover_value_ratio_5_20(view, row.members)
        for row in ranking.ranked
    }
    runs = view.visible_runs()
    ok = runs.loc[runs["status"] == "ok"]
    bars_today = ok.loc[
        (ok["kind"] == "bars") & (ok["session_date"] == t) & (ok["source"] == data_source)
    ].sort_values(["recorded_at", "run_id"], kind="mergesort")
    bars_run_id: str | None = None
    bars_recorded_at: datetime | None = None
    if not bars_today.empty:
        last = bars_today.iloc[-1]
        bars_run_id = str(last["run_id"])
        bars_recorded_at = pd.Timestamp(last["recorded_at"]).to_pydatetime()
    # Provenance: every ok run inside the liquidity window, plus the snapshots in force.
    liquidity = index.trailing_window(view, definition.universe.liquidity_window_sessions - 1)
    since = liquidity[0] if liquidity else t
    used = set(ok.loc[ok["session_date"] >= since, "run_id"].astype(str))
    for snapshot in (calc.listing, calc.classification):
        if snapshot is not None:
            used.add(snapshot.run_id)
    return BoardComputation(
        calc=calc,
        ranking=ranking,
        turnover=turnover,
        data_source=data_source,
        bars_run_id=bars_run_id,
        bars_recorded_at=bars_recorded_at,
        ex_dividend_feed_covered=coverage.ex_dividend_feed_covered(view, definition),
        source_run_ids=tuple(sorted(used)),
    )


def stored_board_of(
    computation: BoardComputation,
    provenance: BoardProvenance,
    definition: SectorMomentumDefinition,
    names: Mapping[str, str],
) -> StoredBoard:
    """What :meth:`SectorBoardStore.save_board` will store, as the store reads it back."""
    calc, ranking = computation.calc, computation.ranking
    market = calc.market
    return StoredBoard(
        board_id=provenance.board_id,
        market=provenance.market,
        method_version=definition.method_version,
        lookback_days=definition.lookback_days,
        holding_days=definition.holding_days,
        data_as_of=calc.decision_date,
        window_start=calc.window[0] if calc.window else None,
        data_source=provenance.data_source,
        bars_run_id=provenance.bars_run_id,
        bars_recorded_at=(
            provenance.bars_recorded_at.isoformat() if provenance.bars_recorded_at else None
        ),
        computed_at=provenance.computed_at.isoformat(),
        benchmark_return_L=ranking.benchmark_return,
        reference_taiex_return_L=provenance.reference_taiex_return_L,
        market_expected_count=len(market.expected),
        market_missing_count=len(market.missing),
        market_ex_date_excluded_count=len(market.ex_date_excluded),
        market_corporate_action_excluded_count=len(market.corporate_action_excluded),
        ex_dividend_feed_covered=provenance.ex_dividend_feed_covered,
        constituent_invariant_violated=bool(ranking.invariant_violations),
        source_run_ids=tuple(sorted(provenance.source_run_ids)),
        ranked=tuple(
            StoredRankedSector(
                rank=row.rank,
                sector_code=row.sector_code,
                sector_name=row.sector_name,
                sector_return_L=row.sector_return,
                rel_return_L=row.rel_return,
                up_count=row.up_count,
                coverage=row.coverage,
                turnover_value_ratio_5_20=computation.turnover.get(row.sector_code),
                top_contributor_share=row.top_contributor_share,
                single_stock_dominated=row.single_stock_dominated,
                member_symbols=tuple(sorted(row.members)),
                constituents=tuple(
                    StoredConstituent(
                        symbol=item.symbol,
                        name=names.get(item.symbol, item.symbol),
                        return_L=item.return_L,
                    )
                    for item in row.constituents
                ),
            )
            for row in ranking.ranked
        ),
        excluded=tuple(
            StoredExcludedSector(
                sector_code=row.sector_code,
                sector_name=row.sector_name,
                reason_code=row.reason_code,
                coverage=row.coverage,
                internal_reason=row.internal_reason,
            )
            for row in ranking.excluded
        ),
    )


def same_board(left: StoredBoard, right: StoredBoard) -> bool:
    """Equal in every column the card or T9 reads (ids, clocks and provenance aside)."""

    def core(board: StoredBoard) -> StoredBoard:
        return dataclasses.replace(
            board, board_id="", computed_at="", bars_recorded_at=None, source_run_ids=()
        )

    return core(left) == core(right)


def board_fingerprint(board: StoredBoard) -> BoardFingerprint:
    """A stored board as the evaluator's T9 compares it (ADR-0012 D-8, wave-2 hand-off)."""
    return BoardFingerprint(
        decision_date=board.data_as_of,
        method_version=board.method_version,
        rows=tuple(
            BoardRow(
                rank=row.rank,
                sector_code=row.sector_code,
                sector_return=row.sector_return_L,
                up_count=row.up_count,
                constituent_count=row.constituent_count,
                constituent_symbols=tuple(item.symbol for item in row.constituents),
                missing_count=row.coverage.missing_count,
                ex_date_excluded_count=row.coverage.ex_date_excluded_count,
                corporate_action_excluded_count=row.coverage.corporate_action_excluded_count,
            )
            for row in board.ranked
        ),
    )


# ---------------------------------------------------------------------------
# The refresh job
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RefreshResult:
    session: date | None
    accumulation_start: date | None
    #: The board written this run; ``None`` when unchanged, impossible or failed.
    board_id: str | None
    #: The ``sector_rank_stats`` row written this run, if any.
    stats_run_id: str | None
    notes: tuple[str, ...] = ()


@dataclass
class SectorBoardService:
    """``sector_board_refresh`` against one market DB and one main DB."""

    market_store: MarketPanelStore
    main_db: str | Path | None = None
    names: NameLookup = _no_names
    reference_taiex: TaiexReturn | None = None
    attestation: Callable[[], AttestationCheck] = sector_attestation.verify
    cost_model: CostModel = field(default_factory=CostModel)
    definition: SectorMomentumDefinition = SECTOR_MOMENTUM_V1
    market: str = "TW"
    clock: Callable[[], datetime] = _utc_now

    def __post_init__(self) -> None:
        self.boards = SectorBoardStore(self.main_db)
        self.stats = SectorStatsRepository(MarketRunIdVerifier(self.market_store), self.main_db)
        self.registry = SectorMethodRegistry(self.main_db)
        self._lock = threading.RLock()
        #: The last sample exit an evaluation was attempted for (no row may result).
        self._attempted_exit: date | None = None

    def refresh(self) -> RefreshResult:
        """One run of the job; serialised, since captures may chain into it."""
        with self._lock:
            return self._refresh()

    def _refresh(self) -> RefreshResult:
        notes: list[str] = []
        d0 = self._accumulation_start(notes)
        t = self.market_store.last_ok_session("bars")
        if t is None:
            return RefreshResult(None, d0, None, None, ("no_ok_bars_run",))
        board_id: str | None = None
        try:
            board_id = self.refresh_board(t, notes)
        except Exception:
            logger.exception("sector board for %s failed; the evaluation still runs", t)
            notes.append("board_failed")
        stats_run_id: str | None = None
        try:
            stats_run_id = self._maybe_evaluate(t, d0, notes)
        except Exception:
            logger.exception("sector evaluation failed; the board is unaffected (D-5)")
            notes.append("evaluation_failed")
        return RefreshResult(t, d0, board_id, stats_run_id, tuple(notes))

    def _accumulation_start(self, notes: list[str]) -> date | None:
        version = self.definition.method_version
        row = self.registry.get(version)
        if row is None:
            notes.append("method_version_not_registered")
            logger.warning("%s is not registered; run register-version first", version)
            return None
        if row.accumulation_start is not None:
            return row.accumulation_start
        d0 = self.market_store.first_all_kinds_ok_session()
        if d0 is not None:
            self.registry.record_accumulation_start(version, d0)
            notes.append("accumulation_start_recorded")
        return d0

    def refresh_board(self, t: date, notes: list[str] | None = None) -> str | None:
        """Compute session ``t``'s board and store it unless the stored one is identical.

        Returns the new ``board_id`` (``None`` when unchanged or no bars are
        visible on ``t``). Past sessions are safe to (re)compute: nothing can
        become visible to ``as_of(t)`` after ``cutoff(t)``.
        """
        with self._lock:
            return self._refresh_board(t, notes if notes is not None else [])

    def _refresh_board(self, t: date, notes: list[str]) -> str | None:
        frames = self.market_store.load_panel_frames(
            t - timedelta(days=BOARD_HISTORY_CALENDAR_DAYS), t
        )
        computation = compute_board(MarketPanel(frames).as_of(t), self.definition)
        if computation is None:
            notes.append("no_visible_bars")
            return None
        window = computation.calc.window
        taiex = (
            self.reference_taiex(window[0], t)
            if self.reference_taiex is not None and window
            else None
        )
        now = self.clock()
        provenance = BoardProvenance(
            board_id=f"{self.market}-{t.isoformat()}-{now.strftime('%Y%m%dT%H%M%S%f')}",
            market=self.market,
            data_source=computation.data_source,
            bars_run_id=computation.bars_run_id,
            bars_recorded_at=computation.bars_recorded_at,
            computed_at=now,
            source_run_ids=computation.source_run_ids,
            ex_dividend_feed_covered=computation.ex_dividend_feed_covered,
            reference_taiex_return_L=taiex,
        )
        listed = {item.symbol for row in computation.ranking.ranked for item in row.constituents}
        names = dict(self.names(listed)) if listed else {}
        fresh = stored_board_of(computation, provenance, self.definition, names)
        latest = self.boards.latest_board(self.market)
        if latest is not None and latest.data_as_of == t and same_board(latest, fresh):
            notes.append("board_unchanged")
            return None
        if computation.ranking.invariant_violations:
            logger.error(
                "constituent invariant violated (C-35) for %s: %s",
                t,
                ",".join(computation.ranking.invariant_violations),
            )
        self.boards.save_board(
            definition=self.definition,
            calc=computation.calc,
            ranking=computation.ranking,
            provenance=provenance,
            turnover=computation.turnover,
            names=names,
        )
        return provenance.board_id

    def _maybe_evaluate(self, t: date, d0: date | None, notes: list[str]) -> str | None:
        version = self.definition.method_version
        registered = self.registry.get(version)
        if d0 is None or registered is None:
            return None
        summary = self.market_store.run_status_summary(d0, t)
        days = sorted(summary["bars"].ok_sessions)
        window = judged_window(days, d0, self.definition.holding_days)
        if not window.decision_dates:
            return None
        last_decision = window.decision_dates[-1]
        latest_exit = days[days.index(last_decision) + self.definition.holding_days]
        history = self.stats.load(version)
        if history and history[-1].recompute_session >= latest_exit:
            return None
        if self._attempted_exit == latest_exit:
            return None
        self._attempted_exit = latest_exit

        panel = MarketPanel(self.market_store.load_panel_frames(EVALUATION_HISTORY_START, t))
        boards = {
            board.data_as_of: board_fingerprint(board)
            for board in self.boards.latest_boards(self.market, version)
        }
        check = self.attestation()
        runtime = runtime_from_check(check, cost_model=self.cost_model)
        m = self.registry.m() + (0 if registered.counts_toward_m else 1)
        evaluation = sector_eval.evaluate(
            panel,
            self.definition,
            cost_model=self.cost_model,
            start=d0,
            m=m,
            seed=int(latest_exit.strftime("%Y%m%d")),
            pit_status=PitStatus(
                accumulation_start=d0,
                ok_sessions={
                    "listing": summary["listing"].ok_sessions,
                    "classification": summary["classification"].ok_sessions,
                    "dividend_announce": summary["dividend_announce"].ok_sessions,
                },
            ),
            de5_verified_on=runtime.de5_verified_on,
            boards=boards,
        )
        now = self.clock()
        record = sector_eval.to_stats_record(
            evaluation,
            self.definition,
            run_id=f"{version}:{latest_exit.isoformat()}:{now.strftime('%Y%m%dT%H%M%S%f')}",
            computed_at=now,
            recompute_session=latest_exit,
            running_commit=check.running_commit or UNKNOWN_COMMIT,
            ci_attestation_ok=check.ok,
        )
        if not check.ok:
            notes.append("attestation:" + ",".join(check.problems))
        if record is None:
            notes.append("no_valid_sample")
            return None
        try:
            self.stats.save(record)
        except BiasedDataRejected:
            logger.exception("statistics refused (D-14); this judgement writes nothing")
            notes.append("biased_data_rejected")
            return None
        if registered.first_forward_eval_at is None:
            self.registry.record_first_forward_eval(version, now)
        return record.run_id


# ---------------------------------------------------------------------------
# CLI: approvals and version registration (C-31)
# ---------------------------------------------------------------------------

OPERATORS: Final[tuple[ApprovalOperator, ...]] = get_args(ApprovalOperator)
APPROVAL_KINDS: Final[tuple[ApprovalKind, ...]] = get_args(ApprovalKind)


class ApprovalRefused(Exception):
    """The CLI refuses to write: a check of C-31 / T-19 did not pass."""


def git_blob_hash(content: bytes) -> str:
    """``git hash-object`` of ``content`` (SHA-1 over ``blob <len>\\0`` + bytes)."""
    return hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False).hexdigest()


@dataclass(frozen=True)
class ReviewDocument:
    #: Repository-relative POSIX path.
    path: str
    blob_hash: str
    text: str


def review_document(
    path: str | Path, repo_root: Path, *, must_contain: Sequence[str]
) -> ReviewDocument:
    """The written record behind an approval: inside the repo, naming what it approves."""
    candidate = Path(path)
    resolved = (candidate if candidate.is_absolute() else Path.cwd() / candidate).resolve()
    root = repo_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ApprovalRefused(f"審查文件不在 repo 內：{resolved}") from exc
    if not resolved.is_file():
        raise ApprovalRefused(f"審查文件不存在：{relative.as_posix()}")
    content = resolved.read_bytes()
    text = content.decode("utf-8", errors="replace")
    for needle in must_contain:
        if needle not in text:
            raise ApprovalRefused(f"審查文件未提及 {needle}：{relative.as_posix()}")
    return ReviewDocument(path=relative.as_posix(), blob_hash=git_blob_hash(content), text=text)


def _operator(value: str) -> ApprovalOperator:
    for operator in OPERATORS:
        if value == operator:
            return operator
    raise ApprovalRefused(f"--operator 只能是 {' / '.join(OPERATORS)}：{value!r}")


def _kind(value: str) -> ApprovalKind:
    for kind in APPROVAL_KINDS:
        if value == kind:
            return kind
    raise ApprovalRefused(f"--kind 只能是 {' / '.join(APPROVAL_KINDS)}：{value!r}")


def approve(
    *,
    kind: str,
    run_id: str,
    operator: str,
    reviewer: str,
    review_doc: str | Path,
    stats: SectorStatsRepository,
    approvals: SectorApprovalStore,
    repo_root: Path = REPO_ROOT,
    clock: Callable[[], datetime] = _utc_now,
) -> ApprovalRecord:
    """Write one ``sector_gate_approvals`` row after every C-31 check (T-19)."""
    checked_kind = _kind(kind)
    checked_operator = _operator(operator)
    if checked_kind == "quarterly_qa" and checked_operator != "dev-lead":
        raise ApprovalRefused("quarterly_qa 只能由 dev-lead 依 qa-reviewer 書面確認執行")
    if not reviewer.strip():
        raise ApprovalRefused("--reviewer 必填")
    if not run_id.strip():
        raise ApprovalRefused("--run-id 必填")
    record = stats.find(run_id)
    if record is None:
        raise ApprovalRefused(f"找不到統計列 run_id={run_id}")
    document = review_document(review_doc, repo_root, must_contain=(run_id, record.method_version))
    approval = ApprovalRecord(
        kind=checked_kind,
        run_id=run_id,
        method_version=record.method_version,
        operator=checked_operator,
        reviewer=reviewer.strip(),
        review_doc_path=document.path,
        review_doc_blob_hash=document.blob_hash,
        approved_at=clock(),
    )
    approvals.add(approval)
    return approval


def register_version(
    *,
    method_version: str,
    operator: str,
    review_doc: str | Path,
    registry: SectorMethodRegistry,
    counts_toward_m: bool = False,
    git: GitProbe | None = None,
    repo_root: Path = REPO_ROOT,
    clock: Callable[[], datetime] = _utc_now,
) -> str:
    """Register a frozen version at the current, clean commit; returns ``frozen_commit``.

    The written record must name the version (methodology §11.2: freeze -> m + 1
    -> risk review -> tell the CEO). The registry has no column for it (D-6), so
    the document is checked, not stored; its path and blob hash are printed.
    """
    _operator(operator)
    definition = KNOWN_DEFINITIONS.get(method_version)
    if definition is None:
        raise ApprovalRefused(f"未知的 method_version：{method_version}")
    review_document(review_doc, repo_root, must_contain=(method_version,))
    probe = git if git is not None else sector_attestation.SubprocessGit(repo_root)
    head, clean = probe.head(), probe.is_clean()
    if head is None or clean is None:
        raise ApprovalRefused("讀不到 git，無法記錄凍結 commit")
    if not clean:
        raise ApprovalRefused("工作樹不乾淨：凍結的定義必須已 commit")
    try:
        registry.register(
            definition,
            frozen_commit=head,
            registered_at=clock(),
            counts_toward_m=counts_toward_m,
        )
    except sqlite3.IntegrityError as exc:
        raise ApprovalRefused(f"{method_version} 已登記過") from exc
    return head


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.services.sector_board")
    commands = parser.add_subparsers(dest="command", required=True)
    approve_cmd = commands.add_parser("approve", help="寫入一筆核准紀錄（C-31）")
    approve_cmd.add_argument("--kind", required=True, choices=APPROVAL_KINDS)
    approve_cmd.add_argument("--run-id", required=True)
    approve_cmd.add_argument("--operator", required=True, choices=OPERATORS)
    approve_cmd.add_argument("--reviewer", required=True)
    approve_cmd.add_argument("--review-doc", required=True)
    register_cmd = commands.add_parser("register-version", help="登記凍結的計算版本（D-6）")
    register_cmd.add_argument(
        "--method-version", default=SECTOR_MOMENTUM_V1.method_version, choices=KNOWN_DEFINITIONS
    )
    register_cmd.add_argument("--operator", required=True, choices=OPERATORS)
    register_cmd.add_argument("--review-doc", required=True)
    register_cmd.add_argument("--counts-toward-m", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(
        "提醒：operator 與文件檢查只是減速帶；依 C-31，只有 CEO／dev-lead 可依書面憑據執行，"
        "唯讀職能與其他 agent 不得代寫。",
        file=sys.stderr,
    )
    try:
        if args.command == "approve":
            stats = SectorStatsRepository(MarketRunIdVerifier(MarketPanelStore()))
            approval = approve(
                kind=args.kind,
                run_id=args.run_id,
                operator=args.operator,
                reviewer=args.reviewer,
                review_doc=args.review_doc,
                stats=stats,
                approvals=SectorApprovalStore(),
            )
            print(
                f"approved kind={approval.kind} run_id={approval.run_id} "
                f"method_version={approval.method_version} doc={approval.review_doc_path} "
                f"blob={approval.review_doc_blob_hash}"
            )
            return 0
        commit = register_version(
            method_version=args.method_version,
            operator=args.operator,
            review_doc=args.review_doc,
            registry=SectorMethodRegistry(),
            counts_toward_m=args.counts_toward_m,
        )
        print(f"registered {args.method_version} frozen_commit={commit}")
        return 0
    except ApprovalRefused as exc:
        print(f"拒絕：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
