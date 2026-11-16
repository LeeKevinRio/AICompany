"""The D-7 real-data pipeline acceptance: reading the ``^TWII`` bars (ADR-0030 supplement 6).

This batch holds only the pure functions that turn a byte copy of the cache
database into the ``bars`` argument of
:func:`tests.forecast_pipeline_harness.run_acceptance` (supplement 6 points
1-2, point 4 (c)); the outer flow -- copying the database, the work folder,
the paste-back whitelist, cleanup -- is not here, and nothing runs on import.

* :func:`read_twii_bars` -- opens **only the copy it is given** (``sqlite3``
  URI ``mode=ro``, plus ``immutable=1`` when the copy has no ``-wal``;
  ``PRAGMA query_only``), SELECTs the eight columns of the
  ``^TWII`` / ``TW`` rows of ``price_bars_cache`` (never ``as_of`` or
  ``fetched_at``), maps each row the way ``PriceBarCache.get`` does and
  stamps ``as_of`` at 20:00 Taipei on the bar's own session, the rule of
  ``synthetic_series``' default;
* :func:`required_sessions` / :func:`check_depth` -- the depth stop:
  N_SNAPSHOT plus :data:`WINDOW_SESSIONS` sessions before the run date, both
  from program derivations;
* :func:`bars_sha256` -- ``app.forecast.canonical.content_sha256`` of the
  injected series (K-6; no serialisation of its own).

Every stop raises :class:`AcceptanceStop` with one kind of a closed set; the
exception carries a fixed sentence and no value, count or path.

Boundaries (supplement 6 point 1 (c), TA C-2): no import of ``app.services``,
``app.data.cache``, ``app.data.service`` or ``app.data.providers``; no network.
The scope of supplement 6 point 1 (b) is this script alone (risk RC-158b).
"""

# ruff: noqa: E402 -- the app / tests imports must follow the sys.path step below.

from __future__ import annotations

import sys
from pathlib import Path

# Run as ``python -I scripts/pipeline_acceptance_real.py``: isolated mode puts
# neither the working directory nor this folder's parent on ``sys.path``, so
# the backend directory is added here -- only when it is the one holding
# ``app/`` -- before the ``app`` / ``tests`` imports below. Silent on import.
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if (_BACKEND_DIR / "app" / "__init__.py").is_file() and str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import hashlib
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Final, Literal, get_args

from app.advice.banned_phrases import BANNED_PHRASES
from app.data.interface import PriceBar
from app.dirdef.definition import DirectionDefinition
from app.dirdef.rules import OutlookRuleSet, load_ruleset
from app.forecast.canonical import content_sha256
from app.outlook.engine import n_snapshot
from app.outlook.inputs import SERIES_SYMBOL, _snapshot_bar
from tests.forecast_pipeline_harness import (
    HORIZONS,
    P0,
    P1,
    WINDOW_SESSIONS,
    PlaceholderRules,
)
from tests.outlook_helpers import TAIPEI

#: The market of the ``^TWII`` rows read.
SERIES_MARKET: Final = "TW"
#: The one source the real run accepts (supplement 6 point 1 (e); F-5 otherwise).
EXPECTED_SOURCE: Final = "yfinance"
#: Sources of the offline demo seeder start with this (a weekday grid, not a real series).
DEMO_SOURCE_PREFIX: Final = "demo"
#: Supplement 6 point 2: the injected stamp hour, equal to ``synthetic_series``' default.
STAMP_HOUR: Final = 20

#: The single SELECT of this script: the eight columns of supplement 6 point 1 (a).
_SELECT_SQL: Final = """
SELECT trade_date, open, high, low, close, volume, currency, source
FROM price_bars_cache
WHERE symbol = ? AND market = ?
ORDER BY trade_date ASC
"""

StopKind = Literal["no_rows", "unparseable_row", "demo_source", "foreign_source", "cache_short"]

#: One fixed ASCII sentence per stop kind; none carries a value, a count or a path.
STOP_SENTENCES: Final[Mapping[StopKind, str]] = MappingProxyType(
    {
        "no_rows": "STOP: the cache copy holds no TWII rows.",
        "unparseable_row": "STOP: a TWII row of the cache copy cannot be read.",
        "demo_source": "STOP: a TWII row of the cache copy comes from the demo seeder.",
        "foreign_source": "STOP: a TWII row of the cache copy is not from the expected source.",
        "cache_short": "STOP: the cache copy holds too few TWII sessions before today.",
    }
)


class AcceptanceStop(Exception):
    """A fail-closed stop of supplement 6 point 1 (e): a closed ``kind``, a fixed sentence."""

    def __init__(self, kind: StopKind) -> None:
        if kind not in get_args(StopKind):
            raise ValueError("unknown stop kind")
        super().__init__(STOP_SENTENCES[kind])
        self.kind: StopKind = kind


