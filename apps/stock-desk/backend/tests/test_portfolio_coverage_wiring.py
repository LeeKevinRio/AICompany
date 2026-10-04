"""ADR-0016 D-5 wiring of the summary endpoint (K-17, K-21, D-5.4, D-5.5, T-15).

``GET /api/portfolio/summary`` is the one place the real D-5 coverage rule
(``AnnounceRunCoverageRule``) goes into the change screen, and it reads the same
main-DB ``DividendEventStore`` that F6 reads its ex-dates from (D-5.4). Under
``SHOW_WHEN_COVERAGE_UNKNOWN`` the verdict never changes the response (D-5.5),
so the wiring is observed through the store's reads and the screen's debug log.

The static checks (K-17 construction site, K-21 constants) are AST scans of
``app/``, so a docstring or a comment cannot trip them.
"""

from __future__ import annotations

import ast
import logging
import sqlite3
from collections.abc import Collection, Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.api.portfolio as portfolio_api
from app.api import deps
from app.api.deps import (
    get_dividend_store,
    get_position_store,
    get_price_bar_cache,
    get_valuator,
)
from app.data.cache import PriceBarCache
from app.data.interface import DividendAnnounceObservation, Market, PriceBar
from app.dividends.coverage import MIN_ANNOUNCE_LEAD_DAYS, AnnounceRunCoverageRule
from app.dividends.models import DividendEvent
from app.dividends.store import DividendEventStore
from app.main import app
from app.portfolio.price_change import SHOW_WHEN_COVERAGE_UNKNOWN, ChangeScreen
from app.portfolio.summary import PortfolioSummary, build_summary
from app.portfolio.valuation import PositionValuator
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from tests.api_helpers import FakePriceService, UnavailableFxProvider
from tests.import_graph import APP_ROOT

NOW = datetime(2026, 10, 5, 7, 0, tzinfo=UTC)  # Monday
WED = date(2026, 9, 30)
THU = date(2026, 10, 1)
FRI = date(2026, 10, 2)
MON = date(2026, 10, 5)

#: 21:30 Asia/Taipei: a run whose Taipei date is that weekday.
THU_EVENING = datetime(2026, 10, 1, 13, 30, tzinfo=UTC)
FRI_EVENING = datetime(2026, 10, 2, 13, 30, tzinfo=UTC)

_SCREEN_LOGGER = "app.portfolio.price_change"
_COVERAGE_LOGGER = "app.dividends.coverage"
_UNKNOWN_LINE = "price change shown with unknown ex-date coverage"

#: 2330 Fri -> Mon, as the summary shows it; 2317 is withheld by F6 (ex-date Monday).
_BASELINE_CHANGES: dict[str, Any] = {
    "2330": {
        "pct": "1.2360",
        "basis_kind": "close",
        "basis_date": "2026-10-02",
        "basis_price": "1072.00",
    },
    "2317": None,
}


def _bars(symbol: str, closes: list[tuple[date, str]]) -> list[PriceBar]:
    return [
        PriceBar(
            symbol=symbol,
            market="TW",
            date=day,
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=1,
            currency="TWD",
            as_of=NOW,
            source="twse",
        )
        for day, close in closes
    ]


class RecordingDividendStore(DividendEventStore):
    """The real main-DB store, recording which instance answered which read."""

    def __init__(self, db_path: Path) -> None:
        super().__init__(db_path)
        self.reads: list[tuple[str, int]] = []

    def ex_dates_between(
        self, keys: Collection[tuple[str, Market]], start: date, end: date
    ) -> dict[tuple[str, Market], frozenset[date]]:
        self.reads.append(("ex_dates_between", id(self)))
        return super().ex_dates_between(keys, start, end)

    def dividend_announce_observations(
        self, symbols: Collection[str], recorded_not_before: date
    ) -> list[DividendAnnounceObservation]:
        self.reads.append(("dividend_announce_observations", id(self)))
        return super().dividend_announce_observations(symbols, recorded_not_before)


