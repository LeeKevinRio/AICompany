"""The sector board service: orchestration, T9 at run time, the NE-7 hand-off (ADR-0012 D-5, D-8).

Everything runs against a real market DB (``tests.sector_board_helpers.store_market``
writes a synthetic market through the store's own API and clock) and a real
main DB in a temp directory; nothing touches the network or git.

* D0 is recorded once; the latest session's board is written, and an
  unchanged recomputation writes nothing;
* **runtime T9** (the wave-2 hand-off): stored boards are projected to
  ``BoardFingerprint`` and handed to the evaluator; with them T9 passes, with
  a tampered board it fails, without any it fails closed (NE-7);
* the board read from a 200-day window equals the evaluator's full-history
  replay on every decision date (T-9 CI half through the services path);
* a ``BiasedDataRejected`` aborts the judgement and writes nothing (T-22);
* the judge-time attestation result lands on the row (C-36), ``m`` counts
  the version and ``first_forward_eval_at`` is stamped once (D-6);
* an evaluation failure never touches the board (D-5).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.backtest import sector_eval
from app.data.market_panel import MarketPanelStore
from app.data.panel import MarketPanel, source_fingerprint
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.definition import GateRules, SectorMomentumDefinition
from app.sectors.gate import judged_window
from app.sectors.store import (
    BoardProvenance,
    SectorBoardStore,
    SectorMethodRegistry,
    SectorStatsRepository,
)
from app.services import sector_board
from app.services.sector_attestation import AttestationCheck
from app.services.sector_board import (
    SectorBoardService,
    board_fingerprint,
    compute_board,
    same_board,
    stored_board_of,
)
from tests.published_helpers import published
from tests.sector_board_helpers import store_market
from tests.sector_eval_helpers import SyntheticMarket, synthetic_market

#: V1 with fewer T1 dates, only to keep CI time sane; every other value is V1's.
FAST = SectorMomentumDefinition(
    method_version=V1.method_version,
    lookback_days=V1.lookback_days,
    holding_days=V1.holding_days,
    gate=GateRules(lookahead_sample_dates=4),
)
NOW = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
GOOD = AttestationCheck(running_commit="c0ffee", ci_passed_commit="c0ffee", problems=())


@pytest.fixture(scope="module", autouse=True)
def _fast_is_published() -> Iterator[None]:
    """FAST is V1 with fewer T1 dates; the gated entries accept it only while published."""
    with published(FAST):
        yield


@dataclass
class World:
    market: SyntheticMarket
    store: MarketPanelStore
    calendar: tuple[date, ...]


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    market = synthetic_market(seed=21, warmup=62, forward=48, n_dividends=5)
    store = store_market(market, tmp_path_factory.mktemp("market") / "market.db")
    return World(market=market, store=store, calendar=market.calendar)


def _service(world: World, main_db: Path, **overrides: object) -> SectorBoardService:
    options: dict[str, object] = {
        "market_store": world.store,
        "main_db": main_db,
        "attestation": lambda: GOOD,
        "clock": lambda: NOW,
        "definition": FAST,
    }
    options.update(overrides)
    return SectorBoardService(**options)  # type: ignore[arg-type]


def _register(main_db: Path) -> SectorMethodRegistry:
    registry = SectorMethodRegistry(main_db)
    registry.register(FAST, frozen_commit="c0ffee", registered_at=NOW)
    return registry


def _decision_dates(world: World) -> tuple[date, ...]:
    return judged_window(world.calendar, world.market.d0, FAST.holding_days).decision_dates


def _selfcheck(repo: SectorStatsRepository, name: str) -> tuple[str, str | None]:
    row = repo.latest_history()[-1]
    check = next(item for item in row.selfchecks if item.check_name == name)
    return check.status, check.detail


# ---------------------------------------------------------------------------
# Adapter and board
# ---------------------------------------------------------------------------


def test_the_market_store_is_the_source_verifier(world: World) -> None:
    """Both C-50 capabilities, straight off the store the service injects."""
    frames = world.store.load_panel_frames(world.calendar[0], world.calendar[-1])
    sources = source_fingerprint(frames.runs)
    assert sources is not None
    assert world.store.source_fingerprint(sources.run_max, sources.session_end) == sources
    tally = world.store.source_tally(
        {sources.run_min, sources.run_max, 999_999_999}, sources.run_max, sources.session_end
    )
    assert tally.ok_endpoints == {sources.run_min, sources.run_max}
    assert (tally.run_count, tally.run_min, tally.run_max) == (
        sources.run_count,
        sources.run_min,
        sources.run_max,
    )


def test_a_stored_board_reads_back_exactly_as_computed(world: World, tmp_path: Path) -> None:
    """``stored_board_of`` mirrors ``save_board`` -- the unchanged-board check relies on it."""
    t = world.calendar[-3]
    view = MarketPanel(world.store.load_panel_frames(world.calendar[0], t)).as_of(t)
    computation = compute_board(view, FAST)
    assert computation is not None
    provenance = BoardProvenance(
        board_id="b1",
        market="TW",
        data_source=computation.data_source,
        bars_run_id=computation.bars_run_id,
        bars_recorded_at=computation.bars_recorded_at,
        computed_at=NOW,
        source_run_ids=computation.source_run_ids,
        ex_dividend_feed_covered=computation.ex_dividend_feed_covered,
        reference_taiex_return_L=0.0123,
    )
    names = {"0100": "甲公司"}
    store = SectorBoardStore(tmp_path / "main.db")
    store.save_board(
        definition=FAST,
        calc=computation.calc,
        ranking=computation.ranking,
        provenance=provenance,
        turnover=computation.turnover,
        names=names,
    )
    loaded = store.load_board("b1")
    assert loaded is not None
    assert loaded == stored_board_of(computation, provenance, FAST, names)
    assert same_board(loaded, dataclasses.replace(loaded, board_id="other", computed_at="x"))
    assert not same_board(loaded, dataclasses.replace(loaded, reference_taiex_return_L=None))


def test_refresh_records_d0_once_and_writes_only_changed_boards(
    world: World, tmp_path: Path
) -> None:
    registry = _register(tmp_path / "main.db")
    service = _service(world, tmp_path / "main.db")
    first = service.refresh()
    assert first.session == world.calendar[-1]
    assert first.accumulation_start == world.market.d0
    assert registry.get(FAST.method_version).accumulation_start == world.market.d0  # type: ignore[union-attr]
    assert first.board_id is not None
    again = service.refresh()
    assert again.board_id is None and "board_unchanged" in again.notes
    assert again.stats_run_id is None  # no new sample since the first evaluation
    board = service.boards.latest_board("TW")
    assert board is not None and board.data_as_of == world.calendar[-1]
    assert board.bars_run_id is not None and board.data_source == "twse_snapshot"
    # Every ranked sector lists three constituents; names fall back to the symbol.
    assert all(len(row.constituents) == 3 for row in board.ranked)
    assert all(item.name == item.symbol for row in board.ranked for item in row.constituents)


def test_an_unregistered_version_still_gets_its_board(world: World, tmp_path: Path) -> None:
    result = _service(world, tmp_path / "main.db").refresh()
    assert "method_version_not_registered" in result.notes
    assert result.board_id is not None and result.stats_run_id is None
    assert result.accumulation_start is None


# ---------------------------------------------------------------------------
# Runtime T9 through the services layer
# ---------------------------------------------------------------------------


@pytest.mark.sector_ne7
def test_windowed_boards_equal_the_full_history_replay(world: World, tmp_path: Path) -> None:
    """T-9 CI half via services: the stored board == ``sector_eval``'s replay, per date."""
    service = _service(world, tmp_path / "main.db")
    full = MarketPanel(world.store.load_panel_frames(date(1900, 1, 1), world.calendar[-1]))
    dates = _decision_dates(world)
    assert len(dates) >= 5
    for t in dates[::2]:
        service.refresh_board(t)
    stored = service.boards.latest_boards("TW", FAST.method_version)
    assert [board.data_as_of for board in stored] == list(dates[::2])
    for board in stored:
        replay = sector_eval.decide(full.as_of(board.data_as_of), FAST).ranking
        assert board_fingerprint(board) == sector_eval.fingerprint_ranking(replay)


