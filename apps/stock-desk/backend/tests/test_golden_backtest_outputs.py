"""Golden regression: the backtest, Kelly import and event-study outputs, frozen.

F11-A-26 (``work/reviews/2026-10-13-F-11-PRD-tech-architect-回覆-F11-A1至A32.md``,
PRD FR-16 / AC-24): before F-11 adds its round-trip detail, the outputs it must
not move are recorded here under fixed synthetic inputs, and afterwards they
have to come out value for value the same:

* (a) ``POST /api/backtest``, every id in ``STRATEGY_IDS`` plus the 除權息
  adjusted and ``insufficient_data`` branches -- the whole response;
* (b) ``POST /api/kelly-inputs/{symbol}/import-backtest`` -- status code and
  body, plus the ``kelly_inputs`` and ``kelly_import_attempts`` rows it wrote;
* (c) ``POST /api/event-study`` -- the whole response, SVGs included.

Comparison is exact and order-sensitive: both sides are rendered to the same
canonical JSON text (Python's ``repr`` of a float round-trips exactly), so a
changed digit, a dropped key or a reordered key all fail. Nothing is compared
by tolerance. The inputs are built from ``random.Random(seed).uniform`` and
``randint`` only -- pure Mersenne Twister plus IEEE ``+``/``*`` -- so the bars
themselves are bit-identical on every platform; no libm call feeds them.

What is **left out**, and why (``_EXCLUDED_*`` below hold the exact lists):

* wall-clock stamps: every ``as_of``; the Kelly row's ``produced_at`` (the
  backtest's ``as_of``) and ``updated_at``; ``attempted_at``. Each is asserted
  present and ISO-parseable instead, so dropping one still fails.
* the Kelly view's ``age_days`` and ``freshness``: both count from *today* to
  the fixed out-of-sample end date, so they move with the calendar, not with
  the code. ``anchored_at`` (the fixed end of that window) is still compared.
* ``round_trip_detail`` on the backtest response only: the one sibling field
  F-11 adds (F11-A-4, A-16). Its absence today and its presence later are both
  accepted; anything *else* new on the response, at any depth, fails.

The event study prints a Taipei wall-clock stamp into its header; the route's
``taipei_stamp`` is pinned to a fixed moment for the duration of those cases,
so the header line is compared rather than excluded.

Regenerating is deliberate and never the default: run with
``STOCK_DESK_UPDATE_GOLDEN=1`` and every golden test rewrites its file and then
**fails**, so a run with the variable left set can never pass. Rerun without it
to confirm, and review the JSON diff -- a regenerated golden is a claim that
every changed value was meant to change.
"""

from __future__ import annotations

import difflib
import inspect
import json
import os
import random
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.api import event_study as event_study_api
from app.api.backtest import BacktestRequest, execute_backtest
from app.api.backtest import router as backtest_router
from app.api.deps import get_index_resolver, get_market_resolver
from app.backtest.strategies import STRATEGY_IDS
from app.data.interface import PriceBar
from app.dividends.models import DividendEvent
from tests.conftest import ApiHarness

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
UPDATE_ENV = "STOCK_DESK_UPDATE_GOLDEN"

_END = date(2026, 7, 20)
_AS_OF = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)
#: Fixed so the dividend block's ``last_synced_at`` is a constant, not "now".
_DIVIDEND_SYNCED_AT = datetime(2026, 7, 21, 1, 0, tzinfo=UTC)
#: The moment the event-study header stamp is pinned to.
_EVENT_STUDY_STAMP_AT = datetime(2026, 7, 21, 9, 30, tzinfo=ZoneInfo("Asia/Taipei"))

#: Top-level backtest response keys that may appear after this golden was cut.
#: F11-A-16: exactly one new sibling field. Nothing nested is listed here.
_ADDED_AFTER_GOLDEN_BACKTEST_KEYS = ("round_trip_detail",)
#: Wall-clock fields per surface (see the module docstring).
_EXCLUDED_KELLY_VIEW_KEYS = ("as_of", "age_days", "freshness")
_EXCLUDED_KELLY_ITEM_KEYS = ("produced_at", "updated_at")
_EXCLUDED_KELLY_INPUT_COLUMNS = ("produced_at", "updated_at")
_EXCLUDED_KELLY_ATTEMPT_COLUMNS = ("attempted_at",)