class FailingRunLogStore(DividendEventStore):
    """A main-DB store whose sync-record read raises; its ex-date read (F6) still works."""

    def __init__(self, db_path: Path, error: BaseException) -> None:
        super().__init__(db_path)
        self.error = error

    def dividend_announce_observations(
        self, symbols: Collection[str], recorded_not_before: date
    ) -> list[DividendAnnounceObservation]:
        raise self.error


@dataclass
class Desk:
    prices: FakePriceService
    positions: PositionStore
    bar_cache: PriceBarCache
    dividends: DividendEventStore

    def valuator(self) -> PositionValuator:
        return PositionValuator(
            market_services={"TW": self.prices, "US": self.prices},
            fx_provider=UnavailableFxProvider(),
            clock=lambda: NOW,
        )


def _hold(positions: PositionStore, symbol: str) -> None:
    positions.create(
        PositionInput(
            symbol=symbol,
            market="TW",
            quantity=Decimal("1000"),
            avg_cost=Decimal("500"),
            currency="TWD",
            opened_at=date(2026, 1, 5),
            instrument_type="stock",
            note=None,
        ),
        now=NOW,
    )


def _seed(
    prices: FakePriceService, bar_cache: PriceBarCache, dividends: DividendEventStore
) -> None:
    """2330 Thu/Fri/Mon (no ex-date), 2317 Fri/Mon with an ex-date on Monday (F6)."""
    prices.seed("2330", _bars("2330", [(THU, "1060.00"), (FRI, "1072.00"), (MON, "1085.25")]))
    prices.seed("2317", _bars("2317", [(FRI, "200.0"), (MON, "190.0")]))
    # The market calendar the cache has observed: Wed through Mon, no gap.
    bar_cache.put(_bars("2330", [(WED, "1"), (THU, "1"), (FRI, "1"), (MON, "1")]), source="twse")
    dividends.upsert(
        [
            DividendEvent(
                symbol="2317",
                market="TW",
                ex_date=MON,
                cash_dividend=Decimal("5.2"),
                source="twse_twt48u",
                as_of=NOW,
            )
        ]
    )


def _record_ok_run(db_path: Path, recorded_at: datetime, *, unparsed: Sequence[str] = ()) -> None:
    """One ok CLI sync run stamped ``recorded_at`` by the store clock."""
    writer = DividendEventStore(db_path, clock=lambda: recorded_at)
    writer.record_sync(
        trigger="cli",
        source="twse_twt48u",
        adapter_ok=True,
        reason=None,
        events=[
            DividendEvent(
                symbol="1101",
                market="TW",
                ex_date=date(2026, 11, 20),
                cash_dividend=Decimal("1"),
                source="twse_twt48u",
                as_of=recorded_at,
            )
        ],
        unparsed_symbols=unparsed,
    )


def _make_desk(tmp_path: Path, dividends: DividendEventStore) -> Desk:
    positions = PositionStore(db_path=tmp_path / "positions.db")
    desk = Desk(
        prices=FakePriceService(source="twse"),
        positions=positions,
        # Calendar and 除權息 store share one main-DB file, as in production.
        bar_cache=PriceBarCache(db_path=dividends.db_path),
        dividends=dividends,
    )
    _seed(desk.prices, desk.bar_cache, desk.dividends)
    _hold(positions, "2330")
    _hold(positions, "2317")
    return desk


@pytest.fixture
def desk(tmp_path: Path) -> Desk:
    return _make_desk(tmp_path, RecordingDividendStore(tmp_path / "main.db"))


@contextmanager
def _serving(desk: Desk) -> Iterator[TestClient]:
    app.dependency_overrides[get_position_store] = lambda: desk.positions
    app.dependency_overrides[get_valuator] = desk.valuator
    app.dependency_overrides[get_dividend_store] = lambda: desk.dividends
    app.dependency_overrides[get_price_bar_cache] = lambda: desk.bar_cache
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def screens(monkeypatch: pytest.MonkeyPatch) -> list[ChangeScreen | None]:
    """Every ``change_screen`` the portfolio API hands to ``build_summary``."""
    captured: list[ChangeScreen | None] = []
    real = build_summary

    def spy(*args: Any, **kwargs: Any) -> PortfolioSummary:
        captured.append(kwargs.get("change_screen"))
        return real(*args, **kwargs)

    monkeypatch.setattr(portfolio_api, "build_summary", spy)
    return captured


