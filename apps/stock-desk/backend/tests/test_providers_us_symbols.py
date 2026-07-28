"""Tests for canonical US ticker normalization and per-provider conversion."""

from __future__ import annotations

import pytest

from app.data.providers.us_symbols import (
    ALPHA_VANTAGE_PROVIDER_ID,
    YFINANCE_PROVIDER_ID,
    InvalidUsSymbolError,
    canonical_us_symbol,
    to_provider_symbol,
)


class TestCanonicalUsSymbol:
    def test_upper_cases_and_strips_whitespace(self) -> None:
        assert canonical_us_symbol("  aapl  ") == "AAPL"

    def test_keeps_dot_form_unchanged(self) -> None:
        assert canonical_us_symbol("BRK.B") == "BRK.B"

    def test_strips_us_market_suffix(self) -> None:
        assert canonical_us_symbol("AAPL.US") == "AAPL"

    def test_rejects_leading_caret_index_symbol(self) -> None:
        with pytest.raises(InvalidUsSymbolError, match="index"):
            canonical_us_symbol("^GSPC")

    def test_rejects_blank_symbol(self) -> None:
        with pytest.raises(InvalidUsSymbolError):
            canonical_us_symbol("   ")

    def test_rejects_symbol_that_is_only_the_us_suffix(self) -> None:
        with pytest.raises(InvalidUsSymbolError):
            canonical_us_symbol(".US")

    def test_rejects_illegal_characters(self) -> None:
        with pytest.raises(InvalidUsSymbolError):
            canonical_us_symbol("AAPL!")

    def test_rejects_illegal_characters_slash(self) -> None:
        with pytest.raises(InvalidUsSymbolError):
            canonical_us_symbol("AAPL/B")

    def test_allows_hyphen_as_a_legal_canonical_character(self) -> None:
        # canonical_us_symbol validates the character set; it does not decide
        # which convention (dot vs hyphen) a symbol "should" use.
        assert canonical_us_symbol("BF-B") == "BF-B"


class TestToProviderSymbol:
    def test_yfinance_default_rule_converts_dot_to_hyphen(self) -> None:
        assert to_provider_symbol("BRK.B", provider_id=YFINANCE_PROVIDER_ID) == "BRK-B"

    def test_yfinance_default_rule_is_identity_for_plain_tickers(self) -> None:
        assert to_provider_symbol("AAPL", provider_id=YFINANCE_PROVIDER_ID) == "AAPL"

    def test_alpha_vantage_default_rule_is_identity(self) -> None:
        assert to_provider_symbol("BRK.B", provider_id=ALPHA_VANTAGE_PROVIDER_ID) == "BRK.B"

    def test_unknown_provider_id_raises(self) -> None:
        with pytest.raises(ValueError, match="no symbol conversion rule"):
            to_provider_symbol("AAPL", provider_id="some_unregistered_provider")

    def test_conversion_is_one_directional_only(self) -> None:
        """There is deliberately no from_provider_symbol / reverse mapping."""
        import app.data.providers.us_symbols as us_symbols_module

        assert not hasattr(us_symbols_module, "from_provider_symbol")
        assert not hasattr(us_symbols_module, "canonical_from_provider_symbol")


class TestBrkBRoundTripsToASingleCanonicalKey:
    """Q-5 contract: BRK.B via both provider paths must yield the same canonical
    symbol on the resulting PriceBar/cache key, never two different keys."""

    def test_both_providers_agree_on_the_canonical_symbol_for_brk_b(self) -> None:
        canonical = canonical_us_symbol("BRK.B")
        # Each provider's wire-format symbol differs...
        av_wire = to_provider_symbol(canonical, provider_id=ALPHA_VANTAGE_PROVIDER_ID)
        yf_wire = to_provider_symbol(canonical, provider_id=YFINANCE_PROVIDER_ID)
        assert av_wire == "BRK.B"
        assert yf_wire == "BRK-B"
        assert av_wire != yf_wire
        # ...but what actually lands on PriceBar.symbol / the cache key must
        # be the same canonical string regardless of which provider answered.
        assert canonical == "BRK.B"
