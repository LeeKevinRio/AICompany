"""Guards on the ETF -> index-code table (ADR-0005 constraints C-1 .. C-6, I-2).

These are not "does the dict parse" tests. Each one pins down a way the table
could rot into producing a plausible-looking but wrong attribution: a key that
matches no fund, a fund with no row, a description that drifted away from the
registry it was copied from, a stated absence with no stated reason, a verified
flag switched on without evidence, or a proxy series slipped in.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.leverage import index_mapping as M
from app.leverage.detect import KNOWN_LEVERAGED_ETF, normalize_symbol

MODULE_PATH = Path(M.__file__)

EXPECTED_UNMAPPED = {"00631L", "00632R", "00680L", "SOXL", "SOXS"}


# --- C-1: pure data, no I/O --------------------------------------------------


def test_module_imports_no_provider_and_no_io() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(name.startswith("app.data.providers") for name in imported)
    # A pure table has no reason to reach for the network, the clock or a file.
    for banned in ("httpx", "sqlite3", "requests", "pathlib", "app.data.cache"):
        assert banned not in imported


def test_the_whole_leverage_package_stays_out_of_the_data_layer() -> None:
    # I-1: ``app/services/index.py`` is the single junction to the data layer.
    # A provider import anywhere in this package would create a second one.
    for path in sorted(MODULE_PATH.parent.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                module = node.names[0].name
            assert not module.startswith("app.data.providers"), (
                f"{path.name} imports a provider; the data-layer junction is "
                "app/services/index.py"
            )


# --- C-2 / C-3: the two tables cover exactly the same funds ------------------


def test_every_mapping_key_is_a_known_leveraged_etf() -> None:
    for symbol in M.INDEX_MAPPING:
        assert symbol in KNOWN_LEVERAGED_ETF, f"{symbol} maps an unknown fund"


def test_every_registry_row_has_a_mapping_row() -> None:
    missing = set(KNOWN_LEVERAGED_ETF) - set(M.INDEX_MAPPING)
    assert not missing, f"registry rows with no index mapping row: {sorted(missing)}"


def test_keys_are_normalized_and_match_their_row() -> None:
    for symbol, ref in M.INDEX_MAPPING.items():
        assert symbol == normalize_symbol(symbol)
        assert ref.etf_symbol == symbol


# --- C-4: drift against the registry's description text ----------------------


def test_underlying_index_text_matches_the_registry_character_for_character() -> None:
    for symbol, ref in M.INDEX_MAPPING.items():
        assert ref.underlying_index_text == KNOWN_LEVERAGED_ETF[symbol].underlying_index, (
            f"{symbol}: the registry's underlying_index text changed; re-check the "
            "index code before updating this snapshot"
        )


# --- C-5: a stated absence states its reason ---------------------------------


def test_phase_7_release_list_is_exactly_twelve_mapped_and_five_unmapped() -> None:
    mapped = {s for s, ref in M.INDEX_MAPPING.items() if ref.basis == "official_index"}
    unmapped = {s for s, ref in M.INDEX_MAPPING.items() if ref.basis == "unmapped"}
    assert len(mapped) == 12
    assert unmapped == EXPECTED_UNMAPPED


@pytest.mark.parametrize("symbol", sorted(EXPECTED_UNMAPPED))
def test_unmapped_rows_say_why_and_refuse_a_proxy(symbol: str) -> None:
    ref = M.INDEX_MAPPING[symbol]
    assert ref.series_symbol is None
    assert ref.return_basis == "unknown"
    # Why it cannot be obtained ...
    assert "取不到" in ref.note or "無法確定可查詢代號" in ref.note
    # ... and why nothing is substituted for it.
    assert "代理" in ref.note
    assert len(ref.note) > 30


def test_unmapped_wording_does_not_read_as_a_temporary_outage() -> None:
    # I-5: these rows describe an established state of the world, not a
    # malfunction the user should retry through.
    for symbol in EXPECTED_UNMAPPED:
        note = M.INDEX_MAPPING[symbol].note
        for phrase in ("暫時", "稍後", "重試", "服務異常", "故障", "維護中"):
            assert phrase not in note, f"{symbol}: {phrase!r} implies a temporary fault"


# --- C-6: verified flags cannot run ahead of the evidence --------------------


def test_no_row_claims_verification_while_the_table_is_unverified() -> None:
    assert M.MAPPING_VERIFIED_ON is None
    for symbol, ref in M.INDEX_MAPPING.items():
        assert ref.verified is False, f"{symbol} claims verified=True"


def test_a_verified_row_must_carry_its_verification_date() -> None:
    for symbol, ref in M.INDEX_MAPPING.items():
        if ref.verified:  # pragma: no cover - none today; the rule outlives that
            assert ref.verified_on is not None, f"{symbol} verified with no date"


# --- I-2: no proxy series, at all --------------------------------------------


def test_no_row_uses_a_proxy_etf_as_its_index_series() -> None:
    offenders = [s for s, ref in M.INDEX_MAPPING.items() if ref.basis == "proxy_etf"]
    assert not offenders, (
        f"proxy_etf rows are not released: {offenders}. Enabling one is a CEO "
        "decision plus a new ADR, not a table edit."
    )


def test_no_tracking_etf_sneaks_in_as_a_series_symbol() -> None:
    # The proxies ADR-0005 names explicitly, in case a row ever claims
    # official_index while pointing at a fund.
    for symbol, ref in M.INDEX_MAPPING.items():
        assert ref.series_symbol not in {"QQQ", "SPY", "0050", "TLT", "SOXX", "SMH"}, symbol
        if ref.series_symbol is not None:
            assert ref.series_symbol.startswith(M.INDEX_SYMBOL_PREFIX), (
                f"{symbol}: an index series code must stay in the '^' namespace "
                "so it can never collide with an equity cache key (I-7)"
            )


# --- Lookup behaviour --------------------------------------------------------


def test_lookup_normalizes_suffix_and_case() -> None:
    assert M.lookup_index_ref("tqqq") is M.INDEX_MAPPING["TQQQ"]
    assert M.lookup_index_ref(" 00675L.TW ") is M.INDEX_MAPPING["00675L"]
    assert M.lookup_index_ref("2330") is None


def test_has_queryable_series_only_accepts_an_official_index() -> None:
    assert M.has_queryable_series(M.INDEX_MAPPING["TQQQ"]) is True
    assert M.has_queryable_series(M.INDEX_MAPPING["SOXL"]) is False
    assert M.has_queryable_series(None) is False
    proxy = M.IndexRef(
        etf_symbol="TQQQ",
        underlying_index_text="NASDAQ-100 Index (3x single-day)",
        basis="proxy_etf",
        series_symbol="QQQ",
        series_market="US",
        return_basis="price",
    )
    assert M.has_queryable_series(proxy) is False


def test_expected_series_codes_of_the_released_rows() -> None:
    assert M.INDEX_MAPPING["00670L"].series_symbol == "^NDX"
    assert M.INDEX_MAPPING["SSO"].series_symbol == "^GSPC"
    assert M.INDEX_MAPPING["SSO"].return_basis == "price"
    assert M.INDEX_MAPPING["00675L"].series_symbol == "^TWII"
    assert M.INDEX_MAPPING["00675L"].series_market == "TW"
    # A Taiwan-listed fund on a US benchmark sources its series from the US.
    assert M.INDEX_MAPPING["00670L"].series_market == "US"
