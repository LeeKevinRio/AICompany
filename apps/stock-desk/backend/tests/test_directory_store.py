"""Tests for ``SecurityDirectoryStore``: idempotent upsert, resolve, search."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.directory.models import DirectoryEntry
from app.directory.store import SecurityDirectoryStore

AS_OF = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _entry(symbol: str, name: str, *, source: str = "twse_openapi") -> DirectoryEntry:
    return DirectoryEntry(symbol=symbol, name=name, market="TW", source=source, as_of=AS_OF)


def _store(tmp_path: Path) -> SecurityDirectoryStore:
    return SecurityDirectoryStore(db_path=tmp_path / "directory.db")


def test_empty_store_is_not_synced(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.is_synced() is False
    assert store.count() == 0
    assert store.resolve("2330") is None


def test_upsert_then_resolve_hits(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert([_entry("2330", "台積電")])

    entry = store.resolve("2330")
    assert entry is not None
    assert entry.symbol == "2330"
    assert entry.name == "台積電"
    assert entry.market == "TW"
    assert entry.source == "twse_openapi"
    assert store.is_synced() is True


def test_resolve_miss_returns_none(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert([_entry("2330", "台積電")])
    assert store.resolve("9999X") is None


def test_upsert_is_idempotent_by_symbol_and_market(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert([_entry("2330", "台積電")])
    store.upsert([_entry("2330", "台積電")])
    store.upsert([_entry("2330", "台積電")])

    assert store.count() == 1


def test_upsert_refreshes_name_on_rerun(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert([_entry("2330", "台積電（舊名）")])
    store.upsert([_entry("2330", "台積電")])

    entry = store.resolve("2330")
    assert entry is not None
    assert entry.name == "台積電"
    assert store.count() == 1


def test_search_prefix_matches_only_symbols_starting_with_query(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert(
        [
            _entry("3037", "欣興"),
            _entry("0050", "元大台灣50"),
            _entry("1330", "無關公司"),
        ]
    )

    items, truncated = store.search("30", limit=12)

    symbols = [item.symbol for item in items]
    assert "3037" in symbols
    assert "1330" not in symbols
    assert truncated is False


def test_search_substring_matches_company_name(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert([_entry("2330", "台積電")])

    items, truncated = store.search("台積電", limit=12)

    assert len(items) == 1
    assert items[0].symbol == "2330"
    assert items[0].name == "台積電"
    assert items[0].market == "TW"
    assert truncated is False


def test_search_symbol_prefix_hits_ranked_before_name_hits(tmp_path: Path) -> None:
    store = _store(tmp_path)
    # "22" is a name-substring hit (公司名稱含"22"), "2200" is a symbol-prefix hit.
    store.upsert(
        [
            _entry("9999", "22世紀控股"),
            _entry("2200", "某代號以22開頭的公司"),
        ]
    )

    items, _truncated = store.search("22", limit=12)

    symbols = [item.symbol for item in items]
    assert symbols[0] == "2200"
    assert "9999" in symbols


def test_search_respects_limit_and_reports_truncated(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert([_entry(f"1{i:03d}", f"電子公司{i}") for i in range(20)])

    items, truncated = store.search("電", limit=5)

    assert len(items) == 5
    assert truncated is True


def test_search_on_empty_store_returns_empty_list(tmp_path: Path) -> None:
    store = _store(tmp_path)
    items, truncated = store.search("2330", limit=12)
    assert items == []
    assert truncated is False
    assert store.is_synced() is False
