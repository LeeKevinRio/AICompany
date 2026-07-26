"""The offline demo seed produces working endpoints, and says the data is fake.

The harness deliberately reproduces the *offline* topology rather than stubbing
the loader: a real :class:`MarketDataService` whose only provider always reports
``unavailable`` (which is what a box with no network gets), backed by the real
SQLite cache the seeder wrote into. So these tests assert the same degradation
path the acceptance machine will take -- provider chain fails, the cache answers
``cached_stale``, and the demo provenance travels intact to the response.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.alerts.store import AlertStore
from app.api.deps import (
    get_alert_store,
    get_market_resolver,
    get_position_store,
    get_settings_store,
    get_valuator,
)
from app.data.cache import PriceBarCache
from app.data.interface import DataStatus, MarketDataProvider, PriceBar, ProviderResult
from app.demo.seed import (
    BLUE_CHIP_SYMBOL,
    DEMO_NOTE_PREFIX,
    DEMO_POSITIONS,
    INDEX_PROXY_SYMBOL,
    LEVERAGED_SYMBOL,
    main,
    reset_demo,
    seed_demo,
)
from app.demo.series import DEMO_SOURCE
from app.main import app
from app.portfolio.valuation import PositionValuator
from app.positions.models import PositionInput
from app.positions.store import PositionStore
from app.settings.store import SettingsStore
from tests.api_helpers import UnavailableFxProvider

_AS_OF = datetime(2026, 7, 25, 6, 0, tzinfo=UTC)


class OfflineProvider(MarketDataProvider):
    """Every live provider on a machine with no outbound network."""

    source_id = "offline_no_network"

    def get_daily_bars(self, symbol: str, start: date, end: date) -> ProviderResult:
        return ProviderResult(
            bars=[],
            status=DataStatus.UNAVAILABLE,
            as_of=_AS_OF,
            source=self.source_id,
            staleness_minutes=None,
        )


@dataclass
class DemoHarness:
    """A client wired to one on-disk database, plus that database's stores."""

    client: TestClient
    db_path: Path
    cache: PriceBarCache
    positions: PositionStore
    alerts: AlertStore


@pytest.fixture
def demo_harness(tmp_path: Path) -> Iterator[DemoHarness]:
    from app.data.service import MarketDataService

    db_path = tmp_path / "demo.db"
    cache = PriceBarCache(db_path)
    positions = PositionStore(db_path)
    alerts = AlertStore(db_path)
    settings = SettingsStore(db_path)
    service = MarketDataService(primary=OfflineProvider(), cache=cache)
    valuator = PositionValuator(
        market_services={"TW": service}, fx_provider=UnavailableFxProvider()
    )

    app.dependency_overrides[get_position_store] = lambda: positions
    app.dependency_overrides[get_alert_store] = lambda: alerts
    app.dependency_overrides[get_settings_store] = lambda: settings
    app.dependency_overrides[get_valuator] = lambda: valuator
    app.dependency_overrides[get_market_resolver] = lambda: {"TW": service}

    with TestClient(app) as client:
        yield DemoHarness(
            client=client,
            db_path=db_path,
            cache=cache,
            positions=positions,
            alerts=alerts,
        )
    app.dependency_overrides.clear()


def _seed(harness: DemoHarness) -> None:
    seed_demo(cache=harness.cache, positions=harness.positions, alerts=harness.alerts)


def test_without_the_seed_every_endpoint_is_insufficient_data(demo_harness: DemoHarness) -> None:
    """The state this whole feature exists to fix, pinned so it cannot regress."""
    for path in ("/api/bars", "/api/signals", "/api/advice"):
        response = demo_harness.client.get(f"{path}/{BLUE_CHIP_SYMBOL}")
        assert response.status_code == 200
        assert response.json()["status"] == "insufficient_data"


@pytest.mark.parametrize("symbol", [BLUE_CHIP_SYMBOL, INDEX_PROXY_SYMBOL, LEVERAGED_SYMBOL])
def test_seeded_endpoints_return_ok_from_the_demo_source(
    demo_harness: DemoHarness, symbol: str
) -> None:
    """/api/bars, /api/signals and /api/advice all answer, all tagged as demo data."""
    _seed(demo_harness)

    bars = demo_harness.client.get(f"/api/bars/{symbol}").json()
    assert bars["status"] == "ok"
    assert bars["data"]["source"] == DEMO_SOURCE
    # No live provider answered, so the cache did: the response says so.
    assert bars["data"]["status"] == DataStatus.CACHED_STALE.value
    assert bars["data"]["bar_count"] > 300
    assert {bar["source"] for bar in bars["bars"]} == {DEMO_SOURCE}

    signals = demo_harness.client.get(f"/api/signals/{symbol}").json()
    assert signals["status"] == "ok"
    assert signals["data"]["source"] == DEMO_SOURCE
    assert signals["signals"]["source"] == DEMO_SOURCE

    advice = demo_harness.client.get(f"/api/advice/{symbol}").json()
    assert advice["status"] == "ok"
    assert advice["data"]["source"] == DEMO_SOURCE
    assert advice["advice"] is not None
    assert advice["held"] is True