def test_runtime_t9_passes_with_the_stored_boards(world: World, tmp_path: Path) -> None:
    _register(tmp_path / "main.db")
    service = _service(world, tmp_path / "main.db")
    for t in _decision_dates(world):
        service.refresh_board(t)
    result = service.refresh()
    assert result.stats_run_id is not None
    status, detail = _selfcheck(service.stats, sector_eval.T9)
    assert status == "pass", detail
    row = service.stats.latest_history()[-1]
    assert row.running_commit == "c0ffee"
    assert row.recompute_session == _latest_exit(world)
    # D-6: the first forward evaluation is stamped and the version counts toward m.
    registered = SectorMethodRegistry(tmp_path / "main.db").get(FAST.method_version)
    assert registered is not None and registered.first_forward_eval_at == NOW
    assert registered.counts_toward_m and row.m_at_evaluation == 1


def test_runtime_t9_fails_on_a_tampered_board(world: World, tmp_path: Path) -> None:
    _register(tmp_path / "main.db")
    service = _service(world, tmp_path / "main.db")
    dates = _decision_dates(world)
    for t in dates:
        service.refresh_board(t)
    target = dates[2]
    view = MarketPanel(world.store.load_panel_frames(world.calendar[0], target)).as_of(target)
    computation = compute_board(view, FAST)
    assert computation is not None and computation.ranking.ranked
    first = computation.ranking.ranked[0]
    tampered = dataclasses.replace(
        computation.ranking,
        ranked=(
            dataclasses.replace(first, sector_return=first.sector_return + 0.01),
            *computation.ranking.ranked[1:],
        ),
    )
    service.boards.save_board(
        definition=FAST,
        calc=computation.calc,
        ranking=tampered,
        provenance=BoardProvenance(
            board_id="tampered",
            market="TW",
            data_source=computation.data_source,
            bars_run_id=None,
            bars_recorded_at=None,
            computed_at=datetime(2030, 1, 1, tzinfo=UTC),
            source_run_ids=computation.source_run_ids,
            ex_dividend_feed_covered=computation.ex_dividend_feed_covered,
        ),
        turnover=computation.turnover,
        names={},
    )
    service.refresh()
    status, detail = _selfcheck(service.stats, sector_eval.T9)
    assert status == "fail"
    assert detail is not None and f"{target.isoformat()}:board_differs" in detail
    assert not service.stats.latest_history()[-1].selfcheck_passed


