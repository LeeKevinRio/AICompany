"""The card's read does not grow with the market DB (ADR-0012 C-51; T-34).

Scale as the ADR states it: a market DB of **100,000** ``ok`` runs -- 1,100
symbols x 80 warm-up sessions, one run per symbol per day (88,000), plus the
four forward kinds on 3,000 sessions (12,000) -- and a main DB with **160**
statistics rows whose source sets reach into it (the latest two carry real
digests; the latest one is written through ``save()`` against the real store,
recomputing both). The main DB's board also carries a ``sector_board.
source_run_ids`` the size a warm-up-era board would have.

The runs are written straight into the schema ``MarketPanelStore`` creates, in
one ``executemany``: the scale is about run count only, and the card reads
no bar rows. Nothing here times anything (the P95 is measured by devops-sre
off CI).

* ``sector_rank_stats`` has no ``source_run_ids`` and every row's source
  columns fit in 256 bytes;
* ``GET /api/sectors/momentum``: at most 7 SQL statements, exactly one source
  check (one statement, one verifier call), none selecting ``source_run_ids``;
* the characters the request fetches from the main DB are the same with a
  1,000-run and a 100,000-run market DB, and far fewer than the board's
  ``source_run_ids`` alone.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.data import market_panel
from app.data import panel as panel_module
from app.data.market_panel import MarketPanelReader, MarketPanelStore
from app.data.panel import SourceFingerprint
from app.positions.store import PositionStore
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.models import ApprovalRecord
from app.sectors.store import (
    SectorApprovalStore,
    SectorCardReader,
    SectorMethodRegistry,
    SectorStatsRepository,
)
from app.services.sector_board import SectorBoardService
from tests.sector_board_helpers import card_client, stats_record, store_market, verified_runtime
from tests.sector_eval_helpers import synthetic_market
from tests.source_helpers import FakeSources, fingerprint

WARMUP_SYMBOLS = 1_100
WARMUP_SESSIONS = 80
FORWARD_SESSIONS = 3_000
FORWARD_KINDS = ("bars", "listing", "classification", "dividend_announce")
TOTAL_RUNS = WARMUP_SYMBOLS * WARMUP_SESSIONS + FORWARD_SESSIONS * len(FORWARD_KINDS)
SMALL_RUNS = 1_000
STATS_ROWS = 160
NOW = datetime(2032, 1, 5, 12, tzinfo=UTC)


def _weekdays(first: date, count: int) -> list[date]:
    days: list[date] = []
    cursor = first
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _build_market(path: Path, symbols: int, warm_sessions: int, forward: int) -> list[date]:
    """Warm-up runs (one per symbol per day, before D0), then the four forward kinds."""
    MarketPanelStore(path)  # the schema, triggers and all
    warm = _weekdays(date(2019, 9, 2), warm_sessions)
    days = _weekdays(warm[-1] + timedelta(days=1), forward)
    warm_recorded = datetime.combine(days[0], datetime.min.time(), tzinfo=UTC).isoformat()
    rows: list[tuple[object, ...]] = [
        ("bars", day.isoformat(), warm_recorded, "finmind_warmup", "ok", 1, None)
        for _ in range(symbols)
        for day in warm
    ]
    for day in days:
        recorded = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=10)
        rows += [
            (kind, day.isoformat(), recorded.isoformat(), "twse", "ok", 1000, 1000)
            for kind in FORWARD_KINDS
        ]
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO pit_snapshot_runs (kind, session_date, recorded_at, source, status, "
            "row_count, expected_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return days


@dataclass(frozen=True)
class Scale:
    big_market: Path
    small_market: Path
    main_db: Path
    positions: PositionStore
    board_source_run_ids_chars: int


def _stats_fingerprints(store: MarketPanelStore, days: list[date]) -> list[SourceFingerprint]:
    """160 rows over the forward sessions; the last one covers every run."""
    warm_runs = WARMUP_SYMBOLS * WARMUP_SESSIONS
    fingerprints: list[SourceFingerprint] = []
    for row in range(STATS_ROWS):
        index = (row + 1) * FORWARD_SESSIONS // STATS_ROWS - 1
        last_run = warm_runs + (index + 1) * len(FORWARD_KINDS)
        fingerprints.append(
            fingerprint(run_min=1, run_max=last_run, session_end=days[index], run_count=last_run)
        )
    # The two rows save() recomputes carry their real digests.
    for position in (-2, -1):
        real = store.source_fingerprint(
            fingerprints[position].run_max, fingerprints[position].session_end
        )
        assert real is not None and real.run_count == fingerprints[position].run_count
        fingerprints[position] = real
    return fingerprints


@pytest.fixture(scope="module")
def scale(tmp_path_factory: pytest.TempPathFactory) -> Scale:
    base = tmp_path_factory.mktemp("t34")
    big_market, small_market = base / "market-100k.db", base / "market-1k.db"
    days = _build_market(big_market, WARMUP_SYMBOLS, WARMUP_SESSIONS, FORWARD_SESSIONS)
    _build_market(small_market, 20, 30, (SMALL_RUNS - 20 * 30) // len(FORWARD_KINDS))
    for path, runs in ((big_market, TOTAL_RUNS), (small_market, SMALL_RUNS)):
        with closing(sqlite3.connect(path)) as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM pit_snapshot_runs WHERE status = 'ok'"
            ).fetchone() == (runs,)

    # The board: computed by the service from a small synthetic market.
    main_db = base / "main.db"
    board_market = synthetic_market(
        seed=3, sectors={f"{10 + i:02d}": 5 + i % 3 for i in range(20)}, warmup=62, forward=30
    )
    board_store = store_market(board_market, base / "board-market.db")
    registry = SectorMethodRegistry(main_db)
    registry.register(V1, frozen_commit="c0ffee", registered_at=NOW)
    SectorBoardService(market_store=board_store, main_db=main_db, clock=lambda: NOW).refresh_board(
        board_market.calendar[-1]
    )
    # A warm-up-era board lists every run of its liquidity window (C-51's reason).
    bloated = "[" + ",".join(f'"{n}"' for n in range(1, WARMUP_SYMBOLS * 20 + 1)) + "]"
    with closing(sqlite3.connect(main_db)) as conn, conn:
        conn.execute("UPDATE sector_board SET source_run_ids = ?", (bloated,))

    # 160 statistics rows over the 100,000-run market DB.
    store = MarketPanelStore(big_market)
    fingerprints = _stats_fingerprints(store, days)
    rows = [
        stats_record(
            f"stats-{n:03d}",
            fingerprints[n],
            computed_at=datetime(2029, 1, 1, tzinfo=UTC) + timedelta(days=7 * n),
        )
        for n in range(STATS_ROWS)
    ]
    trusting = SectorStatsRepository(FakeSources(fingerprints), main_db)
    for row in rows[:-1]:
        trusting.save(row)
    SectorStatsRepository(store, main_db).save(rows[-1])  # full recompute, twice

    SectorApprovalStore(main_db).add(
        ApprovalRecord(
            kind="first_transition_risk",
            run_id=rows[-1].run_id,
            method_version=V1.method_version,
            operator="ceo",
            reviewer="risk-compliance-officer",
            review_doc_path="work/reviews/x.md",
            review_doc_blob_hash="0" * 40,
            approved_at=NOW,
        )
    )
    registry.record_accumulation_start(V1.method_version, days[0])
    return Scale(
        big_market=big_market,
        small_market=small_market,
        main_db=main_db,
        positions=PositionStore(base / "positions.db"),
        board_source_run_ids_chars=len(bloated),
    )


def test_statistics_carry_no_run_list_and_fixed_width_sources(scale: Scale) -> None:
    with closing(sqlite3.connect(scale.main_db)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sector_rank_stats)")}
        count, widest = conn.execute(
            "SELECT COUNT(*), MAX(length(CAST(source_run_min AS TEXT))"
            " + length(CAST(source_run_max AS TEXT)) + length(source_session_end)"
            " + length(CAST(source_run_count AS TEXT)) + length(source_digest))"
            " FROM sector_rank_stats"
        ).fetchone()
    assert "source_run_ids" not in columns
    assert count == STATS_ROWS
    assert widest <= 256
    read = SectorCardReader(verifier=MarketPanelReader(scale.big_market), db_path=scale.main_db)
    card = read.read("TW", V1.method_version)
    assert card.stats_rejected is None
    assert len(card.stats_history) == STATS_ROWS
    assert card.stats_history[-1].source_run_count == TOTAL_RUNS


@dataclass
class Traffic:
    statements: list[str]
    main_db_chars: int
    #: The part of ``main_db_chars`` fetched by the board statement.
    board_chars: int
    tally_calls: int
    body: dict[str, Any]


@contextmanager
def _watch(main_db: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Traffic]:
    """Every SQL statement, the characters fetched from ``main_db``, verifier calls."""
    traffic = Traffic(statements=[], main_db_chars=0, board_chars=0, tally_calls=0, body={})
    real_connect = sqlite3.connect
    real_tally = MarketPanelReader.source_tally

    def count_row(cursor: sqlite3.Cursor, row: tuple[object, ...]) -> tuple[object, ...]:
        chars = sum(len(str(value)) for value in row if value is not None)
        traffic.main_db_chars += chars
        if any(column[0] == "bars_run_id" for column in cursor.description):
            traffic.board_chars += chars
        return row

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(traffic.statements.append)
        if args and str(args[0]) == str(main_db):
            conn.row_factory = count_row
        return conn

    def tally(self: MarketPanelReader, *args: Any, **kwargs: Any) -> Any:
        traffic.tally_calls += 1
        return real_tally(self, *args, **kwargs)

    def no_digest(*args: object, **kwargs: object) -> object:
        raise AssertionError("the read path computed a digest")

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", connect)
        patch.setattr(MarketPanelReader, "source_tally", tally)
        patch.setattr(panel_module, "source_fingerprint", no_digest)
        patch.setattr(market_panel, "source_fingerprint", no_digest)
        yield traffic


def _request(scale: Scale, market_db: Path, monkeypatch: pytest.MonkeyPatch) -> Traffic:
    with card_client(
        main_db=scale.main_db,
        market_db=market_db,
        positions=scale.positions,
        runtime=verified_runtime(),
        now=NOW,
    ) as client:
        with _watch(scale.main_db, monkeypatch) as traffic:
            response = client.get("/api/sectors/momentum", params={"market": "TW"})
    assert response.status_code == 200, response.text
    traffic.body = response.json()
    return traffic


def _source_checks(statements: list[str]) -> list[str]:
    return [s for s in statements if "json_group_array" in s]


def test_the_endpoint_budget_holds_at_a_hundred_thousand_runs(
    scale: Scale, monkeypatch: pytest.MonkeyPatch
) -> None:
    traffic = _request(scale, scale.big_market, monkeypatch)
    assert len(traffic.statements) <= 7, traffic.statements
    assert len(_source_checks(traffic.statements)) == 1
    assert traffic.tally_calls == 1
    assert not any("source_run_ids" in s for s in traffic.statements)
    assert "data_quality" not in traffic.body["not_evaluated_reasons"]


def test_main_db_traffic_does_not_depend_on_the_market_db_run_count(
    scale: Scale, monkeypatch: pytest.MonkeyPatch
) -> None:
    big = _request(scale, scale.big_market, monkeypatch)
    small = _request(scale, scale.small_market, monkeypatch)
    assert big.main_db_chars == small.main_db_chars
    # The whole board read is smaller than the one column it must not select.
    assert 0 < big.board_chars < scale.board_source_run_ids_chars
    # The 1,000-run file is another market DB: the batch is refused (NE-6), same fetch.
    assert "data_quality" in small.body["not_evaluated_reasons"]
    assert len(_source_checks(small.statements)) == 1 and small.tally_calls == 1
    assert len(big.statements) == len(small.statements)
