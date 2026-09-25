"""T-5 (methodology T1), CI half: the future cannot change a decision.

For 50 random decision dates on a synthetic market with late corrections,
reclassification, a delisting, a new listing, missing bars and ex-dividend
events, every row recorded after ``cutoff(t)`` -- prices, listing,
classification, events, runs -- is replaced with noise (and extra noise rows
are added). ``calculation_set``, ``rank_sectors`` and ``list_constituents``
for day ``t`` must come out bit-for-bit identical.

Also here: the private hindsight entry point may only be referenced from
``app/data/panel.py`` and ``app/research/`` (ADR-0012 D-14, C-27).
"""

from __future__ import annotations

import ast
import random
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from app.data.panel import MarketPanel, PanelFrames, cutoff
from app.sectors import constituents, coverage, ranking, universe
from app.sectors.definition import SECTOR_MOMENTUM_V1 as V1
from tests.import_graph import APP_ROOT
from tests.sectors_helpers import PanelBuilder, canonical, taipei, weekdays

SEED = 20260925
N_SESSIONS = 140
N_DECISIONS = 50


def _synthetic_market(rng: random.Random) -> MarketPanel:
    days = weekdays(N_SESSIONS)
    sectors = {
        "01": "水泥工業",
        "02": "食品工業",
        "12": "汽車工業",
        "24": "半導體業",
        "20": "其他業",
    }
    symbols = {code: [f"{code}{i:02d}" for i in range(8)] for code in sectors}
    price = {s: 50.0 + rng.random() * 50 for group in symbols.values() for s in group}
    delisted = "2403"  # disappears after session 80
    newcomer = "2499"  # listed from session 30
    moved = "0105"  # reclassified 01 -> 02 from session 70
    builder = PanelBuilder()
    for n, day in enumerate(days):
        bars = builder.run("bars", day)
        listing = builder.run("listing", day)
        classes = builder.run("classification", day)
        dividend = builder.run("dividend_announce", day) if rng.random() > 0.05 else None
        roster = [s for group in symbols.values() for s in group]
        if n >= 30:
            roster.append(newcomer)
            price.setdefault(newcomer, 30.0)
        for symbol in roster:
            if symbol == delisted and n > 80:
                continue
            price[symbol] *= 1.0 + rng.uniform(-0.04, 0.04)
            if rng.random() > 0.03:  # sporadic missing bars
                builder.bar(bars, day, symbol, round(price[symbol], 2), traded_value=3e7)
            builder.listed(listing, day, symbol)
            code = symbol[:2] if symbol != newcomer else "24"
            if symbol == moved and n >= 70:
                code = "02"
            builder.classified(classes, day, symbol, code, sectors[code])
            if dividend is not None and rng.random() < 0.01:
                ex = day + timedelta(days=rng.randint(1, 10))
                builder.announced(dividend, day, symbol, ex)
        # A late correction by the backup source, visible only from the next day.
        if n % 7 == 0 and n + 1 < len(days):
            late = builder.run("bars", day, source="finmind", recorded=taipei(days[n + 1], 9))
            for symbol in rng.sample(roster, 5):
                builder.bar(late, day, symbol, round(price[symbol] * 1.01, 2), source="finmind")
            fix = builder.run("bars", day, recorded=taipei(days[n + 1], 10))
            for symbol in rng.sample(roster, 3):
                builder.bar(fix, day, symbol, round(price[symbol] * 0.99, 2))
    return builder.panel()


