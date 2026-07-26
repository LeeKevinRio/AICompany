"""The shared FX quote resolver: what it returns, and what it refuses to invent."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.services import fx as F
from tests.api_helpers import UnavailableFxProvider

_AS_OF = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
TARGET = date(2026, 7, 24)


class FakeFxProvider(FxRateProvider):
    """Returns canned rates for the requested window, recording every call."""

    source_id = "fake_fx"

    def __init__(
        self,
        rates: dict[date, str] | None = None,
        *,
        status: DataStatus = DataStatus.FRESH,
        source: str | None = None,
    ) -> None:
        self._rates = dict(rates or {})
        self._status = status
        self._source = source or self.source_id
        self.calls: list[tuple[str, date, date]] = []

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        self.calls.append((pair, start, end))
        rates = [
            FxRate(
                pair=pair,
                date=day,
                rate=Decimal(value),
                as_of=_AS_OF,
                source=self._source,
            )
            for day, value in sorted(self._rates.items())
            if start <= day <= end
        ]
        status = self._status if rates else DataStatus.UNAVAILABLE
        return FxRateResult(rates=rates, status=status, as_of=_AS_OF, source=self._source)


def test_a_twd_instrument_needs_no_quote() -> None:
    provider = FakeFxProvider({TARGET: "31.5"})
    assert F.resolve_fx_quote(provider, currency="TWD", on=TARGET) is None
    assert F.resolve_fx_quote(provider, currency=None, on=TARGET) is None
    # And nothing was fetched to establish that.
    assert provider.calls == []


def test_a_usd_instrument_resolves_to_the_rate_of_that_day() -> None:
    provider = FakeFxProvider({date(2026, 7, 23): "31.0", TARGET: "31.5"})
    quote = F.resolve_fx_quote(provider, currency="usd", on=TARGET)
    assert quote is not None
    assert quote.pair == "USDTWD"
    assert quote.rate == 31.5
    assert quote.as_of == "2026-07-24"
    assert quote.status is DataStatus.FRESH
    assert quote.source == "fake_fx"


def test_the_latest_rate_on_or_before_the_target_is_used_not_a_later_one() -> None:
    provider = FakeFxProvider(
        {date(2026, 7, 22): "30.0", date(2026, 7, 23): "31.0", date(2026, 7, 25): "99.0"}
    )
    quote = F.resolve_fx_quote(provider, currency="USD", on=TARGET)
    assert quote is not None
    # A weekend/holiday gap walks back, never forward: a rate published after
    # the bar being converted did not exist when that bar closed.
    assert quote.rate == 31.0
    assert quote.as_of == "2026-07-23"


def test_the_lookback_window_is_bounded_and_stated() -> None:
    provider = FakeFxProvider({TARGET: "31.5"})
    F.resolve_fx_quote(provider, currency="USD", on=TARGET, backtrack_days=3)
    assert provider.calls == [("USDTWD", date(2026, 7, 21), TARGET)]


def test_an_unavailable_source_yields_a_quote_with_no_rate_not_a_default() -> None:
    quote = F.resolve_fx_quote(UnavailableFxProvider(), currency="USD", on=TARGET)
    assert quote is not None
    assert quote.rate is None
    assert quote.status is DataStatus.UNAVAILABLE
    assert quote.source == "fake_fx_unavailable"
    # The failure still carries its provenance so the caller can explain it.
    assert quote.source_note


def test_a_stale_window_with_nothing_in_range_yields_no_rate() -> None:
    provider = FakeFxProvider({date(2026, 1, 1): "30.0"})
    quote = F.resolve_fx_quote(provider, currency="USD", on=TARGET)
    assert quote is not None
    assert quote.rate is None


def test_no_provider_at_all_is_reported_as_unavailable() -> None:
    quote = F.resolve_fx_quote(None, currency="USD", on=TARGET)
    assert quote is not None
    assert quote.rate is None
    assert quote.source == F.NO_PROVIDER_SOURCE
    assert quote.status is DataStatus.UNAVAILABLE


def test_a_degraded_status_is_passed_through_untouched() -> None:
    provider = FakeFxProvider({TARGET: "31.5"}, status=DataStatus.CACHED_STALE)
    quote = F.resolve_fx_quote(provider, currency="USD", on=TARGET)
    assert quote is not None
    assert quote.status is DataStatus.CACHED_STALE


def test_the_bank_of_taiwan_disclosure_is_the_one_attached_to_its_rates() -> None:
    provider = FakeFxProvider({TARGET: "31.5"}, source="bank_of_taiwan")
    quote = F.resolve_fx_quote(provider, currency="USD", on=TARGET)
    assert quote is not None
    assert "中點" in quote.source_note
    assert "未經本環境線上查證" in quote.source_note
    # An unknown source gets a note that claims nothing about its methodology.
    assert F.source_note("something_else") == F.GENERIC_SOURCE_NOTE
