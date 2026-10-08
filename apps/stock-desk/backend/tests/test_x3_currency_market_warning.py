"""X-3b: the valuator logs a legacy row whose currency does not match its market.

Task X-3 (``work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md``):

* KX-6 -- one WARNING per mismatched id per ``value_all`` pass, on the
  ``app.portfolio.valuation`` logger, reading exactly
  ``position currency does not match market: id=<id> market=<m> currency=<c>``
  and nothing about quantity, cost or note;
* KX-7 -- the judgement is :func:`app.positions.models.currency_matches_market`
  itself, never a second copy of the market -> currency table;
* KX-8 -- the valuation output is unchanged by the check.

The fixtures hold one row of each X-3 direction (US stored as TWD, TW stored
as USD) next to matched rows. Nothing here asserts *what* a mismatched row is
valued at: X-3c (KX-A2) changes that on purpose, and these tests must not be
the thing that pins the X-3 behaviour in place (X3-R8). The KX-8 comparison is
therefore differential -- the same book with and without the branch taken.
"""

from __future__ import annotations

import ast
import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.interface import DataStatus
from app.data.providers.fx import FxRate, FxRateProvider, FxRateResult
from app.portfolio import valuation as valuation_module
from app.portfolio.valuation import PositionValuation, PositionValuator
from app.positions import models as models_module
from app.positions.models import Position, PositionInput
from app.positions.store import PositionStore
from tests.api_helpers import FakePriceService, recent_bars, trending_closes

LOGGER_NAME = "app.portfolio.valuation"
PREFIX = "position currency does not match market:"

#: Values no log line may carry (KX-6): picked so they cannot collide with an id.
SENTINEL_QUANTITY = "1357"
SENTINEL_AVG_COST = "2468"
SENTINEL_NOTE = "X3B-SENTINEL-NOTE"

VALUATION_SOURCE = Path(valuation_module.__file__)


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


def _create(store: PositionStore, symbol: str, market: str, currency: str) -> Position:
    # ``PositionInput`` carries no market/currency rule (ADR-0017 C3), which is
    # what lets a test -- and only a test -- store a legacy mismatched row.
    return store.create(
        PositionInput(
            symbol=symbol,
            market=market,  # type: ignore[arg-type]
            quantity=Decimal(SENTINEL_QUANTITY),
            avg_cost=Decimal(SENTINEL_AVG_COST),
            currency=currency,  # type: ignore[arg-type]
            opened_at=date(2024, 1, 2),
            instrument_type="stock",
            note=SENTINEL_NOTE,
        )
    )


@pytest.fixture
def store(tmp_path: Path) -> PositionStore:
    return PositionStore(db_path=tmp_path / "positions.db")


@pytest.fixture
def valuator() -> PositionValuator:
    tw = FakePriceService()
    us = FakePriceService()
    for symbol in ("2330", "2317"):
        tw.seed(symbol, recent_bars(trending_closes(5, start=600.0), symbol=symbol))
    for symbol in ("AAPL", "MSFT"):
        us.seed(
            symbol,
            recent_bars(trending_closes(5, start=200.0), symbol=symbol, market="US"),
        )
    return PositionValuator(market_services={"TW": tw, "US": us}, fx_provider=_FlatFx())


@pytest.fixture
def mixed_book(store: PositionStore) -> list[Position]:
    """Type A, type B and two matched rows, in id order."""
    _create(store, "AAPL", "US", "TWD")  # type A: US stored as TWD
    _create(store, "2330", "TW", "USD")  # type B: TW stored as USD
    _create(store, "2317", "TW", "TWD")
    _create(store, "MSFT", "US", "USD")
    return store.list_all()


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and record.getMessage().startswith(PREFIX)
    ]


def _by_symbol(positions: list[Position]) -> dict[str, Position]:
    return {position.symbol: position for position in positions}


# --- KX-6 ------------------------------------------------------------------


def test_each_mismatched_row_is_logged_once_per_pass_with_the_pinned_message(
    valuator: PositionValuator,
    mixed_book: list[Position],
    caplog: pytest.LogCaptureFixture,
) -> None:
    rows = _by_symbol(mixed_book)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        valuator.value_all(mixed_book)
    records = _warnings(caplog)
    assert [record.getMessage() for record in records] == [
        f"{PREFIX} id={rows['AAPL'].id} market=US currency=TWD",
        f"{PREFIX} id={rows['2330'].id} market=TW currency=USD",
    ]
    assert all(record.levelno == logging.WARNING for record in records)


