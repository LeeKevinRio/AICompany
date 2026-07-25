"""Detection and metadata-registry behaviour."""

from __future__ import annotations

from app.leverage import detect as D
from tests.leverage_helpers import make_position


def test_registry_entries_are_all_flagged_unverified() -> None:
    # The whole point of the provenance convention: no row may claim to be
    # verified until data-engineer checks it against the issuer document.
    assert D.KNOWN_LEVERAGED_ETF
    assert D.REGISTRY_VERIFIED_ON is None
    for symbol, metadata in D.KNOWN_LEVERAGED_ETF.items():
        assert metadata.symbol == symbol
        assert metadata.verified is False
        assert metadata.verified_on is None
        assert "verified=false" in metadata.source_note
        assert metadata.leverage_factor != 0.0
        assert 0.0 < metadata.expense_ratio_annual < 0.05
        assert metadata.underlying_index.strip()


def test_known_tw_and_us_cases_present() -> None:
    assert D.KNOWN_LEVERAGED_ETF["00631L"].leverage_factor == 2.0
    assert D.KNOWN_LEVERAGED_ETF["00632R"].leverage_factor == -1.0
    assert D.KNOWN_LEVERAGED_ETF["TQQQ"].leverage_factor == 3.0
    assert D.KNOWN_LEVERAGED_ETF["SQQQ"].leverage_factor == -3.0


def test_normalize_symbol_strips_market_suffix_and_case() -> None:
    assert D.normalize_symbol(" 00631l.tw ") == "00631L"
    assert D.normalize_symbol("tqqq") == "TQQQ"
    assert D.normalize_symbol("2330.TWO") == "2330"
    assert D.normalize_symbol("SOXL.US") == "SOXL"


def test_lookup_metadata_hit_and_miss() -> None:
    found = D.lookup_metadata("00631L.TW")
    assert found is not None
    assert found.leverage_factor == 2.0
    assert D.lookup_metadata("2330") is None


def test_detect_known_leveraged_position_is_ok() -> None:
    result = D.detect(make_position(symbol="00631L", instrument_type="leveraged_etf"))
    assert result.status == "ok"
    assert result.is_daily_reset_leveraged is True
    assert result.leverage_factor == 2.0
    assert result.expense_ratio_annual is not None
    assert result.metadata_verified is False
    assert result.classification_mismatch is False
    assert result.reason is None
    # Unverified metadata must announce itself, not hide in a boolean.
    assert any("verified=false" in note for note in result.notes)


def test_detect_declared_leveraged_without_metadata_is_insufficient() -> None:
    result = D.detect(make_position(symbol="00999X", instrument_type="leveraged_etf"))
    assert result.status == "insufficient_data"
    assert result.is_daily_reset_leveraged is True
    assert result.leverage_factor is None
    assert result.expense_ratio_annual is None
    assert result.reason is not None


def test_detect_plain_stock_is_not_applicable() -> None:
    result = D.detect(make_position(symbol="2330", instrument_type="stock"))
    assert result.status == "not_applicable"
    assert result.is_daily_reset_leveraged is False
    assert result.leverage_factor is None
    assert result.reason is not None


def test_futures_etf_alone_is_not_treated_as_daily_reset() -> None:
    # Roll mechanics are not a daily leverage reset; conflating them would
    # attribute the wrong cause to the wrong number.
    result = D.detect(make_position(symbol="00642U", instrument_type="futures_etf"))
    assert result.status == "not_applicable"
    assert result.is_daily_reset_leveraged is False


def test_registry_hit_with_other_instrument_type_reports_both_facts() -> None:
    result = D.detect(make_position(symbol="TQQQ", instrument_type="etf", market="US"))
    assert result.status == "ok"
    assert result.classification_mismatch is True
    assert result.leverage_factor == 3.0
    assert any("instrument_type" in note for note in result.notes)


def test_detect_symbol_core_matches_position_level() -> None:
    assert D.detect_symbol("00632R", "leveraged_etf").leverage_factor == -1.0