# --------------------------------------------------------------------------
# Synthetic inputs
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Walk:
    """One seeded OHLCV path; ``uniform`` steps keep it platform-exact."""

    seed: int
    bars: int
    drift: float
    step: float


def _two_dp(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def _walk_bars(walk: _Walk, *, symbol: str = "2330") -> list[PriceBar]:
    rnd = random.Random(walk.seed)
    first = _END - timedelta(days=walk.bars - 1)
    close = 100.0
    bars: list[PriceBar] = []
    for index in range(walk.bars):
        open_ = close * (1.0 + rnd.uniform(-walk.step / 3, walk.step / 3))
        close = max(close * (1.0 + walk.drift + rnd.uniform(-walk.step, walk.step)), 1.0)
        high = max(open_, close) * (1.0 + rnd.uniform(0.0, walk.step / 2))
        low = min(open_, close) * (1.0 - rnd.uniform(0.0, walk.step / 2))
        bars.append(
            PriceBar(
                symbol=symbol,
                market="TW",
                date=first + timedelta(days=index),
                open=_two_dp(open_),
                high=_two_dp(high),
                low=_two_dp(low),
                close=_two_dp(close),
                volume=rnd.randint(5_000, 20_000),
                currency="TWD",
                as_of=_AS_OF,
                source="fake",
            )
        )
    return bars


#: Backtest / event-study path: every shipped strategy trades in both segments
#: and has at least one winning and one losing out-of-sample round trip on it,
#: asserted below so a degenerate "never traded" golden cannot be recorded.
_REPORT_WALK = _Walk(seed=22, bars=520, drift=0.0003, step=0.045)
#: Kelly paths (1100 bars, train 120 / test 60). On ``_KELLY_MIXED`` breakout
#: clears the 20/5/5 gate, five_conditions is short of wins and ma_cross /
#: rsi_reversal are short of round trips; on ``_KELLY_UPTREND_LOSSES_SHORT``
#: breakout is short of losses; on ``_KELLY_UPTREND_CLEARS`` it clears again.
_KELLY_MIXED = _Walk(seed=2, bars=1100, drift=0.0005, step=0.05)
_KELLY_UPTREND_LOSSES_SHORT = _Walk(seed=4, bars=1100, drift=0.006, step=0.035)
_KELLY_UPTREND_CLEARS = _Walk(seed=2, bars=1100, drift=0.006, step=0.035)

#: Bar indices whose session is a seeded 除權息 ex-date in the adjusted cases.
_EX_DATE_BAR_INDICES = (150, 400)


def _dividend_events(bars: list[PriceBar]) -> list[DividendEvent]:
    """Two cash dividends on the path itself, priced off the previous close."""
    events: list[DividendEvent] = []
    for index in _EX_DATE_BAR_INDICES:
        previous_close = bars[index - 1].close
        cash = Decimal("3.00")
        events.append(
            DividendEvent(
                symbol=bars[index].symbol,
                market="TW",
                ex_date=bars[index].date,
                previous_close=previous_close,
                reference_price=previous_close - cash,
                cash_dividend=cash,
                source="golden",
                as_of=_AS_OF,
            )
        )
    return events


def _seed(harness: ApiHarness, walk: _Walk, *, dividends: bool = False) -> list[PriceBar]:
    bars = _walk_bars(walk)
    harness.price_service.seed("2330", bars)
    if dividends:
        harness.dividends.upsert(_dividend_events(bars), synced_at=_DIVIDEND_SYNCED_AT)
    return bars


def _window(walk: _Walk) -> dict[str, str]:
    return {
        "start": (_END - timedelta(days=walk.bars - 1)).isoformat(),
        "end": _END.isoformat(),
    }


# --------------------------------------------------------------------------
# Golden file plumbing
# --------------------------------------------------------------------------


def _render(value: Any) -> str:
    """Canonical text: insertion order kept, floats by ``repr``, no NaN."""
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _assert_matches_golden(name: str, actual: Any) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    rendered = _render(actual)
    if os.environ.get(UPDATE_ENV) == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8", newline="\n")
        pytest.fail(f"golden rewritten: {path}; unset {UPDATE_ENV} and rerun to confirm")
    if not path.exists():
        pytest.fail(f"golden missing: {path} (generate it with {UPDATE_ENV}=1)")
    # Re-rendered from the parsed file, so line endings a checkout may have
    # rewritten cannot matter while key order and every digit still do.
    expected = _render(json.loads(path.read_text(encoding="utf-8")))
    if rendered != expected:
        diff = difflib.unified_diff(
            expected.splitlines(),
            rendered.splitlines(),
            fromfile=f"golden/{name}.json",
            tofile="actual",
            lineterm="",
            n=3,
        )
        lines = list(diff)
        shown = "\n".join(lines[:200])
        more = f"\n... ({len(lines) - 200} more diff lines)" if len(lines) > 200 else ""
        pytest.fail(f"output drifted from golden/{name}.json:\n{shown}{more}")


def _pop_timestamp(mapping: dict[str, Any], key: str) -> None:
    """Remove a wall-clock field after proving it is there and is a timestamp."""
    assert key in mapping, f"expected timestamp field {key!r} is missing"
    value = mapping.pop(key)
    assert isinstance(value, str) and value, (key, value)
    datetime.fromisoformat(value)


# --------------------------------------------------------------------------
# (a) POST /api/backtest
# --------------------------------------------------------------------------


def _backtest_request(walk: _Walk, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "symbol": "2330",
        "market": "TW",
        "strategy": "ma_cross",
        **_window(walk),
        "train_size": 120,
        "test_size": 60,
    }
    body.update(overrides)
    return body


def _backtest_golden(harness: ApiHarness, request: dict[str, Any]) -> dict[str, Any]:
    response = harness.client.post("/api/backtest", json=request)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    _pop_timestamp(body, "as_of")
    for key in _ADDED_AFTER_GOLDEN_BACKTEST_KEYS:
        body.pop(key, None)
    return {"request": request, "status_code": response.status_code, "body": body}


def _assert_the_run_measured_something(body: dict[str, Any]) -> None:
    """Guard against freezing a degenerate run that never traded."""
    assert body["status"] == "ok"
    for segment in ("in_sample", "out_of_sample"):
        assert body["report"][segment]["strategy"]["num_trades"] > 0, segment
    out_of_sample = body["report"]["out_of_sample"]["strategy"]
    assert out_of_sample["num_round_trips"] >= 2
    assert 0.0 < out_of_sample["round_trip_win_rate"] < 1.0


@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
def test_backtest_response_matches_golden_for_every_strategy(
    strategy_id: str, api_harness: ApiHarness
) -> None:
    _seed(api_harness, _REPORT_WALK)
    golden = _backtest_golden(api_harness, _backtest_request(_REPORT_WALK, strategy=strategy_id))
    _assert_the_run_measured_something(golden["body"])
    _assert_matches_golden(f"backtest/{strategy_id}", golden)


def test_every_strategy_id_has_its_golden_case() -> None:
    """A strategy added later must arrive with a golden of its own, not skip one."""
    recorded = {path.stem for path in (GOLDEN_DIR / "backtest").glob("*.json")}
    assert set(STRATEGY_IDS) <= recorded


def test_backtest_response_matches_golden_with_dividends_adjusted(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, _REPORT_WALK, dividends=True)
    golden = _backtest_golden(api_harness, _backtest_request(_REPORT_WALK))
    assert golden["body"]["dividend_adjustment"]["reason_code"] == "adjusted"
    assert golden["body"]["dividend_adjustment"]["events_applied"] == len(_EX_DATE_BAR_INDICES)
    _assert_the_run_measured_something(golden["body"])
    _assert_matches_golden("backtest/ma_cross__dividends_adjusted", golden)


def test_backtest_response_matches_golden_when_no_backtest_could_run(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, _REPORT_WALK)
    golden = _backtest_golden(api_harness, _backtest_request(_REPORT_WALK, train_size=500))
    assert golden["body"]["status"] == "insufficient_data"
    _assert_matches_golden("backtest/ma_cross__insufficient_data", golden)


# --------------------------------------------------------------------------
# (b) POST /api/kelly-inputs/{symbol}/import-backtest
# --------------------------------------------------------------------------

_KELLY_PATH = "/api/kelly-inputs/{symbol}/import-backtest"


def _kelly_request(walk: _Walk, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "symbol": "2330",
        "market": "TW",
        "strategy": "breakout",
        **_window(walk),
        "train_size": 120,
        "test_size": 60,
    }
    body.update(overrides)
    return body


def _sanitised_kelly_body(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    if status_code == 200:
        for key in _EXCLUDED_KELLY_VIEW_KEYS:
            if key == "as_of":
                _pop_timestamp(body, key)
            else:
                assert key in body, key
                body.pop(key)
        for key in _EXCLUDED_KELLY_ITEM_KEYS:
            _pop_timestamp(body["item"], key)
    return body


def _table_rows(
    db_path: Path, table: str, order_by: str, excluded: Iterable[str]
) -> list[dict[str, Any]]:
    """Every row of ``table`` from the harness's tmp database, timestamps removed."""
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(f"SELECT * FROM {table} ORDER BY {order_by}")
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    for row in rows:
        for column in excluded:
            _pop_timestamp(row, column)
    return rows


@dataclass(frozen=True)
class _KellyStep:
    walk: _Walk | None
    request: dict[str, Any]
    path_symbol: str = "2330"


def _run_kelly_case(harness: ApiHarness, steps: list[_KellyStep]) -> dict[str, Any]:
    recorded: list[dict[str, Any]] = []
    for step in steps:
        if step.walk is not None:
            _seed(harness, step.walk)
        response = harness.client.post(
            _KELLY_PATH.format(symbol=step.path_symbol), json=step.request
        )
        recorded.append(
            {
                "path_symbol": step.path_symbol,
                "request": step.request,
                "status_code": response.status_code,
                "body": _sanitised_kelly_body(response.status_code, response.json()),
            }
        )
    db_path = harness.kelly_inputs.db_path
    assert db_path == harness.kelly_attempts.db_path
    return {
        "steps": recorded,
        "kelly_inputs": _table_rows(
            db_path, "kelly_inputs", "symbol, market", _EXCLUDED_KELLY_INPUT_COLUMNS
        ),
        "kelly_import_attempts": _table_rows(
            db_path, "kelly_import_attempts", "id", _EXCLUDED_KELLY_ATTEMPT_COLUMNS
        ),
    }


_EXPECTED_MIXED_OUTCOMES = {
    "ma_cross": (422, "low_round_trips"),
    "rsi_reversal": (422, "low_round_trips"),
    "breakout": (200, None),
    "five_conditions": (422, "low_win_trips"),
}


@pytest.mark.parametrize("strategy_id", STRATEGY_IDS)
@pytest.mark.usefixtures("kelly_writes_open")
def test_kelly_import_matches_golden_for_every_strategy(
    strategy_id: str, api_harness: ApiHarness
) -> None:
    request = _kelly_request(_KELLY_MIXED, strategy=strategy_id)
    golden = _run_kelly_case(api_harness, [_KellyStep(_KELLY_MIXED, request)])
    step = golden["steps"][0]
    # The fixture is meant to reach both the store and each sample gate; pin
    # that it still does, so a golden of four identical refusals cannot pass.
    expected_status, expected_code = _EXPECTED_MIXED_OUTCOMES[strategy_id]
    assert step["status_code"] == expected_status
    if expected_code is not None:
        assert step["body"]["detail"]["reason_code"] == expected_code
    _assert_matches_golden(f"kelly_import/{strategy_id}", golden)


@pytest.mark.usefixtures("kelly_writes_open")
def test_kelly_import_matches_golden_across_a_refusal_and_two_overwrites(
    api_harness: ApiHarness,
) -> None:
    """K_observed, the upsert and the attempt log, over three imports on one key."""
    golden = _run_kelly_case(
        api_harness,
        [
            _KellyStep(_KELLY_UPTREND_LOSSES_SHORT, _kelly_request(_KELLY_UPTREND_LOSSES_SHORT)),
            _KellyStep(_KELLY_UPTREND_CLEARS, _kelly_request(_KELLY_UPTREND_CLEARS)),
            _KellyStep(_KELLY_MIXED, _kelly_request(_KELLY_MIXED)),
        ],
    )
    assert [step["status_code"] for step in golden["steps"]] == [422, 200, 200]
    assert golden["steps"][0]["body"]["detail"]["reason_code"] == "low_loss_trips"
    assert len(golden["kelly_import_attempts"]) == 3
    assert golden["kelly_inputs"][0]["k_observed_at_write"] == 3
    _assert_matches_golden("kelly_import/breakout__sequence", golden)


@pytest.mark.usefixtures("kelly_writes_open")
def test_kelly_import_matches_golden_for_the_two_runless_refusals(
    api_harness: ApiHarness,
) -> None:
    """Symbol mismatch (refused before any run) and a window with no bars."""
    golden = _run_kelly_case(
        api_harness,
        [
            _KellyStep(None, _kelly_request(_KELLY_MIXED, symbol="2317")),
            _KellyStep(None, _kelly_request(_KELLY_MIXED)),
        ],
    )
    codes = [step["body"]["detail"]["reason_code"] for step in golden["steps"]]
    assert codes == ["symbol_mismatch", "insufficient_data"]
    assert golden["kelly_inputs"] == []
    _assert_matches_golden("kelly_import/runless_refusals", golden)


# --------------------------------------------------------------------------
# (c) POST /api/event-study
# --------------------------------------------------------------------------


@pytest.fixture
def pinned_event_study_stamp(monkeypatch: pytest.MonkeyPatch) -> None:
    real: Callable[[datetime | None], str] = event_study_api.taipei_stamp

    def fixed(now: datetime | None = None) -> str:
        return real(_EVENT_STUDY_STAMP_AT)

    monkeypatch.setattr(event_study_api, "taipei_stamp", fixed)


def _event_study_golden(harness: ApiHarness, request: dict[str, Any]) -> dict[str, Any]:
    response = harness.client.post("/api/event-study", json=request)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    _pop_timestamp(body, "as_of")
    return {"request": request, "status_code": response.status_code, "body": body}


def _assert_the_page_has_events(body: dict[str, Any]) -> None:
    assert body["status"] == "ok"
    for section in body["page"]["sections"]:
        assert section["svg"] is not None and section["empty_statement"] is None, section["key"]


@pytest.mark.usefixtures("pinned_event_study_stamp")
def test_event_study_matches_golden(api_harness: ApiHarness) -> None:
    _seed(api_harness, _REPORT_WALK)
    golden = _event_study_golden(api_harness, {"symbol": "2330", "market": "TW"})
    _assert_the_page_has_events(golden["body"])
    _assert_matches_golden("event_study/walk", golden)


@pytest.mark.usefixtures("pinned_event_study_stamp")
def test_event_study_matches_golden_with_dividends_adjusted(api_harness: ApiHarness) -> None:
    _seed(api_harness, _REPORT_WALK, dividends=True)
    golden = _event_study_golden(
        api_harness, {"symbol": "2330", "market": "TW", **_window(_REPORT_WALK)}
    )
    _assert_the_page_has_events(golden["body"])
    _assert_matches_golden("event_study/walk__dividends_adjusted", golden)


@pytest.mark.usefixtures("pinned_event_study_stamp")
def test_event_study_matches_golden_when_there_is_nothing_to_study(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, _REPORT_WALK)
    golden = _event_study_golden(
        api_harness, {"symbol": "2330", "market": "TW", "start": _END.isoformat()}
    )
    assert golden["body"]["status"] == "insufficient_data"
    _assert_matches_golden("event_study/insufficient_data", golden)


# --------------------------------------------------------------------------
# F11-A-14: the backtest request model is frozen (spec_hash, bootstrap seed)
# --------------------------------------------------------------------------

#: ``spec_hash`` is the SHA-256 of ``BacktestRequest.model_dump(mode="json")``
#: and the Kelly bootstrap seed is cut from it (F11-A-7), so even a defaulted
#: new field changes every stored f* interval.
_BACKTEST_REQUEST_FIELDS = (
    "symbol",
    "market",
    "strategy",
    "start",
    "end",
    "instrument_type",
    "initial_cash",
    "train_size",
    "test_size",
    "cost",
    "adjust_dividends",
)


def test_backtest_request_fields_are_exactly_the_pre_f11_list() -> None:
    assert tuple(BacktestRequest.model_fields) == _BACKTEST_REQUEST_FIELDS


def test_backtest_request_types_and_defaults_match_golden() -> None:
    """Types, defaults and bounds via the schema; the dump is what gets hashed."""
    minimal = BacktestRequest.model_validate(
        {"symbol": "2330", "start": "2024-01-01", "end": "2024-12-31"}
    )
    _assert_matches_golden(
        "backtest_request",
        {
            "fields": list(BacktestRequest.model_fields),
            "json_schema": BacktestRequest.model_json_schema(),
            "minimal_body_dump": minimal.model_dump(mode="json"),
        },
    )


# --------------------------------------------------------------------------
# F11-A-27: one daily-bar read per backtest, and no index read at all
# --------------------------------------------------------------------------


def _dependency_calls(dependant: Dependant) -> set[Any]:
    calls: set[Any] = set()
    for dependency in dependant.dependencies:
        if dependency.call is not None:
            calls.add(dependency.call)
        calls |= _dependency_calls(dependency)
    return calls


def _backtest_route() -> APIRoute:
    """The route as declared on its router (``app.routes`` nests included routers)."""
    for route in backtest_router.routes:
        if (
            isinstance(route, APIRoute)
            and route.path == "/api/backtest"
            and "POST" in (route.methods or ())
        ):
            return route
    raise AssertionError("no POST /api/backtest route")


def test_one_backtest_request_reads_daily_bars_once_and_never_an_index(
    api_harness: ApiHarness,
) -> None:
    _seed(api_harness, _REPORT_WALK)

    response = api_harness.client.post("/api/backtest", json=_backtest_request(_REPORT_WALK))

    assert response.status_code == 200 and response.json()["status"] == "ok"
    assert len(api_harness.price_service.calls) == 1
    assert api_harness.price_service.cached_calls == []
    assert api_harness.index_service.calls == []
    assert api_harness.index_service.cached_calls == []


@pytest.mark.usefixtures("kelly_writes_open")
def test_one_kelly_import_reads_daily_bars_once_and_never_an_index(
    api_harness: ApiHarness,
) -> None:
    """The import shares ``execute_backtest``, so it shares the read budget."""
    _seed(api_harness, _KELLY_MIXED)

    response = api_harness.client.post(
        _KELLY_PATH.format(symbol="2330"), json=_kelly_request(_KELLY_MIXED)
    )

    assert response.status_code == 200, response.text
    assert len(api_harness.price_service.calls) == 1
    assert api_harness.price_service.cached_calls == []
    assert api_harness.index_service.calls == []
    assert api_harness.index_service.cached_calls == []


def test_the_backtest_pipeline_takes_no_index_resolver() -> None:
    """Structural half of F11-A-27: neither the route nor the pipeline can reach one."""
    calls = _dependency_calls(_backtest_route().dependant)
    # Positive control: the walk does see the resolver the route does take.
    assert get_market_resolver in calls
    assert get_index_resolver not in calls
    for name, parameter in inspect.signature(execute_backtest).parameters.items():
        assert "Index" not in str(parameter.annotation), name
