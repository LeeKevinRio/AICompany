"""Statistics-row source fingerprints (ADR-0012 C-50; T-33, T-35).

* :func:`app.data.panel.source_fingerprint` -- the one implementation -- is
  indifferent to row order and to the evaluator's normalisation, binds every
  ``RUNS_COLUMNS`` field of the ``ok`` runs, and refuses non-market run ids;
* **T-33** (write side), on a real ``MarketPanelStore`` holding warm-up-shaped
  runs (one per symbol per day, ``record_symbol_backfill``) and the four
  forward kinds: the fingerprint the evaluator stored equals the verifier's
  recompute in all five fields; runs written after the evaluation (a
  correction included) leave it unchanged; each tampering on its own makes
  ``save()`` raise ``BiasedDataRejected`` with the main DB untouched; and a
  verifier that only checks ``source_run_max`` exists would let them through
  (teeth);
* **T-35** (read side), end to end through ``GET /api/sectors/momentum``: a
  different, larger market DB, an older row whose ``source_run_min`` is gone,
  or no market DB at all refuse the whole batch -- 200 with NE-6
  (``data_quality``) and no ``historical_stat``; an accepted read is one
  verifier call, one SQL statement, and never a digest.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app.data import market_panel
from app.data import panel as panel_module
from app.data.market_panel import MarketPanelReader, MarketPanelStore
from app.data.panel import MarketPanel, SourceFingerprint, source_fingerprint
from app.positions.store import PositionStore
from app.research.sector_biased.study import backfill_frames
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from app.sectors.definition import GateRules, SectorMomentumDefinition
from app.sectors.models import StatsRecord
from app.sectors.store import (
    BiasedDataRejected,
    SectorCardReader,
    SectorMethodRegistry,
    SectorStatsRepository,
    record_fingerprint,
)
from app.services.sector_attestation import AttestationCheck
from app.services.sector_board import EVALUATION_HISTORY_START, SectorBoardService
from tests.published_helpers import published
from tests.sector_board_helpers import (
    card_client,
    live_card,
    stats_record,
    store_market,
    verified_runtime,
)
from tests.sector_eval_helpers import SyntheticMarket, synthetic_market
from tests.source_helpers import FakeSources, source_fields, with_sources

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


def _copy_db(source: Path, target: Path) -> Path:
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    return target


def _counts(main_db: Path) -> tuple[int, int]:
    with closing(sqlite3.connect(main_db)) as conn:
        (stats,) = conn.execute("SELECT COUNT(*) FROM sector_rank_stats").fetchone()
        (checks,) = conn.execute("SELECT COUNT(*) FROM sector_gate_checks").fetchone()
    return int(stats), int(checks)


# ---------------------------------------------------------------------------
# The one fingerprint function
# ---------------------------------------------------------------------------


def _runs(rows: list[tuple[object, ...]]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "run_id",
            "kind",
            "session_date",
            "recorded_at",
            "source",
            "status",
            "row_count",
            "expected_count",
        ],
    )


def _stamp(day: int, hour: int = 10) -> pd.Timestamp:
    return pd.Timestamp(datetime(2026, 9, day, hour, tzinfo=UTC))


BASE_RUNS = [
    ("1", "bars", date(2026, 9, 1), _stamp(1), "finmind_warmup", "ok", 1, None),
    ("2", "bars", date(2026, 9, 2), _stamp(2), "twse_snapshot", "ok", 980, 1000),
    ("3", "listing", date(2026, 9, 2), _stamp(2), "twse_t187ap03_L", "ok", 1000, 1000),
    ("4", "bars", date(2026, 9, 3), _stamp(3), "twse_snapshot", "failed", 0, 1000),
]


def test_the_fingerprint_covers_ok_runs_in_run_id_order() -> None:
    fingerprint = source_fingerprint(_runs(BASE_RUNS))
    assert fingerprint is not None
    assert (fingerprint.run_min, fingerprint.run_max, fingerprint.run_count) == (1, 3, 3)
    assert fingerprint.session_end == date(2026, 9, 2)  # the failed run is not a source
    assert len(fingerprint.digest) == 64
    shuffled = _runs(list(reversed(BASE_RUNS)))
    assert source_fingerprint(shuffled) == fingerprint
    # The evaluator hashes MarketPanel's normalised copy; the verifier the raw one.
    empty = pd.DataFrame()
    frames = panel_module.PanelFrames(
        bars=empty.reindex(columns=list(panel_module.BARS_COLUMNS)),
        listing=empty.reindex(columns=list(panel_module.LISTING_COLUMNS)),
        classification=empty.reindex(columns=list(panel_module.CLASSIFICATION_COLUMNS)),
        ex_dividend=empty.reindex(columns=list(panel_module.EX_DIVIDEND_COLUMNS)),
        runs=_runs(BASE_RUNS),
    )
    assert source_fingerprint(MarketPanel(frames).frames.runs) == fingerprint


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("kind", "classification"),
        ("session_date", date(2026, 8, 31)),
        ("recorded_at", _stamp(2, 11)),
        ("source", "finmind"),
        ("row_count", 979),
        ("expected_count", 999),
    ],
)
def test_every_runs_column_is_bound_by_the_digest(column: str, value: object) -> None:
    changed = _runs(BASE_RUNS)
    changed.loc[1, column] = value
    before, after = source_fingerprint(_runs(BASE_RUNS)), source_fingerprint(changed)
    assert before is not None and after is not None
    assert after.digest != before.digest


def test_the_fingerprint_refuses_what_no_market_db_holds() -> None:
    assert source_fingerprint(_runs([BASE_RUNS[3]])) is None  # no ok run
    with pytest.raises(ValueError, match="not a market-DB run id"):
        source_fingerprint(_runs([("bf-bars-000001", *BASE_RUNS[0][1:])]))
    naive = _runs(BASE_RUNS).assign(recorded_at=pd.Timestamp("2026-09-01 10:00"))
    with pytest.raises(ValueError, match="timezone"):
        source_fingerprint(naive)


#: ``BASE_RUNS``' digest before free-text escaping existed (qa v9 low item): pinned,
#: so escaping provably leaves every ordinary digest -- and every stored row -- as it was.
BASE_RUNS_DIGEST = "ec07a1a6060e361d75400dde02267569ce17ba20212114f9439ba438bb48dbd3"


def test_escaping_leaves_ordinary_digests_unchanged() -> None:
    fingerprint = source_fingerprint(_runs(list[tuple[object, ...]](BASE_RUNS)))
    assert fingerprint is not None and fingerprint.digest == BASE_RUNS_DIGEST


def _forged_single_run() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two honest runs, and one run whose ``source`` spells out the rest of both.

    Without escaping, the forged run's canonical line is the two honest lines
    joined by the line separator, so the digests collide.
    """
    rows: list[tuple[object, ...]] = [BASE_RUNS[0], BASE_RUNS[1]]
    honest = _runs(rows)
    separator = panel_module._FIELD_SEPARATOR
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(panel_module, "_escape_field", lambda text: text)
        (_, first), (_, second) = panel_module._canonical_run_rows(honest)
    first_fields, second_fields = first.split(separator), second.split(separator)
    source = separator.join(first_fields[4:]) + "\n" + separator.join(second_fields[:5])
    forged = _runs([(*BASE_RUNS[0][:4], source, "ok", 980, 1000)])
    return honest, forged


