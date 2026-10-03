"""Contract tests for the intraday quote schema (ADR-0014 D-1, W1)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.data.interface import (
    DataStatus,
    Quote,
    QuoteBatch,
    QuoteKey,
    QuoteProvider,
    QuoteRejectCode,
    QuoteRejection,
)
from tests.import_graph import imported_modules, module_path

TAIPEI = timezone(timedelta(hours=8))
AS_OF = datetime(2026, 10, 5, 2, 0, 5, tzinfo=UTC)


def _quote(**overrides: Any) -> Quote:
    fields: dict[str, Any] = {
        "symbol": "2330",
        "board": "tse",
        "currency": "TWD",
        "price": Decimal("1050.00"),
        "prev_close": Decimal("1040.00"),
        "limit_up": None,
        "limit_down": None,
        "trade_date": date(2026, 10, 5),
        "quote_time": datetime(2026, 10, 5, 10, 0, 3, tzinfo=TAIPEI),
        "server_time": datetime(2026, 10, 5, 10, 0, 4, tzinfo=TAIPEI),
        "as_of": AS_OF,
        "source": "twse_mis",
    }
    fields.update(overrides)
    return Quote.model_validate(fields)


def test_quote_uses_as_of_not_fetched_at_and_has_no_session_state() -> None:
    fields = set(Quote.model_fields)
    assert "as_of" in fields
    assert "fetched_at" not in fields
    assert "session_state" not in fields
    assert "source" in fields


def test_quote_has_no_field_that_could_be_mistaken_for_a_price() -> None:
    forbidden = {"bid", "ask", "open", "high", "low", "close", "best_bid", "best_ask"}
    assert not forbidden & set(Quote.model_fields)


def test_quote_is_frozen() -> None:
    quote = _quote()
    with pytest.raises(ValidationError):
        quote.price = Decimal("1")


@pytest.mark.parametrize("field", ["as_of", "quote_time", "server_time"])
def test_quote_rejects_naive_datetimes(field: str) -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _quote(**{field: datetime(2026, 10, 5, 10, 0, 0)})


def test_quote_allows_missing_server_time() -> None:
    assert _quote(server_time=None).server_time is None


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-1.5")])
def test_quote_rejects_non_positive_price(price: Decimal) -> None:
    with pytest.raises(ValidationError, match="positive"):
        _quote(price=price)


def test_quote_rejects_blank_symbol_and_source() -> None:
    with pytest.raises(ValidationError, match="blank"):
        _quote(symbol=" ")
    with pytest.raises(ValidationError, match="blank"):
        _quote(source="")


def test_quote_currency_is_twd_only() -> None:
    with pytest.raises(ValidationError):
        _quote(currency="USD")


def test_quote_board_is_tse_or_otc_only() -> None:
    with pytest.raises(ValidationError):
        _quote(board="TW")


def test_quote_key_requires_a_board_and_a_symbol() -> None:
    with pytest.raises(ValidationError):
        QuoteKey.model_validate({"symbol": "2330"})
    with pytest.raises(ValidationError, match="blank"):
        QuoteKey(symbol="  ", board="tse")


def test_quote_key_is_hashable() -> None:
    assert len({QuoteKey(symbol="2330", board="tse"), QuoteKey(symbol="2330", board="tse")}) == 1


def _rejection() -> QuoteRejection:
    return QuoteRejection(
        symbol="2330", board="tse", code=QuoteRejectCode.NO_TRADE, detail="no last trade"
    )


def test_batch_ok_round_trip() -> None:
    batch = QuoteBatch(quotes=(_quote(),), rejections=(), status="ok", as_of=AS_OF, source="m")
    assert batch.reason is None
    assert batch.reject_code is None
    assert batch.as_of == AS_OF


@pytest.mark.parametrize("status", ["failed", "blocked"])
def test_batch_failed_or_blocked_cannot_carry_quotes(status: Any) -> None:
    with pytest.raises(ValidationError, match="must not carry quotes"):
        QuoteBatch(quotes=(_quote(),), rejections=(), status=status, as_of=AS_OF, source="m")


def test_batch_ok_cannot_carry_rejections() -> None:
    with pytest.raises(ValidationError, match="must not carry rejections"):
        QuoteBatch(
            quotes=(_quote(),), rejections=(_rejection(),), status="ok", as_of=AS_OF, source="m"
        )


def test_batch_partial_may_carry_both() -> None:
    batch = QuoteBatch(
        quotes=(_quote(),), rejections=(_rejection(),), status="partial", as_of=AS_OF, source="m"
    )
    assert len(batch.quotes) == 1
    assert len(batch.rejections) == 1


def test_batch_rejects_naive_as_of_and_blank_source() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        QuoteBatch(
            quotes=(), rejections=(), status="failed", as_of=datetime(2026, 10, 5), source="m"
        )
    with pytest.raises(ValidationError, match="blank"):
        QuoteBatch(quotes=(), rejections=(), status="failed", as_of=AS_OF, source=" ")


def test_reject_codes_cover_the_adr_list() -> None:
    expected = {
        # batch level
        "batch_blocked",
        "batch_failed",
        "rtcode_not_ok",
        "server_time_missing",
        "clock_skew",
        "feed_lagging",
        # per symbol
        "symbol_missing",
        "code_mismatch",
        "board_mismatch",
        "duplicate_row",
        "no_trade",
        "price_non_positive",
        "not_today",
        "future_quote_time",
        "outside_price_limits",
        "implausible_move",
        "trial_match",
        # service-layer
        "board_unknown",
        "board_ambiguous",
        "demo_series",
        "source_cooldown",
        "throttled_no_cache",
    }
    assert expected <= {code.value for code in QuoteRejectCode}


def test_data_status_still_has_exactly_four_values() -> None:
    """ADR-0014 I-1: the quote work must not add a DataStatus."""
    assert {s.value for s in DataStatus} == {"fresh", "backup", "cached_stale", "unavailable"}


class _FakeProvider(QuoteProvider):
    source_id = "fake"

    def get_quotes(self, keys: Sequence[QuoteKey]) -> QuoteBatch:
        return QuoteBatch(quotes=(), rejections=(), status="ok", as_of=AS_OF, source=self.source_id)


def test_quote_provider_is_abstract_and_implementable() -> None:
    with pytest.raises(TypeError):
        QuoteProvider()  # type: ignore[abstract]
    batch = _FakeProvider().get_quotes([QuoteKey(symbol="2330", board="tse")])
    assert batch.source == "fake"


def test_quote_modules_stay_away_from_the_bar_cache() -> None:
    """ADR-0014 I-4: quote code must not import the bar cache, panel store or PriceBar."""
    forbidden = ("app.data.cache", "app.data.market_panel", "app.directory")
    for module in ("app.data.quote_quality", "app.data.quote_params", "app.data.intraday_session"):
        path = module_path(module)
        assert path is not None
        imports = imported_modules(path, module)
        assert not [m for m in imports if m.startswith(forbidden)], module
        assert "app.data.interface.PriceBar" not in imports, module