# --- reading the copy ---------------------------------------------------------------------


def injected_as_of(day: date) -> datetime:
    """Supplement 6 point 2: 20:00 Asia/Taipei on the bar's own session."""
    return datetime.combine(day, time(STAMP_HOUR), TAIPEI)


def _bar(row: Sequence[Any]) -> PriceBar:
    """One row as ``PriceBarCache.get`` builds it, with the injected ``as_of``."""
    trade_date, open_str, high_str, low_str, close_str, volume, currency, source = row
    day = date.fromisoformat(trade_date)
    return PriceBar(
        symbol=SERIES_SYMBOL,
        market=SERIES_MARKET,
        date=day,
        open=Decimal(open_str),
        high=Decimal(high_str),
        low=Decimal(low_str),
        close=Decimal(close_str),
        volume=volume,
        currency=currency,
        as_of=injected_as_of(day),
        source=source,
    )


def copy_uri(copy_path: Path) -> str:
    """The read-only URI of the copy: ``mode=ro``, plus ``immutable=1`` when it has no ``-wal``.

    The cache database is in WAL mode, and a ``mode=ro`` connection to a WAL
    database creates a ``-wal`` and a ``-shm`` beside it when they are absent.
    Without a ``-wal`` the database file alone holds every committed row, so
    ``immutable=1`` reads it with no side file and no lock. With a copied
    ``-wal`` it must be read (it may hold rows not yet checkpointed into the
    file), so ``immutable`` -- which ignores the WAL -- is not used.
    """
    path = Path(copy_path).resolve()
    query = "mode=ro"
    if not path.with_name(f"{path.name}-wal").exists():
        query += "&immutable=1"
    return f"{path.as_uri()}?{query}"


def read_twii_bars(copy_path: Path) -> list[PriceBar]:
    """The ``^TWII`` bars of the database copy at ``copy_path``, ascending, stamps injected.

    Opens ``copy_path`` read-only (:func:`copy_uri`; a missing file is an
    ``sqlite3.Error`` and is never created) and only through this one
    connection. Raises :class:`AcceptanceStop` when there is no row, when any
    row cannot be read (no row is skipped), when any row comes from the demo
    seeder, or when any row's source is not :data:`EXPECTED_SOURCE`.
    """
    with closing(sqlite3.connect(copy_uri(copy_path), uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute(_SELECT_SQL, (SERIES_SYMBOL, SERIES_MARKET)).fetchall()
    if not rows:
        raise AcceptanceStop("no_rows")
    bars: list[PriceBar] = []
    for row in rows:
        try:
            bars.append(_bar(row))
        except (InvalidOperation, ValueError, TypeError):
            # ``from None``: the parser's own text would carry the row's value.
            raise AcceptanceStop("unparseable_row") from None
    if any(bar.source.startswith(DEMO_SOURCE_PREFIX) for bar in bars):
        raise AcceptanceStop("demo_source")
    if any(bar.source != EXPECTED_SOURCE for bar in bars):
        raise AcceptanceStop("foreign_source")
    return bars


# --- depth ----------------------------------------------------------------------------------


def placeholder_rulesets(rules: Iterable[PlaceholderRules]) -> list[OutlookRuleSet]:
    """Every horizon of the placeholder rule sets, through the real loader."""
    rulesets: list[OutlookRuleSet] = []
    for placeholder in rules:
        for horizon in HORIZONS:
            data = placeholder.rule_bytes(horizon)
            rulesets.append(
                load_ruleset(
                    data,
                    rules_sha256=hashlib.sha256(data).hexdigest(),
                    banned_phrases=BANNED_PHRASES,
                )
            )
    return rulesets


def required_sessions(
    definition: DirectionDefinition, rules: Iterable[PlaceholderRules] = (P0, P1)
) -> int:
    """N_SNAPSHOT of the placeholder rule sets plus :data:`WINDOW_SESSIONS` (point 1 (e))."""
    return n_snapshot(definition=definition, rulesets=placeholder_rulesets(rules)) + WINDOW_SESSIONS


def check_depth(bars: Sequence[PriceBar], *, run_date: date, required: int) -> None:
    """Stop (``cache_short``) with fewer than ``required`` sessions before ``run_date``."""
    if len({bar.date for bar in bars if bar.date < run_date}) < required:
        raise AcceptanceStop("cache_short")


# --- input identity -------------------------------------------------------------------------


def bars_sha256(bars: Iterable[PriceBar]) -> str:
    """Supplement 6 point 4 (c): ``content_sha256`` of the injected series.

    Each bar enters as the snapshot bar the recorder builds from it
    (``app.outlook.inputs._snapshot_bar``: D-5 point 1, ``fetched_at`` equal to
    ``as_of`` per supplement 2 point 3); the serialisation is ``content_sha256``'s own.
    """
    return content_sha256(_snapshot_bar(bar).as_mapping() for bar in bars)