def test_a_separator_inside_a_text_field_cannot_forge_a_run_boundary() -> None:
    honest, forged = _forged_single_run()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(panel_module, "_escape_field", lambda text: text)
        unescaped = source_fingerprint(honest), source_fingerprint(forged)
    assert unescaped[0] is not None and unescaped[1] is not None
    assert unescaped[0].digest == unescaped[1].digest  # teeth: the forgery works unescaped
    escaped = source_fingerprint(honest), source_fingerprint(forged)
    assert escaped[0] is not None and escaped[1] is not None
    assert escaped[0].digest != escaped[1].digest


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("twse_snapshot", "twse_snapshot"),
        ("a\x1fb", "a\\x1fb"),
        ("a\nb", "a\\nb"),
        ("a\\b", "a\\\\b"),
        # The literal characters of an escape are not confused with the escape itself.
        ("a\\x1fb", "a\\\\x1fb"),
    ],
)
def test_free_text_escaping_is_injective(text: str, escaped: str) -> None:
    assert panel_module._escape_field(text) == escaped


@pytest.mark.parametrize(
    ("run_id", "message"),
    [
        ("bf-bars-000001", "not a market-DB run id"),
        (1.0, "has type float"),
        (True, "is a boolean"),
    ],
)
def test_a_bad_run_id_says_whether_type_or_value_is_wrong(run_id: object, message: str) -> None:
    frame = _runs([(run_id, *BASE_RUNS[0][1:])])
    with pytest.raises(ValueError, match=message):
        source_fingerprint(frame)