def _get_summary(desk: Desk) -> dict[str, Any]:
    with _serving(desk) as client:
        response = client.get("/api/portfolio/summary")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def _changes(body: dict[str, Any]) -> dict[str, Any]:
    return {row["symbol"]: row["change"] for row in body["positions"]}


def _without_clock(body: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key != "as_of"}


def _unknown_coverage_symbols(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Symbols the screen showed with ``unknown`` coverage (its DEBUG line)."""
    return [
        str(record.args[1])
        for record in caplog.records
        if record.name == _SCREEN_LOGGER
        and _UNKNOWN_LINE in record.getMessage()
        and isinstance(record.args, tuple)
    ]


# --- AST helpers -----------------------------------------------------------------


def _app_sources() -> list[tuple[str, ast.Module]]:
    return [
        (path.relative_to(APP_ROOT.parent).as_posix(), ast.parse(path.read_text(encoding="utf-8")))
        for path in sorted(APP_ROOT.rglob("*.py"))
    ]


def _callee(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _calls_by_function(tree: ast.Module) -> list[tuple[str, ast.Call]]:
    """Every call with the name of its innermost enclosing function (``<module>`` if none)."""
    owner: dict[int, str] = {}
    calls: dict[int, ast.Call] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            calls[id(node)] = node
            owner.setdefault(id(node), "<module>")
    # ast.walk is breadth-first, so an inner function is visited after its outer one
    # and overwrites the owner of the calls it holds.
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call):
                    owner[id(inner)] = node.name
    return [(owner[key], call) for key, call in calls.items()]


# --- K-17: the one construction site ---------------------------------------------


def test_k17_summary_endpoint_injects_the_announce_run_rule(
    desk: Desk, screens: list[ChangeScreen | None]
) -> None:
    body = _get_summary(desk)
    assert _changes(body) == _BASELINE_CHANGES
    assert len(screens) == 1
    screen = screens[0]
    assert isinstance(screen, ChangeScreen)
    assert isinstance(screen.coverage_rule, AnnounceRunCoverageRule)
    assert screen.ex_dates is desk.dividends
    assert screen.calendar is desk.bar_cache


def test_k17_only_app_api_portfolio_constructs_the_rule() -> None:
    constructed: list[tuple[str, str]] = []
    importers: set[str] = set()
    for path, tree in _app_sources():
        for function, call in _calls_by_function(tree):
            if _callee(call) == "AnnounceRunCoverageRule":
                constructed.append((path, function))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                names = {alias.name for alias in node.names}
                if node.module == "app.dividends.coverage" or (
                    node.module == "app.dividends" and "coverage" in names
                ):
                    importers.add(path)
            elif isinstance(node, ast.Import):
                if any(alias.name == "app.dividends.coverage" for alias in node.names):
                    importers.add(path)
    assert constructed == [("app/api/portfolio.py", "portfolio_summary")]
    assert importers == {"app/api/portfolio.py"}


def test_k17_no_other_build_summary_caller_screens() -> None:
    """D-3/K-17: only ``portfolio_summary`` passes a screen; it alone builds one."""
    screening: list[tuple[str, str]] = []
    unscreened: list[tuple[str, str]] = []
    screens_built: list[tuple[str, str]] = []
    for path, tree in _app_sources():
        for function, call in _calls_by_function(tree):
            name = _callee(call)
            if name == "build_summary":
                keywords = {keyword.arg for keyword in call.keywords}
                target = screening if "change_screen" in keywords else unscreened
                target.append((path, function))
            elif name == "ChangeScreen":
                screens_built.append((path, function))
    assert screening == [("app/api/portfolio.py", "portfolio_summary")]
    assert screens_built == [("app/api/portfolio.py", "portfolio_summary")]
    # The four callers ADR-0016 D-3 names; a new one must be looked at, not slip in.
    assert sorted(path for path, _ in unscreened) == [
        "app/alerts/snapshot.py",
        "app/api/advice.py",
        "app/api/portfolio.py",
        "app/api/settings.py",
    ]


# --- D-5.4: F6 and the coverage rule read one main DB ------------------------------


def test_f6_and_coverage_read_the_same_store_instance(desk: Desk) -> None:
    store = desk.dividends
    assert isinstance(store, RecordingDividendStore)
    _get_summary(desk)
    assert store.reads == [
        ("ex_dates_between", id(store)),
        ("dividend_announce_observations", id(store)),
    ]


def test_screen_wiring_passes_one_store_to_both_lookups() -> None:
    """Statically: ``ex_dates=`` and the rule's source are the same dependency."""
    tree = ast.parse((APP_ROOT / "api" / "portfolio.py").read_text(encoding="utf-8"))
    screens = [
        call
        for function, call in _calls_by_function(tree)
        if function == "portfolio_summary" and _callee(call) == "ChangeScreen"
    ]
    assert len(screens) == 1
    keywords = {keyword.arg: keyword.value for keyword in screens[0].keywords}
    ex_dates = keywords["ex_dates"]
    rule = keywords["coverage_rule"]
    assert isinstance(ex_dates, ast.Name)
    assert isinstance(rule, ast.Call) and _callee(rule) == "AnnounceRunCoverageRule"
    assert len(rule.args) == 1 and not rule.keywords
    assert isinstance(rule.args[0], ast.Name)
    assert rule.args[0].id == ex_dates.id == "dividends"


@pytest.fixture
def production_main_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the production providers at temp files; never at ``backend/data``."""
    main_db = tmp_path / "main" / "stock-desk.db"
    monkeypatch.setenv("STOCK_DESK_DB_PATH", str(main_db))
    monkeypatch.setenv("STOCK_DESK_MARKET_DB_PATH", str(tmp_path / "market" / "market.db"))
    deps._default_dividend_store.cache_clear()
    deps._default_cache.cache_clear()
    try:
        yield main_db
    finally:
        deps._default_dividend_store.cache_clear()
        deps._default_cache.cache_clear()


def test_production_store_is_the_main_db(production_main_db: Path) -> None:
    dividends = get_dividend_store()
    assert dividends is get_dividend_store()
    assert dividends.db_path == production_main_db
    # The calendar the screen reads lives in the same main DB, never the market DB.
    assert get_price_bar_cache().db_path == production_main_db
    assert not (production_main_db.parent.parent / "market" / "market.db").exists()


def test_production_wiring_proves_coverage_from_the_main_db(
    tmp_path: Path, production_main_db: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """End to end through the real providers: a main-DB run makes a row ``known``."""
    prices = FakePriceService(source="twse")
    positions = PositionStore(db_path=tmp_path / "positions.db")
    _seed(prices, get_price_bar_cache(), get_dividend_store())
    # Thu -> Fri: a Thursday-evening run is a valid anchor under the default lead.
    prices.seed("2330", _bars("2330", [(THU, "1060.00"), (FRI, "1072.00")]))
    _hold(positions, "2330")
    _record_ok_run(production_main_db, THU_EVENING)
    desk = Desk(
        prices=prices,
        positions=positions,
        bar_cache=get_price_bar_cache(),
        dividends=get_dividend_store(),
    )

    app.dependency_overrides[get_position_store] = lambda: positions
    app.dependency_overrides[get_valuator] = desk.valuator
    try:
        with (
            caplog.at_level(logging.DEBUG, logger=_SCREEN_LOGGER),
            TestClient(app) as client,
        ):
            response = client.get("/api/portfolio/summary")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert _changes(response.json())["2330"] is not None
    assert _unknown_coverage_symbols(caplog) == []


# --- D-5.4 / D-5.5: before the schedule, mostly unknown; never a different body ----------


def test_d54_without_runs_coverage_is_unknown_and_the_body_matches_the_stub(
    desk: Desk, caplog: pytest.LogCaptureFixture
) -> None:
    """No (or only stale) sync runs: every row is ``unknown``, as with the stub."""
    with caplog.at_level(logging.DEBUG, logger=_SCREEN_LOGGER):
        wired = _get_summary(desk)
    assert _unknown_coverage_symbols(caplog) == ["2330"]

    # A Friday-evening CLI run cannot prove Fri -> Mon under the default lead of 1.
    _record_ok_run(desk.dividends.db_path, FRI_EVENING)
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=_SCREEN_LOGGER):
        with_cli_run = _get_summary(desk)
    assert _unknown_coverage_symbols(caplog) == ["2330"]

    stub = build_summary(
        desk.positions,
        desk.valuator(),
        change_screen=ChangeScreen(ex_dates=desk.dividends, calendar=desk.bar_cache),
    ).model_dump(mode="json")
    assert _without_clock(wired) == _without_clock(stub)
    assert _without_clock(with_cli_run) == _without_clock(stub)
    assert _changes(wired) == _BASELINE_CHANGES


def test_d55_a_known_verdict_does_not_change_the_response(
    desk: Desk, caplog: pytest.LogCaptureFixture
) -> None:
    desk.prices.seed("2330", _bars("2330", [(THU, "1060.00"), (FRI, "1072.00")]))
    with caplog.at_level(logging.DEBUG, logger=_SCREEN_LOGGER):
        unknown = _get_summary(desk)
    assert _unknown_coverage_symbols(caplog) == ["2330"]

    _record_ok_run(desk.dividends.db_path, THU_EVENING)
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=_SCREEN_LOGGER):
        known = _get_summary(desk)
    assert _unknown_coverage_symbols(caplog) == []

    assert _without_clock(known) == _without_clock(unknown)
    assert _changes(known)["2330"] == {
        "pct": "1.1321",
        "basis_kind": "close",
        "basis_date": "2026-10-01",
        "basis_price": "1060.00",
    }


# --- T-15: failures of the coverage read -------------------------------------------


def test_t15_constants_are_pinned() -> None:
    # Also pinned at their governance points (ADR-0016 D-5 / D-5.6), in
    # tests/test_price_change.py (test_unknown_coverage_still_shows_the_change)
    # and tests/test_dividends_coverage.py
    # (test_monday_after_a_friday_anchor_is_unknown_under_the_default_lead).
    assert MIN_ANNOUNCE_LEAD_DAYS == 1
    assert SHOW_WHEN_COVERAGE_UNKNOWN is True


def test_t15_missing_sync_tables_answer_200_and_show_the_change(
    desk: Desk, caplog: pytest.LogCaptureFixture
) -> None:
    with closing(sqlite3.connect(desk.dividends.db_path)) as conn, conn:
        conn.execute("DROP TABLE dividend_sync_unparsed")
        conn.execute("DROP TABLE dividend_sync_runs")
    with caplog.at_level(logging.DEBUG):
        body = _get_summary(desk)
    assert body["change_mode"] == "close_only"
    assert _changes(body) == _BASELINE_CHANGES
    assert _unknown_coverage_symbols(caplog) == ["2330"]
    # A missing table is "no run", not a read failure.
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def _assert_one_clean_warning(caplog: pytest.LogCaptureFixture) -> None:
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert [(r.name, r.levelno) for r in warnings] == [(_COVERAGE_LOGGER, logging.WARNING)]
    message = warnings[0].getMessage().lower()
    for leaked in ("://", "http", "token", "key", "secret"):
        assert leaked not in message


@pytest.mark.parametrize(
    "error",
    [
        sqlite3.OperationalError("disk I/O error"),
        sqlite3.DatabaseError("database disk image is malformed"),
        OSError("read failed"),
        ValueError("Invalid isoformat string"),
    ],
    ids=["operational", "database", "os", "value"],
)
def test_t15_unreadable_run_log_reads_as_unknown_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    desk = _make_desk(tmp_path, FailingRunLogStore(tmp_path / "main.db", error))
    with caplog.at_level(logging.DEBUG):
        body = _get_summary(desk)
    assert body["change_mode"] == "close_only"
    assert _changes(body) == _BASELINE_CHANGES
    assert _unknown_coverage_symbols(caplog) == ["2330"]
    _assert_one_clean_warning(caplog)


def test_t15_corrupt_timestamp_in_the_real_table_reads_as_unknown(
    desk: Desk, caplog: pytest.LogCaptureFixture
) -> None:
    # Inside the read window (on/after price_date - lead - 1 day) so it is read.
    with closing(sqlite3.connect(desk.dividends.db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO dividend_sync_runs (recorded_at, trigger, source, status, "
            "event_count, unparsed_count, unattributed_count, reason) "
            "VALUES ('2026-10-04Tnot-a-time', 'cli', 'twse_twt48u', 'ok', 1, 0, 0, NULL)"
        )
    with caplog.at_level(logging.DEBUG):
        body = _get_summary(desk)
    assert _changes(body) == _BASELINE_CHANGES
    assert _unknown_coverage_symbols(caplog) == ["2330"]
    _assert_one_clean_warning(caplog)


@pytest.mark.allow_price_change_error
def test_t15_unexpected_error_is_not_turned_into_unknown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Only the ADR's read errors become ``unknown``; anything else is D-3's fail-closed."""
    desk = _make_desk(tmp_path, FailingRunLogStore(tmp_path / "main.db", RuntimeError("bug")))
    with caplog.at_level(logging.DEBUG):
        body = _get_summary(desk)
    assert body["change_mode"] == "close_only"
    assert _changes(body) == {"2330": None, "2317": None}
    assert body["totals"] is not None
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert [r.name for r in errors] == [_SCREEN_LOGGER]
    assert errors[0].exc_info is not None and errors[0].exc_info[0] is RuntimeError
    assert not [r for r in caplog.records if r.name == _COVERAGE_LOGGER]
    assert "bug" not in str(body)


# --- K-21: the two constants take no runtime input ------------------------------------

_CONSTANTS = {
    "MIN_ANNOUNCE_LEAD_DAYS": ("app/dividends/coverage.py", 1),
    "SHOW_WHEN_COVERAGE_UNKNOWN": ("app/portfolio/price_change.py", True),
}
_LEAD_PARAMETER = "min_announce_lead_days"
_CONFIG_NAMES = ("environ", "getenv", "dotenv", "settings")
_CONFIG_MODULES = ("os", "dotenv", "app.settings")


def _is_config_read(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return any(word in node.id.lower() for word in _CONFIG_NAMES)
    if isinstance(node, ast.Attribute):
        return any(word in node.attr.lower() for word in _CONFIG_NAMES)
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0] in {"os", "dotenv"} for alias in node.names) or any(
            alias.name.startswith("app.settings") for alias in node.names
        )
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return module in _CONFIG_MODULES or module.startswith(("app.settings", "dotenv"))
    return False


