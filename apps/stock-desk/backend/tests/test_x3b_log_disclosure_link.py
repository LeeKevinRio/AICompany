"""RC-599: the X-3b log line and disclosure (b) come out of one valuation branch.

Risk review
``work/reviews/2026-11-22-X13改判與無法讀取列與殘留iii與關鍵價位文字RC592至RC599-風控.md``
(RC-599, required; RC-581 point 4 raised from suggested). RC-581 point 2 retired
"read the user's local log" in favour of what the screen discloses; that only
holds while the log line and the disclosure are produced by the same branch.
``tests/test_x3_currency_market_warning.py`` pins the log and
``tests/test_x3c_currency_market_mismatch.py`` pins the token and sentence (b),
each on its own fixture, so moving the log or adding an early return could
leave both files green. Here one book is valued **once** and the same pass is
asserted three ways:

* the X-3b WARNING, verbatim (``app/portfolio/valuation.py`` ``value_position``);
* the row's ``missing == [CURRENCY_MARKET_MISMATCH]``;
* sentence (b) (:data:`app.advice.book.CURRENCY_MARKET_MISMATCH_CAUSE`) among
  the book notes built from that same summary.

The frontend's disclosure (a) is pinned on the same token by
``currencyMarketMismatchRow.test.ts``; the token is the link to it (RC-599 2).
The reverse direction: a matched row carries neither the log nor the token.
Every approved sentence is referenced through its constant; none is copied.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

import app.advice.book as book
from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.portfolio import valuation
from app.portfolio.summary import PortfolioSummary, build_summary
from app.portfolio.valuation import PositionValuation, PositionValuator
from app.positions.models import Position, PositionInput
from app.positions.store import PositionStore
from tests.api_helpers import FakePriceService, recent_bars, trending_closes

LOGGER_NAME = "app.portfolio.valuation"
#: The fixed head of the X-3b message; the full line is built per row below.
PREFIX = "position currency does not match market:"

#: The card the book notes are built for: a matched TW holding, so the card
#: itself is valued and only the book-level cause groups carry the mismatch.
CARD_SYMBOL = "2317"
CARD_CLOSE = 600.0


class _FlatFx(FxRateProvider):
    """One flat USDTWD rate dated on the requested window's end."""

    source_id = "bank_of_taiwan"

    def get_daily_rates(self, pair: str, start: date, end: date) -> FxRateResult:
        now = datetime.now(UTC)
        return FxRateResult(
            rates=[FxRate(pair=pair, date=end, rate=Decimal("31.5"), as_of=now, source="bot")],
            status=DataStatus.FRESH,
            as_of=now,
            source=self.source_id,
        )


class _CountingValuator(PositionValuator):
    """Counts ``value_all`` passes, so "the same valuation" is asserted, not assumed."""

    passes = 0

    def value_all(self, positions: Sequence[Position]) -> list[PositionValuation]:
        self.passes += 1
        return super().value_all(positions)


def _valuator() -> _CountingValuator:
    tw = FakePriceService()
    us = FakePriceService()
    for symbol in ("2330", "2317"):
        tw.seed(symbol, recent_bars(trending_closes(5, start=CARD_CLOSE), symbol=symbol))
    for symbol in ("AAPL", "MSFT"):
        us.seed(
            symbol,
            recent_bars(trending_closes(5, start=200.0), symbol=symbol, market="US"),
        )
    return _CountingValuator(market_services={"TW": tw, "US": us}, fx_provider=_FlatFx())


def _create(store: PositionStore, symbol: str, market: str, currency: str) -> Position:
    # ``PositionInput`` carries no market/currency rule (ADR-0017 C3), which is
    # what lets a test -- and only a test -- store a legacy mismatched row.
    return store.create(
        PositionInput(
            symbol=symbol,
            market=market,  # type: ignore[arg-type]
            quantity=Decimal(100),
            avg_cost=Decimal(150),
            currency=currency,  # type: ignore[arg-type]
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            note=None,
        )
    )


def _x3b_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and record.getMessage().startswith(PREFIX)
    ]


def _token() -> str:
    token: str = valuation.CURRENCY_MARKET_MISMATCH
    return token


def _cause_b_prefix(count: int) -> str:
    """Sentence (b) with its count, as it opens its note (``{cause}；{direction}``)."""
    cause: str = book.CURRENCY_MARKET_MISMATCH_CAUSE.format(count=count)
    prefix: str = book.UNVALUED_NOTE_TEMPLATE.format(cause=cause, direction="")
    return prefix


