"""Backfill of existing holdings' industry category from the security directory.

The load-bearing rule is "never overwrite": a category the user chose by hand
outranks anything the directory says, because the sector cap buckets a
holding by that value and a sync job must not move a holding between buckets
behind their back.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.directory.models import DirectoryEntry, DirectorySectorAssignment
from app.directory.sector_backfill import backfill_position_sectors
from app.directory.store import SecurityDirectoryStore
from app.positions.models import Position, PositionInput
from app.positions.store import PositionStore

AS_OF = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
SECTOR_AS_OF = datetime(2026, 8, 16, 3, 0, tzinfo=UTC)


def _directory(tmp_path: Path) -> SecurityDirectoryStore:
    store = SecurityDirectoryStore(db_path=tmp_path / "d.db")
    store.upsert(
        [
            DirectoryEntry(
                symbol="2330", name="台積電", market="TW", source="twse_openapi", as_of=AS_OF
            ),
            DirectoryEntry(
                symbol="2317", name="鴻海", market="TW", source="twse_openapi", as_of=AS_OF
            ),
            # An ETF: in the directory, but absent from the 產業別 dataset.
            DirectoryEntry(
                symbol="0050", name="元大台灣50", market="TW", source="twse_openapi", as_of=AS_OF
            ),
            # 上櫃: same story, from the TPEx source.
            DirectoryEntry(
                symbol="5483", name="中美晶", market="TW", source="tpex_openapi", as_of=AS_OF
            ),
        ]
    )
    store.apply_sectors(
        [
            DirectorySectorAssignment(
                symbol=symbol,
                market="TW",
                sector=sector,
                source="twse_openapi_t187ap03_L",
                as_of=SECTOR_AS_OF,
            )
            for symbol, sector in (("2330", "半導體業"), ("2317", "電子零組件業"))
        ]
    )
    return store


def _positions(tmp_path: Path) -> PositionStore:
    return PositionStore(db_path=tmp_path / "p.db")


class _StaleScanPositionStore(PositionStore):
    """A store whose scan answers from before a concurrent edit landed.

    Writes still go to the real database, so the compare-and-set meets the row
    as it actually is -- the window the backfill has to survive.
    """

    def __init__(self, db_path: Path, snapshot: list[Position]) -> None:
        super().__init__(db_path=db_path)
        self._snapshot = snapshot

    def list_all(self) -> list[Position]:
        return self._snapshot


def _add(store: PositionStore, **overrides: object) -> int:
    payload: dict[str, object] = {
        "symbol": "2330",
        "market": "TW",
        "quantity": "1000",
        "avg_cost": "600",
        "currency": "TWD",
        "instrument_type": "stock",
    }
    payload.update(overrides)
    return store.create(PositionInput.model_validate(payload)).id


def test_fills_an_empty_tw_holding_from_the_directory(tmp_path: Path) -> None:
    positions = _positions(tmp_path)
    position_id = _add(positions, symbol="2330")

    report = backfill_position_sectors(
        position_store=positions, directory_store=_directory(tmp_path)
    )

    assert report.filled == (("2330", "半導體業"),)
    assert report.filled_count == 1
    stored = positions.get(position_id)
    assert stored is not None
    assert stored.sector == "半導體業"


def test_never_overwrites_a_manually_chosen_category(tmp_path: Path) -> None:
    """The user filed 2330 under 其他業; the directory says 半導體業. The user wins."""
    positions = _positions(tmp_path)
    position_id = _add(positions, symbol="2330", sector="其他業")

    report = backfill_position_sectors(
        position_store=positions, directory_store=_directory(tmp_path)
    )

    assert report.filled == ()
    assert report.skipped_already_set == 1
    stored = positions.get(position_id)
    assert stored is not None
    assert stored.sector == "其他業"


def test_a_category_saved_mid_run_is_not_overwritten(tmp_path: Path) -> None:
    """The race the compare-and-set closes.

    The scan reads the holding as unclassified; the user saves 其他業 through
    the API before the write lands. The write must find the row taken and
    report a skip, not clobber the value the user is looking at.
    """
    positions = _positions(tmp_path)
    position_id = _add(positions, symbol="2330")
    stale_snapshot = positions.list_all()
    # The user's edit, landing after the scan above and before the write below.
    with closing(sqlite3.connect(positions.db_path)) as conn, conn:
        conn.execute("UPDATE positions SET sector = ? WHERE id = ?", ("其他業", position_id))

    report = backfill_position_sectors(
        position_store=_StaleScanPositionStore(tmp_path / "p.db", stale_snapshot),
        directory_store=_directory(tmp_path),
    )

    assert report.filled == ()
    assert report.skipped_already_set == 1
    stored = positions.get(position_id)
    assert stored is not None
    assert stored.sector == "其他業"


def test_skips_us_holdings(tmp_path: Path) -> None:
    positions = _positions(tmp_path)
    position_id = _add(positions, symbol="AAPL", market="US", currency="USD")

    report = backfill_position_sectors(
        position_store=positions, directory_store=_directory(tmp_path)
    )

    assert report.skipped_not_tw == 1
    assert report.filled == ()
    stored = positions.get(position_id)
    assert stored is not None
    assert stored.sector is None


def test_skips_a_symbol_the_directory_has_never_seen(tmp_path: Path) -> None:
    positions = _positions(tmp_path)
    _add(positions, symbol="9999")

    report = backfill_position_sectors(
        position_store=positions, directory_store=_directory(tmp_path)
    )

    assert report.skipped_not_in_directory == 1
    assert report.filled == ()


def test_leaves_etf_and_otc_holdings_empty_rather_than_guessing(tmp_path: Path) -> None:
    positions = _positions(tmp_path)
    etf_id = _add(positions, symbol="0050", instrument_type="etf")
    otc_id = _add(positions, symbol="5483")

    report = backfill_position_sectors(
        position_store=positions, directory_store=_directory(tmp_path)
    )

    assert report.skipped_directory_has_no_sector == 2
    assert report.filled == ()
    for position_id in (etf_id, otc_id):
        stored = positions.get(position_id)
        assert stored is not None
        assert stored.sector is None


def test_is_idempotent_second_run_writes_nothing(tmp_path: Path) -> None:
    positions = _positions(tmp_path)
    _add(positions, symbol="2330")
    directory = _directory(tmp_path)

    first = backfill_position_sectors(position_store=positions, directory_store=directory)
    second = backfill_position_sectors(position_store=positions, directory_store=directory)

    assert first.filled_count == 1
    assert second.filled_count == 0
    assert second.skipped_already_set == 1


def test_every_position_is_accounted_for_in_the_report(tmp_path: Path) -> None:
    positions = _positions(tmp_path)
    _add(positions, symbol="2330")
    _add(positions, symbol="2317")
    _add(positions, symbol="0050", instrument_type="etf")
    _add(positions, symbol="9999")
    _add(positions, symbol="AAPL", market="US", currency="USD")
    _add(positions, symbol="1101", sector="水泥工業")

    report = backfill_position_sectors(
        position_store=positions, directory_store=_directory(tmp_path)
    )

    assert report.considered_count == 6
    assert report.filled_count == 2
    assert report.skipped_count == 4
    assert report.skipped_already_set == 1
    assert report.skipped_not_tw == 1
    assert report.skipped_not_in_directory == 1
    assert report.skipped_directory_has_no_sector == 1


def test_backfill_on_an_unsynced_directory_changes_nothing(tmp_path: Path) -> None:
    positions = _positions(tmp_path)
    _add(positions, symbol="2330")
    empty_directory = SecurityDirectoryStore(db_path=tmp_path / "empty.db")

    report = backfill_position_sectors(
        position_store=positions, directory_store=empty_directory
    )

    assert report.filled == ()
    assert report.skipped_not_in_directory == 1


def test_backfill_advances_updated_at_only_on_rows_it_filled(tmp_path: Path) -> None:
    positions = _positions(tmp_path)
    filled_id = _add(positions, symbol="2330")
    untouched_id = _add(positions, symbol="1101", sector="水泥工業")
    before_untouched = positions.get(untouched_id)
    assert before_untouched is not None

    moment = datetime(2026, 8, 16, 9, 30, tzinfo=UTC)
    backfill_position_sectors(
        position_store=positions, directory_store=_directory(tmp_path), now=moment
    )

    filled = positions.get(filled_id)
    untouched = positions.get(untouched_id)
    assert filled is not None and untouched is not None
    assert filled.updated_at == moment
    assert untouched.updated_at == before_untouched.updated_at