def test_a_matched_row_is_never_logged(
    valuator: PositionValuator,
    store: PositionStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _create(store, "2317", "TW", "TWD")
    _create(store, "MSFT", "US", "USD")
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        valuator.value_all(store.list_all())
    assert not any(PREFIX in record.getMessage() for record in caplog.records)


def test_every_pass_logs_again_one_record_per_id(
    valuator: PositionValuator,
    mixed_book: list[Position],
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Each request values the book once; the warning is per pass, so a row
    # that is still wrong keeps showing up in the log until it is corrected.
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        valuator.value_all(mixed_book)
        valuator.value_all(mixed_book)
    messages = [record.getMessage() for record in _warnings(caplog)]
    assert len(messages) == 4
    assert messages[:2] == messages[2:]


def test_the_log_line_carries_no_quantity_cost_or_note(
    valuator: PositionValuator,
    mixed_book: list[Position],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        valuator.value_all(mixed_book)
    records = _warnings(caplog)
    assert records  # not vacuous
    for record in records:
        rendered = record.getMessage()
        for sentinel in (SENTINEL_QUANTITY, SENTINEL_AVG_COST, SENTINEL_NOTE):
            assert sentinel not in rendered
            assert all(sentinel not in str(arg) for arg in (record.args or ()))


# --- KX-7 ------------------------------------------------------------------


def test_the_judgement_is_the_models_function_itself() -> None:
    # Read by name: the valuation module imports it, it does not re-export it.
    shared = vars(valuation_module)["currency_matches_market"]
    assert shared is models_module.currency_matches_market


def test_the_valuator_defers_to_the_shared_rule_for_every_row(
    valuator: PositionValuator,
    mixed_book: list[Position],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A rule that calls *everything* a mismatch makes every row log; a local
    # copy of the table would keep logging only the two real ones.
    asked: list[tuple[str, str]] = []

    def everything_mismatches(market: str, currency: str) -> bool:
        asked.append((market, currency))
        return False

    monkeypatch.setattr(valuation_module, "currency_matches_market", everything_mismatches)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        valuator.value_all(mixed_book)
    assert asked == [(position.market, position.currency) for position in mixed_book]
    assert len(_warnings(caplog)) == len(mixed_book)


def test_the_valuation_module_keeps_no_copy_of_the_market_currency_table() -> None:
    tree = ast.parse(VALUATION_SOURCE.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "MARKET_CURRENCY" not in names | attributes
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = {key.value for key in node.keys if isinstance(key, ast.Constant)}
            assert not keys & {"TW", "US"}, "a market -> currency table belongs in models.py"
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.positions.models"
    ]
    assert any(alias.name == "currency_matches_market" for node in imports for alias in node.names)


# --- KX-8 ------------------------------------------------------------------


def _dump(valuations: list[PositionValuation]) -> list[tuple[str, object, object, object]]:
    return [
        (
            item.valuation.model_dump_json(),
            item.cost_twd,
            item.market_value_twd,
            item.change_basis,
        )
        for item in valuations
    ]


def test_the_check_changes_no_figure_of_any_row(
    valuator: PositionValuator,
    mixed_book: list[Position],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Byte-for-byte the same output whether or not the mismatch branch runs.

    X-3b only: X-3c (KX-A2) changes the mismatched rows' output on purpose,
    and replaces this comparison for them with its own assertions
    (``tests/test_x3c_currency_market_mismatch.py``). Since X-3c the comparison
    therefore covers the matched rows of the same book: the branch taken for
    their neighbours changes nothing about them.
    """
    matched = [
        index
        for index, position in enumerate(mixed_book)
        if models_module.currency_matches_market(position.market, position.currency)
    ]
    assert len(matched) == 2  # not vacuous: 2317 and MSFT
    with_check = _dump(valuator.value_all(mixed_book))
    monkeypatch.setattr(valuation_module, "currency_matches_market", lambda _m, _c: True)
    without_check = _dump(valuator.value_all(mixed_book))
    assert [with_check[i] for i in matched] == [without_check[i] for i in matched]
