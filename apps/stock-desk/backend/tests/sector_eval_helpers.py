"""Synthetic whole-market panels for the basket / evaluator / research tests (offline).

:func:`synthetic_market` builds a forward point-in-time history the way the
market DB would hold it: one ``bars`` / ``listing`` / ``classification`` /
``dividend_announce`` run per session, recorded at 18:00 Asia/Taipei that day,
with a warm-up stretch of bars before D0 (no listing / classification then,
exactly like the pre-D0 warm-up of ADR-0012 D-3).

Built with numpy so a few thousand rows cost milliseconds. Events are opt-in:

* ex-dividend events (announced ten sessions ahead, reference price
  ``previous close - dividend`` on the ex-date, ``change`` against it);
* a delisting (a name leaves bars and listing from one session on);
* a reclassification (a name moves sector from one session on);
* late corrections (a second bars run for a session, recorded the next morning).

Return-generating knobs:

* ``sector_persistence`` -- each sector's daily drift is an AR(1) with this
  coefficient, so past sector strength predicts future strength (momentum);
  0 leaves no sector effect at all;
* ``small_sector_drift`` -- a constant daily drift for the smallest sectors
  (a structural, time-invariant effect the time-shift placebo must flag).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from app.backtest import sector_eval
from app.backtest.sector_eval import BoardFingerprint
from app.data.panel import (
    BARS_COLUMNS,
    CLASSIFICATION_COLUMNS,
    EX_DIVIDEND_COLUMNS,
    LISTING_COLUMNS,
    RUNS_COLUMNS,
    TAIPEI,
    MarketPanel,
    PanelFrames,
)
from app.sectors.definition import SECTOR_MOMENTUM_V1

START = date(2025, 1, 6)  # a Monday


def weekdays(count: int, start: date = START) -> list[date]:
    days: list[date] = []
    cursor = start
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def taipei(day: date, hour: int = 18, minute: int = 0) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(day, time(hour, minute), tzinfo=TAIPEI)).tz_convert("UTC")


#: Sector code -> number of members; "20" is 其他業 (B_EW only, never ranked).
DEFAULT_SECTORS: Mapping[str, int] = {
    "01": 5,
    "02": 6,
    "03": 7,
    "12": 9,
    "14": 12,
    "24": 16,
    "28": 20,
    "20": 6,
}


@dataclass(frozen=True)
class DividendEvent:
    symbol: str
    ex_date: date
    dividend: float


@dataclass
class SyntheticMarket:
    panel: MarketPanel
    calendar: tuple[date, ...]
    d0: date
    members: Mapping[str, tuple[str, ...]]
    dividends: tuple[DividendEvent, ...] = ()
    delisted: str | None = None
    delisted_from: date | None = None
    moved: str | None = None
    moved_from: date | None = None
    moved_to_code: str | None = None
    extra: dict[str, object] = field(default_factory=dict)


def synthetic_market(
    *,
    seed: int = 0,
    sectors: Mapping[str, int] = DEFAULT_SECTORS,
    warmup: int = 70,
    forward: int = 160,
    n_dividends: int = 6,
    delist: bool = True,
    reclassify: bool = True,
    late_corrections: bool = True,
    sector_persistence: float = 0.0,
    sector_vol: float = 0.004,
    stock_vol: float = 0.015,
    small_sector_drift: float = 0.0,
    source: str = "twse_snapshot",
) -> SyntheticMarket:
    rng = np.random.default_rng(seed)
    days = weekdays(warmup + forward)
    n_days = len(days)
    d0 = days[warmup]
    codes = list(sectors)
    members = {code: tuple(f"{code}{i:02d}" for i in range(size)) for code, size in sectors.items()}
    symbols = [symbol for code in codes for symbol in members[code]]
    code_of = {symbol: code for code in codes for symbol in members[code]}
    n_sym = len(symbols)

    # Sector drift: AR(1) with ``sector_persistence``; zero-mean when 0.
    drift = np.zeros((n_days, len(codes)))
    shocks = rng.normal(0.0, sector_vol, (n_days, len(codes)))
    for day in range(1, n_days):
        drift[day] = sector_persistence * drift[day - 1] + shocks[day]
    small = sorted(codes, key=lambda code: sectors[code])[:2]
    column = {code: index for index, code in enumerate(codes)}
    sector_ret = np.column_stack([drift[:, column[code_of[s]]] for s in symbols])
    if small_sector_drift:
        for index, symbol in enumerate(symbols):
            if code_of[symbol] in small:
                sector_ret[:, index] += small_sector_drift
    overnight = rng.normal(0.0, stock_vol * 0.5, (n_days, n_sym)) + sector_ret * 0.5
    intraday = rng.normal(0.0, stock_vol * 0.8, (n_days, n_sym)) + sector_ret * 0.5

    # Dividend events in the forward period, away from the edges.
    events: list[DividendEvent] = []
    candidates = rng.permutation(n_sym)[:n_dividends]
    for index in candidates:
        day = int(rng.integers(warmup + 15, n_days - 10))
        events.append(DividendEvent(symbols[index], days[day], 2.0))
    ex_by = {(e.symbol, e.ex_date): e for e in events}

    delisted = symbols[-1] if delist else None
    delisted_from = days[warmup + forward // 2] if delist else None
    moved = members[codes[3]][0] if reclassify else None
    moved_from = days[warmup + forward // 3] if reclassify else None
    moved_to = codes[4] if reclassify else None

    opens = np.zeros((n_days, n_sym))
    closes = np.zeros((n_days, n_sym))
    changes = np.full((n_days, n_sym), np.nan)
    prev = np.full(n_sym, 50.0) * np.exp(rng.normal(0.0, 0.3, n_sym))
    for day in range(n_days):
        reference = prev.copy()
        for index, symbol in enumerate(symbols):
            event = ex_by.get((symbol, days[day]))
            if event is not None:
                reference[index] = prev[index] - event.dividend
        opens[day] = reference * np.exp(overnight[day])
        closes[day] = np.round(opens[day] * np.exp(intraday[day]), 2)
        opens[day] = np.round(opens[day], 2)
        changes[day] = np.round(closes[day] - reference, 2)
        prev = closes[day]

    run_rows: list[dict[str, object]] = []
    bar_parts: list[pd.DataFrame] = []
    listing_parts: list[pd.DataFrame] = []
    class_parts: list[pd.DataFrame] = []
    dividend_rows: list[dict[str, object]] = []
    counter = 0

    def new_run(kind: str, day: date, recorded: pd.Timestamp, run_source: str) -> str:
        nonlocal counter
        counter += 1
        run_id = f"{kind[:2]}{counter:06d}"
        run_rows.append(
            {
                "run_id": run_id,
                "kind": kind,
                "session_date": day,
                "recorded_at": recorded,
                "source": run_source,
                "status": "ok",
                "row_count": n_sym,
                "expected_count": n_sym,
            }
        )
        return run_id

    for day_index, day in enumerate(days):
        recorded = taipei(day)
        warm = day_index < warmup
        live = np.array(
            [
                not (s == delisted and delisted_from is not None and day >= delisted_from)
                for s in symbols
            ]
        )
        bars_source = "finmind_warmup" if warm else source
        bars_run = new_run("bars", day, recorded, bars_source)
        live_symbols = [s for s, ok in zip(symbols, live, strict=True) if ok]
        bar_parts.append(
            pd.DataFrame(
                {
                    "run_id": bars_run,
                    "session_date": [day] * len(live_symbols),
                    "recorded_at": recorded,
                    "source": bars_source,
                    "symbol": live_symbols,
                    "open": opens[day_index][live],
                    "high": np.maximum(opens[day_index], closes[day_index])[live],
                    "low": np.minimum(opens[day_index], closes[day_index])[live],
                    "close": closes[day_index][live],
                    "shares": 100_000,
                    "traded_value": 5e7,
                    "change": changes[day_index][live],
                }
            )
        )
        if late_corrections and not warm and day_index % 11 == 0 and day_index + 1 < n_days:
            late = new_run("bars", day, taipei(days[day_index + 1], 9), bars_source)
            bar_parts.append(
                bar_parts[-1].assign(
                    run_id=late,
                    recorded_at=taipei(days[day_index + 1], 9),
                    close=(bar_parts[-1]["close"] * 1.001).round(2),
                )
            )
        if warm:
            continue
        listing_run = new_run("listing", day, recorded, "twse_t187ap03_L")
        listing_parts.append(
            pd.DataFrame(
                {
                    "run_id": listing_run,
                    "session_date": [day] * len(live_symbols),
                    "recorded_at": recorded,
                    "symbol": live_symbols,
                    "security_type": "common_stock",
                }
            )
        )
        class_run = new_run("classification", day, recorded, "twse_t187ap03_L")
        sector_codes = [
            moved_to
            if (s == moved and moved_from is not None and day >= moved_from)
            else code_of[s]
            for s in live_symbols
        ]
        class_parts.append(
            pd.DataFrame(
                {
                    "run_id": class_run,
                    "session_date": [day] * len(live_symbols),
                    "recorded_at": recorded,
                    "symbol": live_symbols,
                    "sector_code": sector_codes,
                    "sector_name": [f"S{c}" for c in sector_codes],
                }
            )
        )
        dividend_run = new_run("dividend_announce", day, recorded, "twse_twt48u")
        for event in events:
            ahead = days.index(event.ex_date) - day_index
            if 0 <= ahead <= 10:
                dividend_rows.append(
                    {
                        "run_id": dividend_run,
                        "session_date": day,
                        "recorded_at": recorded,
                        "symbol": event.symbol,
                        "ex_date": event.ex_date,
                    }
                )

    frames = PanelFrames(
        bars=pd.concat(bar_parts, ignore_index=True).loc[:, list(BARS_COLUMNS)],
        listing=pd.concat(listing_parts, ignore_index=True).loc[:, list(LISTING_COLUMNS)],
        classification=pd.concat(class_parts, ignore_index=True).loc[
            :, list(CLASSIFICATION_COLUMNS)
        ],
        ex_dividend=pd.DataFrame(dividend_rows, columns=list(EX_DIVIDEND_COLUMNS)),
        runs=pd.DataFrame(run_rows, columns=list(RUNS_COLUMNS)),
    )
    return SyntheticMarket(
        panel=MarketPanel(frames),
        calendar=tuple(days),
        d0=d0,
        members=members,
        dividends=tuple(events),
        delisted=delisted,
        delisted_from=delisted_from,
        moved=moved,
        moved_from=moved_from,
        moved_to_code=moved_to,
    )


def replace_frame(panel: MarketPanel, **frames: pd.DataFrame) -> MarketPanel:
    """A new panel with some raw frames swapped (for teeth tests)."""
    current = panel.frames
    parts = {
        name: frames.get(name, getattr(current, name))
        for name in ("bars", "listing", "classification", "ex_dividend", "runs")
    }
    return MarketPanel(PanelFrames(**parts))


def boards_for(market: SyntheticMarket, dates: Sequence[date]) -> dict[date, BoardFingerprint]:
    """What the services layer would hand the evaluator: each day's board, fingerprinted."""
    return {
        t: sector_eval.fingerprint_ranking(
            sector_eval.decide(market.panel.as_of(t), SECTOR_MOMENTUM_V1).ranking
        )
        for t in dates
    }
