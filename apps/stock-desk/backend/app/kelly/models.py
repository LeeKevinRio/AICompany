"""Schemas for one Kelly input row, one import attempt, and one gate verdict.

The effective ``win_rate`` / ``payoff_ratio`` pair is what risk cap 5 consumes;
everything else on the row exists so a reader can tell where the pair came from
without a history table (ADR-0006 D-2). A row is keyed on ``(symbol, market)``
and only the latest one is kept, so the provenance columns travel *with* the
value rather than in a version chain.

Three rules shape these models:

* ``updated_at`` is never accepted from a caller. The server stamps it, so "how
  old is this input" is always the age of a real user action -- the same stance
  :class:`app.settings.models.NetWorthInput` takes on the reported net worth.
* out-of-range numbers are **rejected, not clamped** (約束 6). A probability of
  ``1.2`` is not a preference that could be nudged into range; a silently
  corrected one is a number the user would later believe they had entered.
* ``strategy_id`` is provenance, not part of the key (D-1), and is NULL for a
  manually entered pair -- a fabricated id would make a hand-typed number look
  like it came from a strategy.

Freshness (D-4) anchors on **different** facts per source: a manual input ages
from the moment it was typed, an imported one from the end of the out-of-sample
segment it was measured over. Anchoring an import on its run time would let a
re-run of a stale window present itself as fresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.positions.models import Market

#: ``manual`` -- typed by the user; ``backtest`` -- imported and untouched
#: since; ``backtest_overridden`` -- imported, then edited by hand (the import's
#: own numbers are kept alongside, see 約束 4).
KellySource = Literal["manual", "backtest", "backtest_overridden"]

#: ``fresh`` / ``ageing`` -- usable, the second one past the soft notice;
#: ``expired`` -- past the freshness rule. "Never entered" is the absence of a
#: row, not a state of one.
KellyFreshness = Literal["fresh", "ageing", "expired"]

#: One reason per gate, so a refusal names which door closed (D-3). The first
#: three are sample-size gates, the last three are upstream conditions the
#: import path checks before there is a sample to size.
KellyGateReasonCode = Literal[
    "low_round_trips",
    "low_win_trips",
    "low_loss_trips",
    "pb_none",
    "symbol_mismatch",
    "insufficient_data",
]

#: Days after which the input carries a "this is getting old" notice, and days
#: after which cap 5 stops using it. Deliberately **separate** constants from
#: :data:`app.advice.limits.NET_WORTH_SOFT_NOTICE_DAYS` and its stale partner
#: (D-4): the two happen to share their values today, but they answer different
#: questions and must be able to move apart without one dragging the other.
KELLY_SOFT_NOTICE_DAYS = 7
KELLY_STALE_AFTER_DAYS = 30

KELLY_WIN_RATE_OUT_OF_RANGE_MESSAGE = (
    "勝率必須大於 0 且小於 1（收到 {value}）。"
    "系統不會自行調整這個數字，請確認後重新輸入。"
)

KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE = (
    "賠率（平均獲利 ÷ 平均虧損）必須大於 0（收到 {value}）。"
    "系統不會自行調整這個數字，請確認後重新輸入。"
)

#: ISO calendar day, the shape every date-only provenance column is stored in.
#: Pinned by pattern so the freshness anchor can be parsed without a fallback.
_ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


def normalize_symbol(symbol: str) -> str:
    """The stored form of a ticker: trimmed and upper-cased (約束 1).

    The same normalisation ``app.advice.book_limits._group_positions`` applies
    when it groups holdings, so a Kelly input and the holding it constrains
    cannot end up under two spellings of one ticker.
    """
    return symbol.strip().upper()


def _check_win_rate(value: float) -> float:
    if not 0.0 < value < 1.0:
        raise ValueError(KELLY_WIN_RATE_OUT_OF_RANGE_MESSAGE.format(value=value))
    return value


def _check_payoff_ratio(value: float) -> float:
    if not value > 0.0:
        raise ValueError(KELLY_PAYOFF_RATIO_OUT_OF_RANGE_MESSAGE.format(value=value))
    return value


class KellyManualInput(BaseModel):
    """The ``PUT /api/kelly-inputs/{symbol}`` body: the pair, nothing else.

    No ``source``, no ``strategy_id``, no timestamp: this door only ever
    produces a manual input, and the two facts a client could otherwise dress
    up (where the number came from, when it was entered) are the server's to
    state.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Probability of a winning outcome, strictly inside (0, 1).
    win_rate: float
    #: Average win over average loss -- **not** profit factor (ADR-0006
    #: Context 事實 2: PF = (p/(1-p))·b, equal only at p = 0.5).
    payoff_ratio: float

    @field_validator("win_rate")
    @classmethod
    def _win_rate_in_range(cls, value: float) -> float:
        return _check_win_rate(value)

    @field_validator("payoff_ratio")
    @classmethod
    def _payoff_ratio_positive(cls, value: float) -> float:
        return _check_payoff_ratio(value)