@pytest.mark.parametrize("symbol", [BLUE_CHIP_SYMBOL, INDEX_PROXY_SYMBOL, LEVERAGED_SYMBOL])
def test_seeded_signals_are_computed_not_insufficient(
    demo_harness: DemoHarness, symbol: str
) -> None:
    """The point of the synthetic regimes: the indicators actually have values."""
    _seed(demo_harness)
    signals = demo_harness.client.get(f"/api/signals/{symbol}").json()["signals"]

    technical = signals["technical"]
    for name in ("moving_averages", "rsi", "macd", "bollinger", "atr", "kd", "volume_zscore"):
        assert technical[name]["status"] == "ok", name
    assert technical["moving_averages"]["last"]["ma_60"] is not None

    risk = signals["risk"]
    assert risk["volatility"]["status"] == "ok"
    assert risk["drawdown"]["status"] == "ok"
    # The layout puts a correction and a sell-off in every path, so the
    # drawdown rules on the advice card have something to fire on.
    assert risk["drawdown"]["max_drawdown"] < -0.15


def test_seeded_advice_card_matches_rules(demo_harness: DemoHarness) -> None:
    _seed(demo_harness)
    advice = demo_harness.client.get(f"/api/advice/{BLUE_CHIP_SYMBOL}").json()["advice"]
    assert advice["matched_rules"], "示範資料應至少命中一條建議規則"
    assert advice["counterarguments"]


def test_seed_writes_positions_and_alert_rules_marked_as_demo(
    demo_harness: DemoHarness,
) -> None:
    _seed(demo_harness)

    positions = demo_harness.client.get("/api/positions").json()["items"]
    assert len(positions) == len(DEMO_POSITIONS)
    assert all(position["note"].startswith(DEMO_NOTE_PREFIX) for position in positions)

    rules = demo_harness.client.get("/api/alerts").json()["items"]
    assert len(rules) == 3
    assert all(rule["note"].startswith(DEMO_NOTE_PREFIX) for rule in rules)

    # The portfolio page has real totals rather than an empty book.
    summary = demo_harness.client.get("/api/portfolio/summary").json()
    assert Decimal(summary["totals"]["market_value_twd"]) > 0


def test_seeded_alert_rules_actually_fire(demo_harness: DemoHarness) -> None:
    """The alerts panel is not empty after one evaluation pass."""
    _seed(demo_harness)
    result = demo_harness.client.post("/api/alerts/evaluate").json()
    assert result["events"], result["outcomes"]


def test_seeding_twice_is_idempotent(demo_harness: DemoHarness) -> None:
    first = seed_demo(
        cache=demo_harness.cache, positions=demo_harness.positions, alerts=demo_harness.alerts
    )
    second = seed_demo(
        cache=demo_harness.cache, positions=demo_harness.positions, alerts=demo_harness.alerts
    )

    assert first.positions_created and not first.positions_kept
    assert second.positions_created == [] and len(second.positions_kept) == len(DEMO_POSITIONS)
    assert second.rules_created == [] and len(second.rules_kept) == 3
    assert len(demo_harness.positions.list_all()) == len(DEMO_POSITIONS)
    assert len(demo_harness.alerts.list_rules()) == 3

    bars = demo_harness.client.get(f"/api/bars/{BLUE_CHIP_SYMBOL}").json()["bars"]
    assert len({bar["date"] for bar in bars}) == len(bars), "重跑不得產生重複的日線"


def test_reset_removes_demo_rows_and_leaves_real_ones(demo_harness: DemoHarness) -> None:
    _seed(demo_harness)
    real = demo_harness.positions.create(
        PositionInput(
            symbol="2412",
            market="TW",
            quantity=Decimal("2000"),
            avg_cost=Decimal("120"),
            currency="TWD",
            opened_at=date(2025, 1, 6),
            instrument_type="stock",
            note="使用者自己的持倉",
        )
    )
    real_bar = PriceBar(
        symbol="2412",
        market="TW",
        date=date.today(),
        open=Decimal("120"),
        high=Decimal("121"),
        low=Decimal("119"),
        close=Decimal("120.5"),
        volume=1000,
        currency="TWD",
        as_of=_AS_OF,
        source="twse",
    )
    demo_harness.cache.put([real_bar], source="twse", fetched_at=_AS_OF)

    removed = reset_demo(
        cache=demo_harness.cache, positions=demo_harness.positions, alerts=demo_harness.alerts
    )

    assert removed.bars_deleted > 0
    assert removed.positions_deleted == len(DEMO_POSITIONS)
    assert removed.rules_deleted == 3
    assert [position.id for position in demo_harness.positions.list_all()] == [real.id]
    assert demo_harness.alerts.list_rules() == []
    assert demo_harness.cache.get("2412", "TW", date.today(), date.today()) is not None

    after = demo_harness.client.get(f"/api/bars/{BLUE_CHIP_SYMBOL}").json()
    assert after["status"] == "insufficient_data"


def test_cli_prints_the_synthetic_warning_before_and_after(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "cli.db"
    assert main(["--db-path", str(db_path)]) == 0

    printed = capsys.readouterr().out
    assert printed.count("警告：這是合成示範資料，不可用於任何真實決策。") == 2
    assert DEMO_SOURCE in printed
    assert PositionStore(db_path).list_all()

    assert main(["--db-path", str(db_path), "--reset"]) == 0
    reset_output = capsys.readouterr().out
    assert reset_output.count("警告：這是合成示範資料，不可用於任何真實決策。") == 2
    assert PositionStore(db_path).list_all() == []
