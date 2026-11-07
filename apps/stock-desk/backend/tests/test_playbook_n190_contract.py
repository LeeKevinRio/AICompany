"""ADR-0040 附錄 B T15: the checks behind Decision 1～6 and 15.

QB-3 (truth table), QB-4 (a) single implementation, (c) the data layer's
contract on its three ``cached_stale`` exits, QB-5 (signature, no switch),
QB-6 (four statuses), QB-13 (B-1 unreachable), QB-15 (TW only), QB-21 (the
ledger badge). QB-4 (b) is ``test_playbook_n190_ttl_plumbing.py``, (d) the spy
in ``test_playbook_n190_usable_cache.py``; QB-8 / QB-19 are there too, QB-12 in
``test_playbook_n190_marks.py``.
"""

from __future__ import annotations

import ast
import inspect
import itertools
import random
import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.cache import PriceBarCache
from app.data.freshness import expected_session, policy_for
from app.data.interface import DataStatus, ProviderResult
from app.data.service import MarketDataService
from app.playbook import engine as engine_module
from app.playbook import service as service_module
from app.playbook import wording
from app.playbook.engine import evaluate, is_usable
from app.playbook.models import MarketSnapshot
from tests import playbook_helpers as helper
from tests.market_service_helpers import equity_service
from tests.n190_helpers import MON, TPE, TUE, TwseLive, flat

APP = Path(service_module.__file__).resolve().parents[1]
FRONTEND = APP.parents[1] / "frontend"

# --- QB-3 ----------------------------------------------------------------------------------

STATUSES = ("fresh", "backup", "cached_stale", "unavailable", "something_else")
SOURCES = ("twse", "yfinance", "demo_synthetic", "none")
TTLS: tuple[bool | None, ...] = (True, False, None)


def _decision_1(status: str, source: str, ttl: bool | None) -> bool:
    """ADR-0040 Decision 1, written out: (a) and ((b) or (c))."""
    if source == "demo_synthetic":
        return False
    return status in ("fresh", "backup") or (status == "cached_stale" and ttl is True)


@pytest.mark.parametrize(
    ("status", "source", "ttl"), list(itertools.product(STATUSES, SOURCES, TTLS))
)
def test_qb3_is_usable_is_decision_1_on_every_combination(
    status: str, source: str, ttl: bool | None
) -> None:
    assert is_usable(status, source, is_within_ttl=ttl) is _decision_1(status, source, ttl)


def test_qb3_the_table_has_exactly_the_three_cached_usable_cases() -> None:
    usable_cached = [
        (source, ttl)
        for source, ttl in itertools.product(SOURCES, TTLS)
        if is_usable("cached_stale", source, is_within_ttl=ttl)
    ]
    assert usable_cached == [("twse", True), ("yfinance", True), ("none", True)]


# --- QB-5 ----------------------------------------------------------------------------------