def _cause_b_head() -> str:
    """The fixed text of sentence (b) before its count: present for any count."""
    template: str = book.CURRENCY_MARKET_MISMATCH_CAUSE
    return template.split("{", 1)[0]


def _value_once(
    store: PositionStore, caplog: pytest.LogCaptureFixture, *, level: int
) -> tuple[PortfolioSummary, list[str], _CountingValuator]:
    """One valuation pass under ``caplog``, and the book notes built from it."""
    valuator = _valuator()
    with caplog.at_level(level, logger=LOGGER_NAME):
        summary = build_summary(store, valuator)
        notes = book.book_notes(
            book.build_book_context(
                summary, symbol=CARD_SYMBOL, market="TW", close=CARD_CLOSE, currency="TWD"
            )
        )
    # Building the notes reads the summary; it must not value the book again.
    assert valuator.passes == 1
    return summary, notes, valuator


@pytest.mark.parametrize(
    ("symbol", "market", "currency"),
    [
        pytest.param("AAPL", "US", "TWD", id="type-A"),
        pytest.param("2330", "TW", "USD", id="type-B"),
    ],
)
def test_one_pass_logs_the_row_flags_it_and_discloses_b(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    symbol: str,
    market: str,
    currency: str,
) -> None:
    store = PositionStore(db_path=tmp_path / "positions.db")
    mismatched = _create(store, symbol, market, currency)
    _create(store, CARD_SYMBOL, "TW", "TWD")
    _create(store, "MSFT", "US", "USD")

    summary, notes, _ = _value_once(store, caplog, level=logging.WARNING)

    # 1. The X-3b WARNING, verbatim, once, naming exactly this row.
    records = _x3b_records(caplog)
    assert [record.getMessage() for record in records] == [
        f"{PREFIX} id={mismatched.id} market={market} currency={currency}"
    ]
    assert [record.levelno for record in records] == [logging.WARNING]

    # 2. The same row, in the same pass, carries the token and nothing else.
    rows = {row.id: row for row in summary.positions}
    assert rows[mismatched.id].valuation.missing == [_token()]
    flagged = [row.id for row in summary.positions if _token() in row.valuation.missing]
    assert flagged == [mismatched.id]

    # 3. Sentence (b), counted from that pass, opens exactly one book note.
    stated = [note for note in notes if note.startswith(_cause_b_prefix(len(flagged)))]
    assert len(stated) == 1
    assert sum(_cause_b_head() in note for note in notes) == 1


def test_matched_rows_carry_neither_the_log_nor_the_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = PositionStore(db_path=tmp_path / "positions.db")
    matched = [
        _create(store, CARD_SYMBOL, "TW", "TWD"),
        _create(store, "2330", "TW", "TWD"),
        _create(store, "MSFT", "US", "USD"),
        _create(store, "AAPL", "US", "USD"),
    ]

    # DEBUG, so a demoted copy of the line would be caught too.
    summary, notes, _ = _value_once(store, caplog, level=logging.DEBUG)

    assert not any(PREFIX in record.getMessage() for record in caplog.records)
    assert [row.id for row in summary.positions] == [row.id for row in matched]
    for row in summary.positions:
        assert _token() not in row.valuation.missing
    # Not vacuous: the matched rows were valued, and no note states (b).
    assert all(row.valuation.status == "ok" for row in summary.positions)
    assert not any(_cause_b_head() in note for note in notes)


def test_a_mismatched_neighbour_puts_no_log_or_token_on_a_matched_row(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    store = PositionStore(db_path=tmp_path / "positions.db")
    _create(store, "AAPL", "US", "TWD")
    matched = [_create(store, CARD_SYMBOL, "TW", "TWD"), _create(store, "MSFT", "US", "USD")]

    summary, _, _ = _value_once(store, caplog, level=logging.DEBUG)

    rows = {row.id: row for row in summary.positions}
    messages = [record.getMessage() for record in _x3b_records(caplog)]
    assert len(messages) == 1  # not vacuous: the neighbour was logged
    for position in matched:
        assert all(f"id={position.id} " not in message for message in messages)
        assert _token() not in rows[position.id].valuation.missing
        assert rows[position.id].valuation.status == "ok"