def test_integer_run_ids_of_any_kind_are_accepted() -> None:
    as_text = source_fingerprint(_runs(list[tuple[object, ...]](BASE_RUNS)))
    rows: list[tuple[object, ...]] = [(int(str(row[0])), *row[1:]) for row in BASE_RUNS]
    as_int = source_fingerprint(_runs(rows))
    assert as_text == as_int


# ---------------------------------------------------------------------------
# T-33: the write side on a real market DB
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Judged:
    market: SyntheticMarket
    market_db: Path
    main_db: Path
    row: StatsRecord


@pytest.fixture(scope="module")
def judged(tmp_path_factory: pytest.TempPathFactory) -> Judged:
    base = tmp_path_factory.mktemp("t33")
    market = synthetic_market(seed=21, warmup=62, forward=48, n_dividends=5)
    store = store_market(market, base / "market.db", warmup_per_symbol=True)
    main_db = base / "main.db"
    SectorMethodRegistry(main_db).register(FAST, frozen_commit="c0ffee", registered_at=NOW)
    service = SectorBoardService(
        market_store=store,
        main_db=main_db,
        attestation=lambda: GOOD,
        clock=lambda: NOW,
        definition=FAST,
    )
    result = service.refresh()
    assert result.stats_run_id is not None, result.notes
    row = service.stats.find(result.stats_run_id)
    assert row is not None
    return Judged(market=market, market_db=base / "market.db", main_db=main_db, row=row)


def test_the_market_db_holds_warm_up_shaped_runs(judged: Judged) -> None:
    with closing(sqlite3.connect(judged.market_db)) as conn:
        warm, kinds = conn.execute(
            "SELECT SUM(source = 'finmind_warmup'), COUNT(DISTINCT kind) FROM pit_snapshot_runs"
        ).fetchone()
    symbols = sum(len(members) for members in judged.market.members.values())
    warm_days = judged.market.calendar.index(judged.market.d0)
    assert warm == symbols * warm_days  # one run per symbol per day
    assert kinds == 4


def test_the_evaluator_and_the_verifier_agree_on_all_five_fields(judged: Judged) -> None:
    store = MarketPanelStore(judged.market_db)
    t = store.last_ok_session("bars")  # what the service loaded the evaluation up to
    assert t is not None
    evaluated = MarketPanel(store.load_panel_frames(EVALUATION_HISTORY_START, t))
    by_evaluator = source_fingerprint(evaluated.frames.runs)
    recomputed = store.source_fingerprint(judged.row.source_run_max, judged.row.source_session_end)
    assert by_evaluator is not None and recomputed is not None
    assert record_fingerprint(judged.row) == by_evaluator == recomputed
    assert (
        MarketPanelReader(judged.market_db).source_fingerprint(
            judged.row.source_run_max, judged.row.source_session_end
        )
        == recomputed
    )