def _noise(frames: PanelFrames, t: date, rng: random.Random) -> PanelFrames:
    cut = cutoff(t)
    out: dict[str, pd.DataFrame] = {}
    for name in ("bars", "listing", "classification", "ex_dividend", "runs"):
        frame: pd.DataFrame = getattr(frames, name).copy()
        future = frame["recorded_at"] > cut
        n = int(future.sum())
        if n:
            frame.loc[future, "session_date"] = [
                t - timedelta(days=rng.randint(0, 30)) for _ in range(n)
            ]
            if "symbol" in frame:
                frame.loc[future, "symbol"] = [
                    f"{rng.choice(['01', '24'])}0{rng.randint(0, 9)}" for _ in range(n)
                ]
            if name == "bars":
                for column in ("open", "high", "low", "close", "traded_value"):
                    frame.loc[future, column] = [rng.uniform(1, 1e6) for _ in range(n)]
                frame.loc[future, "source"] = "twse_snapshot"
            if name == "classification":
                frame.loc[future, "sector_code"] = [
                    rng.choice(["01", "02", "24"]) for _ in range(n)
                ]
            if name == "ex_dividend":
                frame.loc[future, "ex_date"] = [
                    t - timedelta(days=rng.randint(0, 5)) for _ in range(n)
                ]
            if name == "runs":
                frame.loc[future, "status"] = "ok"
        out[name] = frame
    # Extra future rows claiming to describe day t itself.
    extra_run = pd.DataFrame(
        [
            {
                "run_id": "noise-run",
                "kind": "bars",
                "session_date": t,
                "recorded_at": cut + pd.Timedelta(seconds=1),
                "source": "twse_snapshot",
                "status": "ok",
                "row_count": 1,
                "expected_count": 1,
            }
        ]
    )
    extra_bar = pd.DataFrame(
        [
            {
                "run_id": "noise-run",
                "session_date": t,
                "recorded_at": cut + pd.Timedelta(seconds=1),
                "source": "twse_snapshot",
                "symbol": "0100",
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "shares": 1,
                "traded_value": 1.0,
                "change": 0.0,
            }
        ]
    )
    out["runs"] = pd.concat([out["runs"], extra_run], ignore_index=True)
    out["bars"] = pd.concat([out["bars"], extra_bar], ignore_index=True)
    return PanelFrames(**out)


def _decision(market: MarketPanel, t: date) -> object:
    view = market.as_of(t)
    calc = universe.calculation_set(view, V1)
    board = ranking.rank_sectors(calc, V1)
    listed = {
        row.sector_code: constituents.list_constituents(calc, row.sector_code)
        for row in board.ranked
    }
    return canonical(
        (calc, board, listed, coverage.ex_dividend_feed_covered(view, V1), view.sessions)
    )


def test_future_noise_never_changes_a_decision() -> None:
    rng = random.Random(SEED)
    market = _synthetic_market(rng)
    sessions = sorted(set(market.frames.bars["session_date"]))
    decisions = rng.sample(sessions[62:], N_DECISIONS)
    ranked_somewhere = False
    for t in decisions:
        clean = _decision(market, t)
        noisy = _decision(MarketPanel(_noise(market.frames, t, rng)), t)
        assert noisy == clean, f"decision on {t} changed under future noise"
        ranked_somewhere |= bool(
            ranking.rank_sectors(universe.calculation_set(market.as_of(t), V1), V1).ranked
        )
    assert ranked_somewhere, "the synthetic market must actually rank something"


def test_the_noise_is_not_vacuous() -> None:
    """Teeth: the same noise applied to *visible* rows does change the decision."""
    rng = random.Random(SEED)
    market = _synthetic_market(rng)
    t = sorted(set(market.frames.bars["session_date"]))[90]
    frames = market.frames
    bars = frames.bars.copy()
    visible = bars["session_date"] == t
    bars.loc[visible, "close"] = bars.loc[visible, "close"] * 1.5
    assert _decision(MarketPanel(replace(frames, bars=bars)), t) != _decision(market, t)


def test_the_view_refuses_the_future_it_filtered_out() -> None:
    market = _synthetic_market(random.Random(SEED))
    sessions = sorted(set(market.frames.bars["session_date"]))
    view = market.as_of(sessions[80])
    with pytest.raises(LookupError):
        view.field_matrix("close", [sessions[81]])


def _names_used(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.name.split(".")[-1])
            if node.asname:
                names.add(node.asname)
    return names


def test_hindsight_entry_point_is_reachable_only_from_panel_and_research() -> None:
    allowed = {APP_ROOT / "data" / "panel.py"}
    offenders = [
        str(path.relative_to(APP_ROOT))
        for path in APP_ROOT.rglob("*.py")
        if path not in allowed
        and "research" not in path.relative_to(APP_ROOT).parts
        and "_hindsight_view" in _names_used(path)
    ]
    assert offenders == []


def test_hindsight_scan_has_teeth(tmp_path: Path) -> None:
    leak = tmp_path / "leak.py"
    leak.write_text("from app.data.panel import _hindsight_view\n", encoding="utf-8")
    assert "_hindsight_view" in _names_used(leak)