def _mentions_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id in _CONSTANTS or node.id == _LEAD_PARAMETER
    if isinstance(node, ast.Attribute):
        return node.attr in _CONSTANTS
    if isinstance(node, ast.arg):
        return node.arg == _LEAD_PARAMETER
    if isinstance(node, ast.keyword):
        return node.arg == _LEAD_PARAMETER
    if isinstance(node, ast.alias):
        return node.name in _CONSTANTS
    return False


def _scopes(tree: ast.Module) -> list[tuple[str, list[ast.AST]]]:
    """Each function (with its signature) and the module level, as flat node lists."""
    scopes: list[tuple[str, list[ast.AST]]] = []
    module_nodes: list[ast.AST] = []
    for statement in tree.body:
        if not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            module_nodes.extend(ast.walk(statement))
    scopes.append(("<module>", module_nodes))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            scopes.append((node.name, list(ast.walk(node))))
        elif isinstance(node, ast.ClassDef):
            body = [
                inner
                for statement in node.body
                if not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef)
                for inner in ast.walk(statement)
            ]
            scopes.append((node.name, body))
    return scopes


def test_k21_constants_are_final_literals_assigned_once() -> None:
    definitions: dict[str, list[tuple[str, ast.AST]]] = {name: [] for name in _CONSTANTS}
    for path, tree in _app_sources():
        for node in ast.walk(tree):
            targets: list[ast.AST] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign | ast.AugAssign):
                targets = [node.target]
            for target in targets:
                for inner in ast.walk(target):
                    name = inner.id if isinstance(inner, ast.Name) else None
                    if isinstance(inner, ast.Attribute):
                        name = inner.attr
                    if name in definitions:
                        definitions[name].append((path, node))
            # setattr(module, "NAME", ...) would be a runtime override too.
            if isinstance(node, ast.Call) and _callee(node) == "setattr":
                literals = [arg.value for arg in node.args if isinstance(arg, ast.Constant)]
                assert not set(literals) & set(_CONSTANTS), path
    for name, (expected_path, expected_value) in _CONSTANTS.items():
        assert len(definitions[name]) == 1, (name, definitions[name])
        path, node = definitions[name][0]
        assert path == expected_path
        assert isinstance(node, ast.AnnAssign)
        annotation = node.annotation
        assert (isinstance(annotation, ast.Name) and annotation.id == "Final") or (
            isinstance(annotation, ast.Attribute) and annotation.attr == "Final"
        )
        assert isinstance(node.value, ast.Constant)
        assert node.value.value is expected_value or (
            type(node.value.value) is type(expected_value) and node.value.value == expected_value
        )