def test_runs_written_after_the_evaluation_leave_the_fingerprint_unchanged(
    judged: Judged, tmp_path: Path
) -> None:
    market_db = _copy_db(judged.market_db, tmp_path / "market.db")
    row = judged.row
    clock = {"now": NOW}
    store = MarketPanelStore(market_db, clock=lambda: clock["now"])
    # A correction of an already-covered session, then a whole new session.
    corrected = judged.market.calendar[judged.market.calendar.index(row.source_session_end) - 3]
    store.record_run(
        kind="bars",
        session_date=corrected,
        source="twse_snapshot",
        status="ok",
        row_count=0,
        expected_count=0,
    )
    after = row.source_session_end + timedelta(days=1)
    clock["now"] = NOW + timedelta(days=1)
    for kind in ("bars", "listing", "classification", "dividend_announce"):
        store.record_run(
            kind=kind,  # type: ignore[arg-type]
            session_date=after,
            source="t",
            status="ok",
            row_count=0,
            expected_count=None,
        )
    assert store.source_fingerprint(row.source_run_max, row.source_session_end) == (
        record_fingerprint(row)
    )
    main_db = _copy_db(judged.main_db, tmp_path / "main.db")
    SectorStatsRepository(store, main_db).save(
        dataclasses.replace(row, run_id="again", computed_at=NOW + timedelta(days=2))
    )
    assert _counts(main_db)[0] == _counts(judged.main_db)[0] + 1


def _later(row: StatsRecord, **changes: object) -> StatsRecord:
    return dataclasses.replace(
        row, run_id="tampered", computed_at=row.computed_at + timedelta(days=7), **changes
    )


def _research_fingerprint(market: SyntheticMarket) -> SourceFingerprint:
    """What an evaluator reading the research DB would claim, renumbered to look like runs."""
    bars = market.panel.frames.bars.loc[
        :, ["symbol", "session_date", "open", "high", "low", "close", "shares", "traded_value"]
    ]
    symbols = sorted(set(bars["symbol"]))
    research = backfill_frames(
        bars,
        listing=symbols,
        classification={symbol: ("01", "S01") for symbol in symbols},
        fetched_at=NOW,
    ).runs
    with pytest.raises(ValueError):
        source_fingerprint(research)  # bf-* ids are not market-DB runs at all
    renumbered = research.assign(run_id=[str(n) for n in range(1, len(research) + 1)])
    claimed = source_fingerprint(renumbered)
    assert claimed is not None
    return claimed


#: Each builds, on copies of the judged DBs, one tampered record for ``save()``.
Tamper = Callable[[Judged, MarketPanelStore, Path], StatsRecord]


def _count_off_by_one(j: Judged, store: MarketPanelStore, main_db: Path) -> StatsRecord:
    return _later(j.row, source_run_count=j.row.source_run_count - 1)


def _digest_one_character(j: Judged, store: MarketPanelStore, main_db: Path) -> StatsRecord:
    last = j.row.source_digest[-1]
    return _later(j.row, source_digest=j.row.source_digest[:-1] + ("0" if last != "0" else "1"))


def _run_max_missing(j: Judged, store: MarketPanelStore, main_db: Path) -> StatsRecord:
    return _later(j.row, source_run_max=j.row.source_run_max + 10_000)


def _run_max_not_ok(j: Judged, store: MarketPanelStore, main_db: Path) -> StatsRecord:
    failed = store.record_run(
        kind="bars",
        session_date=j.row.source_session_end,
        source="twse_snapshot",
        status="failed",
        row_count=0,
        expected_count=1000,
    )
    return _later(j.row, source_run_max=failed)


def _run_min_mismatch(j: Judged, store: MarketPanelStore, main_db: Path) -> StatsRecord:
    return _later(j.row, source_run_min=j.row.source_run_min + 1)


def _run_count_zero(j: Judged, store: MarketPanelStore, main_db: Path) -> StatsRecord:
    return _later(j.row, source_run_count=0)


def _from_the_research_db(j: Judged, store: MarketPanelStore, main_db: Path) -> StatsRecord:
    return with_sources(_later(j.row), _research_fingerprint(j.market))


def _previous_row_mismatch(j: Judged, store: MarketPanelStore, main_db: Path) -> StatsRecord:
    """A stored row the market DB does not reproduce, then a genuine row after it."""
    stored = record_fingerprint(j.row)
    bad = dataclasses.replace(stored, run_count=stored.run_count + 1, digest="f" * 64)
    bad = dataclasses.replace(bad, session_end=stored.session_end + timedelta(days=1))
    # Saved against a market DB that held it (the fake), next to the genuine row.
    SectorStatsRepository(FakeSources((stored, bad)), main_db).save(
        with_sources(
            dataclasses.replace(
                j.row, run_id="previous", computed_at=j.row.computed_at + timedelta(days=1)
            ),
            bad,
        )
    )
    return _later(j.row)