def test_qb5_the_signature_is_decision_2_verbatim_and_has_no_default() -> None:
    signature = inspect.signature(is_usable)
    assert (
        str(signature)
        == "(status: 'str', source: 'str', *, is_within_ttl: 'bool | None') -> 'bool'"
    )
    parameter = signature.parameters["is_within_ttl"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        is_usable("fresh", "twse")  # type: ignore[call-arg]


def test_qb5_no_flag_environment_or_parameter_reaches_the_decision() -> None:
    source = inspect.getsource(is_usable)
    for banned in ("environ", "getenv", "settings", "RuleParams", "params", "market", "clock"):
        assert banned not in source, banned
    tree = ast.parse(Path(engine_module.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "os" not in imported


# --- QB-4 (a) ------------------------------------------------------------------------------

FORBIDDEN_NAMES = frozenset(
    {"judge", "expected_session", "latest_completed_session", "Verdict", "policy_for"}
)


def _names(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            found.update(alias.name.split(".")[-1] for alias in node.names)
            found.update(alias.asname for alias in node.names if alias.asname)
            if isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
    return found


@pytest.mark.parametrize(
    "path", sorted((APP / "playbook").rglob("*.py")), ids=lambda path: path.name
)
def test_qb4a_the_playbook_never_judges_a_session_itself(path: Path) -> None:
    """Decision 15: the one judgement is the data layer's ``judge()``, read as ``is_within_ttl``."""
    names = _names(ast.parse(path.read_text(encoding="utf-8")))
    assert names & FORBIDDEN_NAMES == set()
    assert [name for name in names if name.endswith("_POLICY")] == []
    assert "app.data.freshness" not in names


# --- QB-4 (c): the data layer's contract, three exits ---------------------------------------

#: Taipei wall times across the cutoff, the cooldown and a weekend.
CLOCKS = [
    datetime.combine(day, time(hh, mm), tzinfo=TPE)
    for day in (MON, TUE, date(2026, 8, 15), date(2026, 8, 16))
    for hh, mm in ((9, 0), (13, 45), (14, 59), (15, 0), (15, 20), (16, 5), (18, 30))
]
#: ``requested_end`` relative to the clock's date: today, a past end, a future end.
END_SHIFTS = (0, -3, 1)


class _Ladder:
    def __init__(self, tmp_path: Path, *, cache_first: bool) -> None:
        self.now = CLOCKS[0]
        self.cache = PriceBarCache(db_path=tmp_path / f"cache-{cache_first}.db")
        self.live = TwseLive(flat({"2330": "100"}))
        self.service: MarketDataService = equity_service(
            primary=self.live, cache=self.cache, cache_first=cache_first, clock=lambda: self.now
        )

    def at(self, now: datetime, *, published: date, failing: bool) -> None:
        self.now = now
        self.live.available_through = published
        self.live.failing = failing


def _holds_latest(result: ProviderResult, *, end: date, now: datetime) -> bool:
    last = max(bar.date for bar in result.bars)
    return last >= expected_session(policy_for("TW"), requested_end=end, now=now)


Exit = Callable[[_Ladder, date, date], ProviderResult]


def _exits(tmp_path: Path) -> dict[str, tuple[_Ladder, Exit]]:
    layered = _Ladder(tmp_path, cache_first=True)
    plain = _Ladder(tmp_path, cache_first=False)
    return {
        # layer 0: cache_first, answered with no live call.
        "layer0": (
            layered,
            lambda ladder, start, end: ladder.service.get_daily_bars("2330", "TW", start, end),
        ),
        # the degrade-to-cache rung: every live rung declined.
        "fallback": (
            plain,
            lambda ladder, start, end: ladder.service.get_daily_bars("2330", "TW", start, end),
        ),
        # get_cached_bars: never a live call.
        "cache_only": (
            layered,
            lambda ladder, start, end: ladder.service.get_cached_bars("2330", "TW", start, end),
        ),
    }


def test_qb4c_cached_stale_within_ttl_always_holds_the_expected_session(tmp_path: Path) -> None:
    """Context 4 (風控 C-4): every exit that can say ``is_within_ttl=True`` means ④.

    Must not be deleted or weakened (ADR-0040 Decision 16 第 3 點, C-7).
    """
    exits = _exits(tmp_path)
    rng = random.Random(40)
    seen: dict[str, int] = {name: 0 for name in exits}
    checked = 0
    for name, (ladder, call) in exits.items():
        for now in CLOCKS:
            for shift in END_SHIFTS:
                end = now.date() + timedelta(days=shift)
                start = end - timedelta(days=rng.choice((20, 180, 540)))
                published = now.date() - timedelta(days=rng.choice((0, 1, 3)))
                failing = name == "fallback" or rng.random() < 0.3
                # A live answer first, so the cache and its fetch log exist.
                ladder.at(
                    now - timedelta(hours=rng.choice((0, 1, 2, 30))),
                    published=published,
                    failing=False,
                )
                ladder.service.get_daily_bars("2330", "TW", start, end)
                ladder.at(now, published=published, failing=failing)
                calls_before = len(ladder.live.calls)
                result = call(ladder, start, end)
                if name == "layer0" and len(ladder.live.calls) != calls_before:
                    continue  # the ladder ran: not the layer-0 exit
                if result.status is DataStatus.CACHED_STALE and result.is_within_ttl is True:
                    seen[name] += 1
                    checked += 1
                    assert _holds_latest(result, end=end, now=now), (name, now, start, end)
                if result.status is DataStatus.CACHED_STALE:
                    assert result.is_within_ttl is not None, (name, now)
    print("QB-4(c) cached_stale + ttl True per exit:", seen)
    assert all(count > 0 for count in seen.values()), seen
    assert checked >= 10


def test_qb4c_the_playbook_never_takes_the_cache_only_exit() -> None:
    """C-4: ``get_cached_bars`` is covered above; the playbook does not call it anyway."""
    source = (APP / "playbook" / "service.py").read_text(encoding="utf-8")
    assert "get_cached_bars" not in source


# --- QB-6, QB-15 -----------------------------------------------------------------------------


def test_qb6_there_are_still_four_data_statuses() -> None:
    assert sorted(status.value for status in DataStatus) == [
        "backup",
        "cached_stale",
        "fresh",
        "unavailable",
    ]


def test_qb15_the_playbook_trades_tw_only() -> None:
    """Decision 6: changing the market reopens ADR-0040; ``is_usable`` takes no market."""
    assert service_module.PLAYBOOK_MARKET == "TW"
    assert "market" not in inspect.signature(is_usable).parameters


# --- QB-13 -----------------------------------------------------------------------------------


def _random_snapshot(rng: random.Random, symbol: str) -> MarketSnapshot:
    close = Decimal(rng.randint(40, 160))
    return MarketSnapshot(
        symbol=symbol,
        data_date=helper.TUESDAY,
        close=close,
        change_pct=Decimal(rng.randint(-9, 9)),
        ma25=Decimal(rng.randint(60, 140)),
        bias25=Decimal(rng.randint(-20, 20)),
        data_status="cached_stale",
        source=rng.choice(("twse", "tpex", "finmind")),
        is_within_ttl=True,
    )


@pytest.mark.parametrize("seed", range(60))
def test_qb13_a_cache_within_ttl_never_gets_a_gap_sentence(seed: int) -> None:
    """Decision 10: B-1's trigger is ``is_usable``, so the sentences it replaced never appear."""
    rng = random.Random(seed)
    symbols = [f"23{index:02d}" for index in range(rng.randint(1, 4))]
    markets = {symbol: _random_snapshot(rng, symbol) for symbol in symbols}
    batches = [
        helper.batch(symbol, batch_no, cost=str(rng.randint(50, 150)))
        if rng.random() < 0.6
        else helper.planned(symbol, batch_no)
        for symbol in symbols
        for batch_no in (1, 2, 3)
    ]
    index = helper.index(
        status="cached_stale",
        close=str(rng.randint(18000, 21000)),
        days_below=rng.randint(0, 5),
    ).model_copy(update={"is_within_ttl": True})
    evaluation = evaluate(
        data_date=helper.TUESDAY,
        calendar=helper.calendar(),
        params=helper.params(),
        index=index,
        markets=markets,
        batches=batches,
        symbols={},
        portfolio=helper.portfolio(),
    )
    for symbol, snapshot in markets.items():
        for template in (wording.DATA_GAP_NOTE, wording.DATA_GAP_HOLDING_NOTE):
            gap = template.format(symbol=symbol, status="cached_stale", source=snapshot.source)
            assert gap not in evaluation.warnings
    assert wording.INDEX_DATA_GAP_NOTE.format(status="cached_stale", source="yfinance") not in (
        evaluation.warnings
    )


# --- QB-21 -----------------------------------------------------------------------------------


def test_qb21_the_ledger_badge_is_never_told_the_cache_is_current() -> None:
    """C-8: on the ledger path ``isWithinTtl`` stays ``null`` -- no ``true``, nothing derived."""
    ledger = (FRONTEND / "app" / "playbook" / "DirectiveLedger.tsx").read_text(encoding="utf-8")
    assert re.findall(r"isWithinTtl=\{([^}]*)\}", ledger) == ["null"]
    assert "isWithinTtl={true}" not in ledger