def test_k21_no_environment_or_settings_read_shares_a_scope_with_the_constants() -> None:
    offenders: list[tuple[str, str]] = []
    for path, tree in _app_sources():
        for scope, nodes in _scopes(tree):
            if any(_mentions_constant(node) for node in nodes) and any(
                _is_config_read(node) for node in nodes
            ):
                offenders.append((path, scope))
    assert offenders == []


def test_k21_defining_modules_read_no_environment_or_settings() -> None:
    for path, _ in _CONSTANTS.values():
        tree = ast.parse((APP_ROOT.parent / path).read_text(encoding="utf-8"))
        assert [ast.dump(node) for node in ast.walk(tree) if _is_config_read(node)] == [], path


def test_k21_no_caller_overrides_the_lead() -> None:
    """The rule is only ever built on the default ``MIN_ANNOUNCE_LEAD_DAYS``."""
    overrides = [
        (path, function)
        for path, tree in _app_sources()
        for function, call in _calls_by_function(tree)
        if any(keyword.arg == _LEAD_PARAMETER for keyword in call.keywords)
        or (_callee(call) == "AnnounceRunCoverageRule" and len(call.args) > 1)
    ]
    assert overrides == []


def test_k21_scan_sees_the_known_uses() -> None:
    """Guard against a scan that silently matches nothing."""
    seen: set[tuple[str, str]] = set()
    for path, tree in _app_sources():
        for scope, nodes in _scopes(tree):
            if any(_mentions_constant(node) for node in nodes):
                seen.add((path, scope))
    assert ("app/dividends/coverage.py", "__init__") in seen
    assert ("app/portfolio/price_change.py", "_book_checks") in seen
    assert ("app/portfolio/price_change.py", "<module>") in seen
    # The detector itself fires on the forms it is meant to catch.
    probe = ast.parse(
        "import os\ndef f():\n    return os.environ.get('X') or os.getenv('Y') or settings.lead\n"
    )
    assert sum(_is_config_read(node) for node in ast.walk(probe)) >= 4