TAMPERING: dict[str, Tamper] = {
    "count_off_by_one": _count_off_by_one,
    "digest_one_character": _digest_one_character,
    "run_max_missing": _run_max_missing,
    "run_max_not_ok": _run_max_not_ok,
    "run_min_mismatch": _run_min_mismatch,
    "run_count_zero": _run_count_zero,
    "from_the_research_db": _from_the_research_db,
    "previous_row_mismatch": _previous_row_mismatch,
}


def _prepare(
    judged: Judged, tmp_path: Path, name: str
) -> tuple[MarketPanelStore, Path, StatsRecord, tuple[int, int]]:
    """Set the case up on copies: the store, the main DB, the record and the counts before."""
    store = MarketPanelStore(_copy_db(judged.market_db, tmp_path / f"{name}-market.db"))
    main_db = _copy_db(judged.main_db, tmp_path / f"{name}-main.db")
    record = TAMPERING[name](judged, store, main_db)
    return store, main_db, record, _counts(main_db)


@pytest.mark.parametrize("name", sorted(TAMPERING))
def test_each_tampering_alone_is_refused_on_save(judged: Judged, tmp_path: Path, name: str) -> None:
    store, main_db, record, before = _prepare(judged, tmp_path, name)
    with pytest.raises(BiasedDataRejected):
        SectorStatsRepository(store, main_db).save(record)
    assert _counts(main_db) == before