class KellyInputRecord(BaseModel):
    """Everything about one Kelly input except when it was written.

    Flat on purpose: the field order is the column order of ``kelly_inputs``
    (:mod:`app.kelly.store` asserts the two agree), so a column added to one
    without the other is a startup failure rather than a silently dropped
    value.

    Every provenance field is optional because a manual input has none of them.
    ``backtest_win_rate`` / ``backtest_payoff_ratio`` hold what the import
    computed and are **never** overwritten by a later hand edit -- that is what
    makes ``backtest_overridden`` auditable rather than merely labelled.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- Key and effective values -------------------------------------------
    symbol: str = Field(min_length=1)
    market: Market
    win_rate: float
    payoff_ratio: float
    source: KellySource

    # --- What the import computed (kept even after a hand edit) --------------
    backtest_win_rate: float | None = None
    backtest_payoff_ratio: float | None = None

    # --- Run provenance (backtest sources only) ------------------------------
    strategy_id: str | None = None
    window_start: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    window_end: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    oos_start_date: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    oos_end_date: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    #: When the run that produced the numbers was executed. Recorded for audit
    #: only -- ageing anchors on ``oos_end_date`` (D-4), never on this.
    produced_at: str | None = None
    rates_verified: bool | None = None
    dividend_reason_code: str | None = None
    adjust_dividends: bool | None = None

    # --- Round-trip sample structure (never fill-level; 約束 25) -------------
    oos_round_trips: int | None = Field(default=None, ge=0)
    oos_win_trips: int | None = Field(default=None, ge=0)
    oos_loss_trips: int | None = Field(default=None, ge=0)
    oos_excluded_boundary_trips: int | None = Field(default=None, ge=0)
    oos_open_trip_at_end: int | None = Field(default=None, ge=0)
    oos_observations: int | None = Field(default=None, ge=0)

    # --- Disclosure-only interval fields (約束 27/34) ------------------------
    #: None of these may reach the cap computation, rewrite the effective pair,
    #: or serve as a clamp. ``f_star`` in particular is stored for audit and
    #: interval comparison only: the cap always re-calls ``kelly_fraction``
    #: with the effective pair.
    p_ci_low: float | None = None
    p_ci_high: float | None = None
    f_star: float | None = None
    f_star_ci_low: float | None = None
    f_star_ci_high: float | None = None
    bootstrap_seed: int | None = None
    bootstrap_draws: int | None = Field(default=None, ge=0)
    #: Degenerate resamples counted **by direction** (quant 2026-08-19): an
    #: all-win draw and an all-loss draw push opposite ends of the interval, so
    #: one merged counter would leave an auditor unable to read either.
    bootstrap_degenerate_no_loss_draws: int | None = Field(default=None, ge=0)
    bootstrap_degenerate_no_win_draws: int | None = Field(default=None, ge=0)
    spec_hash: str | None = None
    #: Set when the sample cleared the hard gate but sits in the soft band
    #: (D-3). A disclosure flag, never an input to a calculation.
    low_sample_warning: bool | None = None
    #: ``K_observed`` at the moment this row was written, for the selection-bias
    #: disclosure (約束 30). A snapshot, not a live count.
    k_observed_at_write: int | None = None

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @field_validator("win_rate")
    @classmethod
    def _win_rate_in_range(cls, value: float) -> float:
        return _check_win_rate(value)

    @field_validator("payoff_ratio")
    @classmethod
    def _payoff_ratio_positive(cls, value: float) -> float:
        return _check_payoff_ratio(value)

    @field_validator("backtest_win_rate")
    @classmethod
    def _backtest_win_rate_in_range(cls, value: float | None) -> float | None:
        return None if value is None else _check_win_rate(value)

    @field_validator("backtest_payoff_ratio")
    @classmethod
    def _backtest_payoff_ratio_positive(cls, value: float | None) -> float | None:
        return None if value is None else _check_payoff_ratio(value)

    @model_validator(mode="after")
    def _manual_carries_no_strategy(self) -> KellyInputRecord:
        """A manual input may not name a strategy (約束 2).

        Not cosmetic: ``strategy_id`` is what the disclosure reads to say which
        strategy produced a number, and a hand-typed pair was produced by none.
        """
        if self.source == "manual" and self.strategy_id is not None:
            raise ValueError("manual 來源的 Kelly 輸入不得帶 strategy_id")
        return self

    @classmethod
    def manual(
        cls, *, symbol: str, market: Market, win_rate: float, payoff_ratio: float
    ) -> KellyInputRecord:
        """A hand-typed pair with no provenance at all."""
        return cls(
            symbol=symbol,
            market=market,
            win_rate=win_rate,
            payoff_ratio=payoff_ratio,
            source="manual",
        )

    @classmethod
    def overriding(
        cls, previous: KellyInputRow, *, win_rate: float, payoff_ratio: float
    ) -> KellyInputRecord:
        """``previous`` with a hand-typed pair on top of it (約束 4).

        Everything the import established -- its own ``backtest_*`` numbers, the
        window, the counts, the intervals -- is carried over untouched, and only
        the effective pair and the source change. Rebuilding the row as a plain
        manual input instead would erase the evidence that the user edited an
        imported number rather than typing one from nowhere.
        """
        values = {name: getattr(previous, name) for name in cls.model_fields}
        values.update(
            win_rate=win_rate, payoff_ratio=payoff_ratio, source="backtest_overridden"
        )
        return cls(**values)


class KellyInputRow(KellyInputRecord):
    """A stored Kelly input: the record plus the server's write stamp."""

    #: Server-stamped on every accepted write; the freshness anchor for manual
    #: inputs and the audit trail for every source.
    updated_at: datetime


