"""Seed (or retract) the offline demo dataset.

    uv run python -m app.demo.seed            # seed / refresh
    uv run python -m app.demo.seed --reset    # remove every demo row

WHAT THIS IS FOR
================
An environment with no outbound network gets ``unavailable`` from every
provider, so the four pages render nothing but ``insufficient_data``. This
seeder fills the **existing** cache and stores -- no new tables, no parallel
schema -- with a synthetic dataset so the whole stack (indicators, risk caps,
advice cards, alerts) can be exercised and demonstrated offline.

WHAT THIS IS NOT
================
It is not market data. Every bar is written with
``source="demo_synthetic"`` (:data:`app.demo.series.DEMO_SOURCE`), which is the
string the API echoes in ``data.source`` and the UI prints in its "來源" line,
so a demo dataset can never be mistaken for a TWSE/TPEx/FinMind series. Every
seeded position and alert rule carries :data:`DEMO_NOTE_PREFIX` in its note.
The CLI prints the same warning before and after it runs.

Idempotence
-----------
* Bars go through :meth:`PriceBarCache.put`, whose primary key is
  ``(symbol, market, trade_date)``: a re-run overwrites the same rows rather
  than duplicating them.
* Positions and alert rules are matched on their demo marker plus their
  identity (symbol/market, and rule type) and **left untouched** when they
  already exist, so a re-run never stacks up a second copy and never rewrites a
  cost basis the demo already told a story about.
* ``--reset`` deletes exactly the rows this seeder owns -- bars tagged
  ``demo_synthetic``, and positions/rules carrying the marker -- and nothing
  else.

It never overwrites real data
-----------------------------
Because the symbols are real listed codes (see below), a database that already
holds real quotes for them would have those bars replaced by the upsert -- and
``--reset`` could not undo that, because it only deletes rows still tagged
``demo_synthetic``. So the seeder asks first: :meth:`PriceBarCache.find_foreign_bars`
looks for rows at the exact keys it is about to write that some *other* source
owns, and if there are any the run **refuses outright**
(:class:`DemoSeedConflictError`, exit code 1) before writing a single row --
bars, positions and alert rules included. Deciding that those quotes are
expendable is the user's call, not this script's: it prints what conflicts and
suggests a separate ``STOCK_DESK_DB_PATH`` / ``--db-path``, and never deletes
anything it did not write.

Every symbol below is a real listed code, deliberately: the demo is more useful
when the leveraged chapter can find ``00631L`` in the registry. The *prices*
attached to those codes are invented.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final

from app.advice.loader import Comparison
from app.alerts.models import (
    AlertRule,
    AlertRuleInput,
    PriceThresholdParams,
    RiskLimitParams,
    SignalConditionParams,
)
from app.alerts.store import AlertStore
from app.data.cache import ForeignBarConflict, PriceBarCache, resolve_db_path
from app.data.interface import PriceBar
from app.demo.series import (
    DEMO_SOURCE,
    build_bars,
    daily_reset_closes,
    regime_bar_count,
    regime_volume_multipliers,
    synthetic_closes,
    trading_days,
)
from app.leverage.detect import lookup_metadata
from app.positions.models import Currency, InstrumentType, Market, Position, PositionInput
from app.positions.store import PositionStore

#: Marker written into the ``note`` of every demo position and alert rule. It is
#: both the "this is fake" disclosure the user sees in the UI and the key
#: ``--reset`` deletes on, so a row can never be retracted by accident.
DEMO_NOTE_PREFIX: Final = "[demo_synthetic]"

#: Shown on the CLI before and after every run.
WARNING_BANNER: Final = (
    "警告：這是合成示範資料，不可用於任何真實決策。\n"
    f"所有日線的 source 皆標記為 {DEMO_SOURCE}，並非 TWSE／TPEx／FinMind 的真實行情；\n"
    f"示範持倉與警示規則的備註都帶有 {DEMO_NOTE_PREFIX} 標記。"
)

_BANNER_RULE: Final = "=" * 72

DEMO_MARKET: Final[Market] = "TW"
DEMO_CURRENCY: Final[Currency] = "TWD"

#: A large-cap ordinary stock.
BLUE_CHIP_SYMBOL: Final = "2330"
#: The index-tracking ETF used as the underlying series for the leveraged fund.
#: 00631L's benchmark is an index with no ticker of its own, so its tracker is
#: the stand-in a data adapter would realistically quote.
INDEX_PROXY_SYMBOL: Final = "0050"
#: The daily-reset leveraged ETF, present in ``app.leverage.detect``'s registry.
LEVERAGED_SYMBOL: Final = "00631L"

#: Per-symbol generator inputs. The seeds are fixed so the dataset is
#: reproducible bar for bar, and they were *chosen* rather than picked at
#: random: a regime layout only states the intended drift, and a single draw can
#: still wander far enough that the correction never actually corrects or the
#: level ends up implausible. These two were screened so that every segment is
#: visible on the chart (the correction and the sell-off each give back at least
#: 13%), the two-year return stays in a believable band, and the final RSI lands
#: on either side of the overbought line -- the blue chip below it, the index
#: above it -- so the two advice cards do not read identically.
_BLUE_CHIP_START: Final = 620.0
_BLUE_CHIP_SEED: Final = 24
_BLUE_CHIP_VOLUME: Final = 22_000
_INDEX_START: Final = 120.0
_INDEX_SEED: Final = 41
_INDEX_VOLUME: Final = 14_000
#: The leveraged path is derived from the index, so its "seed" only shapes the
#: intraday structure and volume of its bars.
_LEVERAGED_START: Final = 70.0
_LEVERAGED_SEED: Final = 631
_LEVERAGED_VOLUME: Final = 9_000
#: Offset added to a series seed for its OHLC/volume stream, so the price path
#: and the intraday structure do not share a random stream.
_SHAPE_SEED_OFFSET: Final = 7


@dataclass(frozen=True)
class DemoPositionSpec:
    """One demo holding, priced off the generated series itself.

    ``opened_bar_index`` indexes the generated bars: the demo's ``opened_at``
    and ``avg_cost`` are that bar's date and close, so the book's P&L is
    consistent with the chart the user is looking at instead of being a second
    set of invented numbers.
    """

    symbol: str
    instrument_type: InstrumentType
    quantity: Decimal
    opened_bar_index: int
    note: str


DEMO_POSITIONS: Final[tuple[DemoPositionSpec, ...]] = (
    DemoPositionSpec(
        symbol=BLUE_CHIP_SYMBOL,
        instrument_type="stock",
        quantity=Decimal("1000"),
        opened_bar_index=150,
        note="示範持倉：一般台股，建倉於第一段上升趨勢中",
    ),
    DemoPositionSpec(
        symbol=INDEX_PROXY_SYMBOL,
        instrument_type="etf",
        quantity=Decimal("5000"),
        opened_bar_index=200,
        note="示範持倉：指數型 ETF，建倉於回檔段",
    ),
    DemoPositionSpec(
        symbol=LEVERAGED_SYMBOL,
        instrument_type="leveraged_etf",
        quantity=Decimal("3000"),
        opened_bar_index=460,
        note="示範持倉：日度重置槓桿 ETF，建倉於波段高點附近（示範帳面虧損）",
    ),
)

#: How far above the latest close the demo ``price_below`` threshold sits, so
#: the alert page has at least one event to show after an evaluation run.
_PRICE_ALERT_HEADROOM: Final = Decimal("1.05")

#: The drawdown the demo ``signal_condition`` rule watches on the leveraged ETF.
#: Calibrated against the *alert engine's* 400-day snapshot window (see
#: ``app.alerts.snapshot``), which is shorter than the 540-day window
#: ``/api/signals`` reports against and therefore sees a shallower drawdown. A
#: threshold tuned to the longer window would leave the rule permanently quiet,
#: which would look like "nothing happened" rather than "not measured" -- the
#: exact confusion the alert layer is built to avoid.
_DRAWDOWN_ALERT_THRESHOLD: Final = -0.20


@dataclass(frozen=True)
class DemoSeedSummary:
    """What one seeding run wrote, for the CLI to print and a test to assert on."""

    bars_by_symbol: dict[str, int] = field(default_factory=dict)
    first_bar_date: date | None = None
    last_bar_date: date | None = None
    positions_created: list[str] = field(default_factory=list)
    positions_kept: list[str] = field(default_factory=list)
    rules_created: list[str] = field(default_factory=list)
    rules_kept: list[str] = field(default_factory=list)

    @property
    def bar_count(self) -> int:
        return sum(self.bars_by_symbol.values())


def _conflict_report(conflicts: Sequence[ForeignBarConflict], db_path: Path) -> str:
    """The refusal message: what conflicts, why it is fatal, and the way out.

    It names every affected symbol with a row count, a date range and the
    source that wrote those rows, so the user can tell at a glance whether the
    data in the way is something they care about. The remedies stop at
    suggesting a separate database or clearing the rows *themselves*: this
    script deletes nothing it did not write.
    """
    by_series: dict[tuple[str, str], list[ForeignBarConflict]] = {}
    for conflict in conflicts:
        by_series.setdefault((conflict.symbol, conflict.market), []).append(conflict)

    lines = [
        "拒絕寫入示範資料：目標資料庫在示範標的的相同日期上，已經有非示範來源的日線。",
        f"資料庫：{db_path}",
        "衝突明細：",
    ]
    for (symbol, market), rows in sorted(by_series.items()):
        sources = "、".join(sorted({row.source for row in rows}))
        first = min(row.trade_date for row in rows)
        last = max(row.trade_date for row in rows)
        lines.append(f"  - {symbol}（{market}）：{len(rows)} 筆，{first} ~ {last}，來源：{sources}")
    lines += [
        f"合計 {len(conflicts)} 筆。",
        "示範日線是以 (symbol, market, trade_date) upsert 寫入，會直接覆蓋上面這些列；"
        f"而 --reset 只會刪掉 source={DEMO_SOURCE} 的列，"
        "被覆蓋掉的原始資料無法還原，那些日期會變成沒有資料。",
        "因此本次不寫入任何東西（日線、示範持倉、示範警示規則都沒有建立）。",
        "請擇一處理：",
        "  1.（建議）把示範資料放進獨立的資料庫，例如加上 --db-path ./data/demo.db，"
        "或設定環境變數 STOCK_DESK_DB_PATH=./data/demo.db 後重跑；",
        "  2. 若你確認上面這些日線可以捨棄，請自行清除後再重跑；"
        "本腳本不會替你刪除任何不是它寫的資料。",
    ]
    return "\n".join(lines)


class DemoSeedConflictError(RuntimeError):
    """Raised instead of overwriting bars another source wrote.

    Carries the conflicting rows so a caller can report them its own way; the
    string form is the ready-made CLI message from :func:`_conflict_report`.
    """

    def __init__(self, conflicts: Sequence[ForeignBarConflict], *, db_path: Path) -> None:
        super().__init__(_conflict_report(conflicts, db_path))
        self.conflicts: tuple[ForeignBarConflict, ...] = tuple(conflicts)
        self.db_path = db_path


@dataclass(frozen=True)
class DemoResetSummary:
    """What one ``--reset`` run removed."""

    bars_deleted: int
    positions_deleted: int
    rules_deleted: int


def build_demo_bars(
    *, today: date | None = None, as_of: datetime | None = None
) -> dict[str, list[PriceBar]]:
    """Generate the full synthetic dataset, symbol -> ascending bars.

    The series ends on the latest weekday on or before ``today`` because every
    symbol-scoped endpoint asks for ``[today - lookback, today]`` and the
    valuation layer only looks back ten days for a price: a dataset pinned to a
    fixed past date would silently be "no data" again.
    """
    end = today if today is not None else date.today()
    moment = as_of if as_of is not None else datetime.now(UTC)
    count = regime_bar_count()
    dates = trading_days(count, end=end)
    multipliers = regime_volume_multipliers()

    metadata = lookup_metadata(LEVERAGED_SYMBOL)
    if metadata is None:  # pragma: no cover - the symbol is a registry entry
        raise RuntimeError(
            f"{LEVERAGED_SYMBOL} is missing from app.leverage.detect.KNOWN_LEVERAGED_ETF; "
            "the demo derives its NAV path from the registry's leverage factor and "
            "expense ratio rather than hard-coding them"
        )

    blue_chip = synthetic_closes(start_price=_BLUE_CHIP_START, seed=_BLUE_CHIP_SEED)
    index = synthetic_closes(start_price=_INDEX_START, seed=_INDEX_SEED)
    leveraged = daily_reset_closes(
        index,
        start_price=_LEVERAGED_START,
        leverage_factor=metadata.leverage_factor,
        expense_ratio_annual=metadata.expense_ratio_annual,
    )

    return {
        symbol: build_bars(
            symbol=symbol,
            market=DEMO_MARKET,
            currency=DEMO_CURRENCY,
            dates=dates,
            closes=closes,
            base_volume=volume,
            seed=seed + _SHAPE_SEED_OFFSET,
            as_of=moment,
            volume_multipliers=multipliers,
        )
        for symbol, closes, volume, seed in (
            (BLUE_CHIP_SYMBOL, blue_chip, _BLUE_CHIP_VOLUME, _BLUE_CHIP_SEED),
            (INDEX_PROXY_SYMBOL, index, _INDEX_VOLUME, _INDEX_SEED),
            (LEVERAGED_SYMBOL, leveraged, _LEVERAGED_VOLUME, _LEVERAGED_SEED),
        )
    }


def _demo_note(text: str) -> str:
    return f"{DEMO_NOTE_PREFIX} {text}"


def _is_demo_note(note: str | None) -> bool:
    return note is not None and note.startswith(DEMO_NOTE_PREFIX)


def _position_inputs(bars_by_symbol: Mapping[str, Sequence[PriceBar]]) -> list[PositionInput]:
    """Turn the position specs into validated inputs priced off the series."""
    inputs: list[PositionInput] = []
    for spec in DEMO_POSITIONS:
        bars = bars_by_symbol[spec.symbol]
        anchor = bars[min(spec.opened_bar_index, len(bars) - 1)]
        inputs.append(
            PositionInput(
                symbol=spec.symbol,
                market=DEMO_MARKET,
                quantity=spec.quantity,
                avg_cost=anchor.close,
                currency=DEMO_CURRENCY,
                opened_at=anchor.date,
                instrument_type=spec.instrument_type,
                note=_demo_note(spec.note),
            )
        )
    return inputs


def _rule_inputs(bars_by_symbol: Mapping[str, Sequence[PriceBar]]) -> list[AlertRuleInput]:
    """The demo alert rules, one per rule type that can fire offline.

    The price threshold is derived from the seeded series so the rule actually
    crosses on the next evaluation and the alerts panel has something in it; the
    other two watch a measurement the demo dataset is known to produce.
    """
    latest_close = bars_by_symbol[BLUE_CHIP_SYMBOL][-1].close
    threshold = float((latest_close * _PRICE_ALERT_HEADROOM).quantize(Decimal("0.01")))
    return [
        AlertRuleInput(
            type="price_below",
            symbol=BLUE_CHIP_SYMBOL,
            market=DEMO_MARKET,
            params=PriceThresholdParams(threshold=threshold),
            note=_demo_note(f"示範警示：收盤價低於 {threshold} 時提醒"),
        ),
        AlertRuleInput(
            type="signal_condition",
            symbol=LEVERAGED_SYMBOL,
            market=DEMO_MARKET,
            params=SignalConditionParams(
                condition=Comparison(
                    field="drawdown.max_drawdown", op="lt", value=_DRAWDOWN_ALERT_THRESHOLD
                )
            ),
            note=_demo_note("示範警示：區間最大回撤深於 -20%"),
        ),
        AlertRuleInput(
            type="risk_limit_breach",
            symbol=BLUE_CHIP_SYMBOL,
            market=DEMO_MARKET,
            params=RiskLimitParams(limit_id="single_position_weight"),
            note=_demo_note("示範警示：單一標的佔比觸及風險上限"),
        ),
    ]


def _existing_demo_positions(store: PositionStore) -> dict[tuple[str, str], Position]:
    return {
        (position.symbol, position.market): position
        for position in store.list_all()
        if _is_demo_note(position.note)
    }


def _existing_demo_rules(store: AlertStore) -> dict[tuple[str, str, str], AlertRule]:
    return {
        (rule.type, rule.symbol, rule.market): rule
        for rule in store.list_rules()
        if _is_demo_note(rule.note)
    }


def seed_demo(
    *,
    cache: PriceBarCache,
    positions: PositionStore,
    alerts: AlertStore,
    today: date | None = None,
    as_of: datetime | None = None,
) -> DemoSeedSummary:
    """Write the demo dataset through the existing cache and stores.

    Raises :class:`DemoSeedConflictError` -- before writing anything at all --
    when the cache already holds bars from another source at the keys this run
    would upsert. See the module docstring: overwriting them would be silent,
    irreversible data loss, and choosing to give them up is the user's call.
    """
    moment = as_of if as_of is not None else datetime.now(UTC)
    bars_by_symbol = build_demo_bars(today=today, as_of=moment)

    conflicts = [
        conflict
        for bars in bars_by_symbol.values()
        for conflict in cache.find_foreign_bars(bars, source=DEMO_SOURCE)
    ]
    if conflicts:
        raise DemoSeedConflictError(conflicts, db_path=cache.db_path)

    for bars in bars_by_symbol.values():
        # ``fetched_at`` is the run time: the bars are as fresh as this run, and
        # the API will report the resulting staleness honestly.
        cache.put(list(bars), source=DEMO_SOURCE, fetched_at=moment)

    existing_positions = _existing_demo_positions(positions)
    created_positions: list[str] = []
    kept_positions: list[str] = []
    for data in _position_inputs(bars_by_symbol):
        if (data.symbol, data.market) in existing_positions:
            kept_positions.append(data.symbol)
            continue
        positions.create(data, now=moment)
        created_positions.append(data.symbol)

    existing_rules = _existing_demo_rules(alerts)
    created_rules: list[str] = []
    kept_rules: list[str] = []
    for rule in _rule_inputs(bars_by_symbol):
        label = f"{rule.type}／{rule.symbol}"
        if (rule.type, rule.symbol, rule.market) in existing_rules:
            kept_rules.append(label)
            continue
        alerts.create_rule(rule, now=moment)
        created_rules.append(label)

    sample = next(iter(bars_by_symbol.values()))
    return DemoSeedSummary(
        bars_by_symbol={symbol: len(bars) for symbol, bars in bars_by_symbol.items()},
        first_bar_date=sample[0].date,
        last_bar_date=sample[-1].date,
        positions_created=created_positions,
        positions_kept=kept_positions,
        rules_created=created_rules,
        rules_kept=kept_rules,
    )


def reset_demo(
    *, cache: PriceBarCache, positions: PositionStore, alerts: AlertStore
) -> DemoResetSummary:
    """Remove every row this seeder owns, and only those.

    Bars are deleted by ``source = demo_synthetic`` and positions/rules by their
    demo marker, so a database that also holds real rows keeps them. This stays
    deliberately narrow: clearing real data is never this script's decision, it
    is the thing the seeding guard tells the user to do themselves.

    Alert *events* raised by demo rules are deliberately not deleted: an event
    is a record of something that was observed at a point in time, which the
    alert store treats as append-only (see ``app/alerts/store.py``). Re-running
    the seeder does not resurrect the rules those events came from, so they age
    out of the panel as acknowledged history.
    """
    bars_deleted = cache.delete_by_source(DEMO_SOURCE)

    positions_deleted = 0
    for position in positions.list_all():
        if _is_demo_note(position.note) and positions.delete(position.id):
            positions_deleted += 1

    rules_deleted = 0
    for rule in alerts.list_rules():
        if _is_demo_note(rule.note) and alerts.delete_rule(rule.id):
            rules_deleted += 1

    return DemoResetSummary(
        bars_deleted=bars_deleted,
        positions_deleted=positions_deleted,
        rules_deleted=rules_deleted,
    )


def _print_banner() -> None:
    print(_BANNER_RULE)
    print(WARNING_BANNER)
    print(_BANNER_RULE)


def _print_seed_summary(summary: DemoSeedSummary, db_path: Path) -> None:
    print(f"資料庫：{db_path}")
    print(
        f"日線：共 {summary.bar_count} 根，"
        f"{summary.first_bar_date} ~ {summary.last_bar_date}（source={DEMO_SOURCE}）"
    )
    for symbol, count in summary.bars_by_symbol.items():
        print(f"  - {symbol}：{count} 根")
    print(
        f"持倉：新增 {len(summary.positions_created)} 筆"
        f"（{'、'.join(summary.positions_created) or '無'}）、"
        f"沿用既有 {len(summary.positions_kept)} 筆"
        f"（{'、'.join(summary.positions_kept) or '無'}）"
    )
    print(
        f"警示規則：新增 {len(summary.rules_created)} 條"
        f"（{'、'.join(summary.rules_created) or '無'}）、"
        f"沿用既有 {len(summary.rules_kept)} 條"
        f"（{'、'.join(summary.rules_kept) or '無'}）"
    )
    print("提示：呼叫 POST /api/alerts/evaluate 才會產生警示事件。")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m app.demo.seed",
        description=(
            "產生（或清除）離線示範用的合成資料；資料不可用於任何真實決策。"
            "若目標資料庫在相同標的與日期上已有非示範來源的日線，會拒絕執行（結束碼 1）"
            "而不覆蓋任何資料。"
        ),
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="只清除示範資料（source=demo_synthetic 的日線、帶有示範標記的持倉與警示規則）後結束",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="覆寫資料庫路徑；未指定時沿用 STOCK_DESK_DB_PATH（預設 ./data/stock-desk.db）",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db_path) if args.db_path is not None else resolve_db_path()
    cache = PriceBarCache(db_path)
    positions = PositionStore(db_path)
    alerts = AlertStore(db_path)

    _print_banner()
    if args.reset:
        removed = reset_demo(cache=cache, positions=positions, alerts=alerts)
        print(f"資料庫：{db_path}")
        print(
            f"已清除：日線 {removed.bars_deleted} 根、持倉 {removed.positions_deleted} 筆、"
            f"警示規則 {removed.rules_deleted} 條。"
        )
        print("（警示事件為 append-only 紀錄，依既有設計保留。）")
    else:
        try:
            summary = seed_demo(cache=cache, positions=positions, alerts=alerts)
        except DemoSeedConflictError as error:
            # Nothing was written, so the closing banner would be a lie about
            # what is now in that database. Report on stderr and fail the run.
            print(str(error), file=sys.stderr)
            return 1
        _print_seed_summary(summary, db_path)
    _print_banner()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the CLI
    raise SystemExit(main())