def test_the_tampering_table_has_teeth(
    judged: Judged, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A verifier that only asks whether ``source_run_max`` exists lets tampering through."""

    def run_max_exists_only(self: SectorStatsRepository, run_id: str, claimed: Any) -> None:
        tally = self._verifier.source_tally({claimed.run_max}, claimed.run_max, claimed.session_end)
        if claimed.run_max not in tally.ok_endpoints:
            raise BiasedDataRejected(f"{run_id}: source_run_max does not exist")

    monkeypatch.setattr(SectorStatsRepository, "_recompute", run_max_exists_only)
    slipped = []
    for name in sorted(TAMPERING):
        store, main_db, record, before = _prepare(judged, tmp_path, name)
        try:
            SectorStatsRepository(store, main_db).save(record)
        except BiasedDataRejected:
            continue
        assert _counts(main_db) != before
        slipped.append(name)
    assert {"count_off_by_one", "digest_one_character", "previous_row_mismatch"} <= set(slipped)


# ---------------------------------------------------------------------------
# T-35: the read side, end to end
# ---------------------------------------------------------------------------


def _momentum(main_db: Path, market_db: Path, positions: PositionStore) -> dict[str, Any]:
    with card_client(
        main_db=main_db,
        market_db=market_db,
        positions=positions,
        runtime=verified_runtime(),
        now=datetime(2029, 3, 12, 12, tzinfo=UTC),
    ) as client:
        response = client.get("/api/sectors/momentum", params={"market": "TW"})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _refused(body: dict[str, Any]) -> None:
    assert "data_quality" in body["not_evaluated_reasons"]
    assert body["historical_stat"] is None and body["gate_checks"] is None


def test_an_accepted_read_is_one_call_one_statement_and_no_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = live_card(tmp_path, 10, now=NOW)

    def no_digest(*args: object, **kwargs: object) -> object:
        raise AssertionError("the read path computed a digest")

    calls = {"tally": 0}
    real_tally = MarketPanelReader.source_tally

    def counting(self: MarketPanelReader, *args: Any, **kwargs: Any) -> Any:
        calls["tally"] += 1
        return real_tally(self, *args, **kwargs)

    statements: list[str] = []
    real_connect = sqlite3.connect

    def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    with card_client(
        main_db=live.main_db,
        market_db=live.market_db,
        positions=live.positions,
        runtime=verified_runtime(),
        now=datetime(2029, 3, 12, 12, tzinfo=UTC),
    ) as client:
        monkeypatch.setattr(panel_module, "source_fingerprint", no_digest)
        monkeypatch.setattr(market_panel, "source_fingerprint", no_digest)
        monkeypatch.setattr(MarketPanelReader, "source_tally", counting)
        monkeypatch.setattr(sqlite3, "connect", connect)
        response = client.get("/api/sectors/momentum", params={"market": "TW"})
    assert response.status_code == 200, response.text
    assert "data_quality" not in response.json()["not_evaluated_reasons"]
    assert calls["tally"] == 1
    assert len([s for s in statements if "json_group_array" in s]) == 1


def test_a_different_larger_market_db_refuses_the_batch(tmp_path: Path) -> None:
    live = live_card(tmp_path, 10, now=NOW)
    other = store_market(
        synthetic_market(seed=99, warmup=70, forward=40, n_dividends=2), tmp_path / "other.db"
    )
    with (
        closing(sqlite3.connect(live.market_db)) as small,
        closing(sqlite3.connect(other.db_path)) as large,
    ):
        assert (
            large.execute("SELECT COUNT(*) FROM pit_snapshot_runs").fetchone()[0]
            > small.execute("SELECT COUNT(*) FROM pit_snapshot_runs").fetchone()[0]
        )
    read = SectorCardReader(verifier=MarketPanelReader(other.db_path), db_path=live.main_db).read(
        "TW", V1.method_version
    )
    assert read.stats_history == ()
    assert read.stats_rejected is not None and "source set" in read.stats_rejected
    _refused(_momentum(live.main_db, other.db_path, live.positions))


def test_an_older_row_whose_first_run_is_gone_refuses_the_batch(tmp_path: Path) -> None:
    live = live_card(tmp_path, 10, now=NOW)
    reader = MarketPanelReader(live.market_db)
    (current,) = SectorStatsRepository(MarketPanelStore(live.market_db), live.main_db).load(
        V1.method_version
    )
    assert _momentum(live.main_db, live.market_db, live.positions)["historical_stat"] is not None
    # A gap in run ids (as after a restore that lost runs), then one more ok run.
    with closing(sqlite3.connect(live.market_db)) as conn, conn:
        conn.execute("UPDATE sqlite_sequence SET seq = seq + 100 WHERE name = 'pit_snapshot_runs'")
    after_gap = MarketPanelStore(live.market_db).record_run(
        kind="listing",
        session_date=current.source_session_end + timedelta(days=1),
        source="t",
        status="ok",
        row_count=0,
        expected_count=None,
    )
    gone = after_gap - 50
    assert MarketPanelReader(live.market_db).source_tally(
        {gone, after_gap}, after_gap, current.source_session_end
    ).ok_endpoints == {after_gap}
    older = with_sources(
        stats_record("older", computed_at=current.computed_at - timedelta(days=30)),
        dataclasses.replace(record_fingerprint(current), run_min=gone, run_max=after_gap),
    )
    SectorStatsRepository(
        FakeSources((record_fingerprint(older), record_fingerprint(current))), live.main_db
    ).save(older)
    read = SectorCardReader(verifier=reader, db_path=live.main_db).read("TW", V1.method_version)
    assert read.stats_rejected is not None and "older" in read.stats_rejected
    _refused(_momentum(live.main_db, live.market_db, live.positions))


def test_a_missing_market_db_refuses_the_batch(tmp_path: Path) -> None:
    live = live_card(tmp_path, 10, now=NOW)
    missing = tmp_path / "gone" / "market.db"
    _refused(_momentum(live.main_db, missing, live.positions))
    assert not missing.parent.exists()


def test_source_fields_round_trip_through_the_helpers() -> None:
    """The test helpers' five fields are the record's (guards the fixtures above)."""
    record = stats_record("x")
    assert source_fields(record_fingerprint(record)) == {
        "source_run_min": record.source_run_min,
        "source_run_max": record.source_run_max,
        "source_session_end": record.source_session_end,
        "source_run_count": record.source_run_count,
        "source_digest": record.source_digest,
    }