def test_runtime_t9_fails_closed_without_boards(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(tmp_path / "main.db")
    service = _service(world, tmp_path / "main.db")
    # The latest session's board is written by refresh; hide every stored board from T9.
    monkeypatch.setattr(service.boards, "latest_boards", lambda market, version: ())
    service.refresh()
    status, detail = _selfcheck(service.stats, sector_eval.T9)
    assert status == "fail" and detail is not None and "no_board_compared" in detail


def _latest_exit(world: World) -> date:
    dates = _decision_dates(world)
    return world.calendar[world.calendar.index(dates[-1]) + FAST.holding_days]


# ---------------------------------------------------------------------------
# NE-7 hand-off and fail-closed paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("check", "commit"),
    [
        (AttestationCheck("c0ffee", "c0ffee", ("dirty_worktree",)), "c0ffee"),
        (AttestationCheck(None, "c0ffee", ("git_unreadable",)), sector_board.UNKNOWN_COMMIT),
        (AttestationCheck("c0ffee", None, ("attestation_missing",)), "c0ffee"),
    ],
)
def test_a_failed_attestation_marks_the_row(
    world: World, tmp_path: Path, check: AttestationCheck, commit: str
) -> None:
    _register(tmp_path / "main.db")
    service = _service(world, tmp_path / "main.db", attestation=lambda: check)
    result = service.refresh()
    assert result.stats_run_id is not None
    assert any(note.startswith("attestation:") for note in result.notes)
    row = service.stats.latest_history()[-1]
    assert row.running_commit == commit and not row.selfcheck_passed


def test_biased_data_aborts_the_judgement(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _register(tmp_path / "main.db")
    monkeypatch.setattr(world.store, "source_fingerprint", lambda run_max, session_end: None)
    service = _service(world, tmp_path / "main.db")
    result = service.refresh()
    assert "biased_data_rejected" in result.notes and result.stats_run_id is None
    monkeypatch.undo()
    assert service.stats.latest_history() == ()
    assert registry.get(FAST.method_version).first_forward_eval_at is None  # type: ignore[union-attr]


def test_an_evaluation_failure_leaves_the_board(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register(tmp_path / "main.db")

    def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("evaluator bug")

    monkeypatch.setattr(sector_board.sector_eval, "evaluate", explode)
    result = _service(world, tmp_path / "main.db").refresh()
    assert "evaluation_failed" in result.notes
    assert result.board_id is not None and result.stats_run_id is None


def test_no_evaluation_before_a_sample_completes(world: World, tmp_path: Path) -> None:
    _register(tmp_path / "main.db")
    service = _service(world, tmp_path / "main.db")
    early = world.calendar[world.calendar.index(world.market.d0) + 3]

    class Frozen:
        """The market store as it stood on ``early`` (later sessions unseen)."""

        def __getattr__(self, name: str) -> object:
            return getattr(world.store, name)

        def last_ok_session(self, kind: str, *, before: date | None = None) -> date | None:
            return early

    service.market_store = Frozen()  # type: ignore[assignment]
    result = service.refresh()
    assert result.session == early and result.stats_run_id is None