class KellyAttemptRecord(BaseModel):
    """One ``import-backtest`` attempt, as it is appended to the log.

    Written for **every** attempt that gets past request validation, including
    the ones the gate refuses (D-3): a refused attempt is still an attempt the
    user made, and dropping it would under-report ``K_observed``, which is the
    one number the selection-bias disclosure rests on (約束 30).

    ``outcome`` is the **gate verdict**, not whether the row was stored. The
    two are decided at different moments and by different code, and conflating
    them would make the log answer a question it was not asked.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1)
    market: Market
    #: NOT NULL here, unlike on the input row: an import always runs a named
    #: strategy, so an attempt without one could not have happened.
    strategy_id: str = Field(min_length=1)
    #: Canonical JSON of the validated backtest request. Contains no credential
    #: of any kind, so it is safe to keep indefinitely.
    request_spec: str
    #: sha256 of ``request_spec``; also the source of the bootstrap seed.
    spec_hash: str = Field(min_length=1)
    outcome: Literal["ok", "rejected"]
    reason_code: KellyGateReasonCode | None = None

    win_rate: float | None = None
    payoff_ratio: float | None = None
    kelly_fraction: float | None = None

    oos_round_trips: int | None = Field(default=None, ge=0)
    oos_win_trips: int | None = Field(default=None, ge=0)
    oos_loss_trips: int | None = Field(default=None, ge=0)
    oos_excluded_boundary_trips: int | None = Field(default=None, ge=0)
    oos_open_trip_at_end: int | None = Field(default=None, ge=0)
    oos_start_date: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    oos_end_date: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    oos_observations: int | None = Field(default=None, ge=0)
    f_star_ci_low: float | None = None
    f_star_ci_high: float | None = None

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return normalize_symbol(value)

    @model_validator(mode="after")
    def _reason_code_matches_outcome(self) -> KellyAttemptRecord:
        """``reason_code`` is present exactly when the gate refused.

        An ``ok`` carrying a reason, or a ``rejected`` carrying none, would
        make the log unreadable in the only direction it is ever read.
        """
        if self.outcome == "ok" and self.reason_code is not None:
            raise ValueError("outcome 為 ok 時不得帶 reason_code")
        if self.outcome == "rejected" and self.reason_code is None:
            raise ValueError("outcome 為 rejected 時必須帶 reason_code")
        return self


def anchor_moment(row: KellyInputRow) -> datetime | None:
    """The moment ``row`` ages from (D-4), or ``None`` when it has none.

    Manual inputs age from the write stamp -- the user's own action. Imported
    ones age from the end of the out-of-sample segment, because a re-run of an
    old window would otherwise reset the clock and present stale evidence as
    current.

    An imported row carrying no OOS end date therefore has **no anchor at
    all**, and this returns ``None`` rather than substituting the write stamp
    (qa-reviewer 退修 2026-08-19). The substitution looked conservative and was
    the opposite: ``updated_at`` is always at or after the end of the segment
    that was measured, so falling back to it moves the anchor *towards now* and
    makes the row read younger -- precisely the "re-running an old window makes
    it look fresh" failure D-4 exists to prevent. With no anchor there is no
    age, and :func:`ageing_of` treats that as expired.
    """
    if row.source == "manual":
        return row.updated_at
    if row.oos_end_date is None:
        return None
    return datetime.fromisoformat(row.oos_end_date).replace(tzinfo=UTC)


def age_in_days(anchor: datetime, *, now: datetime | None = None) -> int:
    """Whole days between ``anchor`` and now, never negative.

    A future anchor (clock skew, or an edited database) reads as "just now"
    rather than as a negative age, matching
    :func:`app.advice.book.self_reported_net_worth`.
    """
    moment = now if now is not None else datetime.now(UTC)
    return max((moment - anchor).days, 0)


def freshness_of(age_days: int) -> KellyFreshness:
    """Which freshness band a **known** age falls in."""
    if age_days >= KELLY_STALE_AFTER_DAYS:
        return "expired"
    if age_days >= KELLY_SOFT_NOTICE_DAYS:
        return "ageing"
    return "fresh"


@dataclass(frozen=True)
class KellyAgeing:
    """How old one input is, and whether it is still usable.

    ``anchored_at`` and ``age_days`` are ``None`` together, and only in the
    unanchorable case (see :func:`anchor_moment`). They are withheld rather
    than filled with a stand-in because every number that could be put there
    would be read as evidence of freshness, and there is none.
    """

    anchored_at: datetime | None
    age_days: int | None
    freshness: KellyFreshness


def ageing_of(row: KellyInputRow, *, now: datetime | None = None) -> KellyAgeing:
    """The freshness verdict on one input, anchor rule included (D-4).

    The single place the "no anchor means expired" rule is applied, so a second
    caller cannot re-derive it and land on a friendlier answer. An input whose
    age cannot be established is treated exactly like one that is provably too
    old: cap 5 stops using it and the reader is told why. Fail-safe is the only
    defensible direction here -- the alternative is a risk cap that keeps
    computing from evidence of unknown age.
    """
    anchor = anchor_moment(row)
    if anchor is None:
        return KellyAgeing(anchored_at=None, age_days=None, freshness="expired")
    age = age_in_days(anchor, now=now)
    return KellyAgeing(anchored_at=anchor, age_days=age, freshness=freshness_of(age))
