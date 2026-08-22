"""Read, write, import and clear the Kelly input behind risk cap 5 (ADR-0006 D-8).

Two doors lead to one row. The manual one takes a pair the user typed. The
import one (``POST .../import-backtest``) takes **a backtest request** -- never
a number -- re-runs that backtest server-side and stores what the server itself
computed from it. A body carrying p, b or f\\* is refused by
:class:`~app.api.backtest.BacktestRequest` before this module sees it (約束 31),
which is what stops the "imported from a backtest" badge from being attached to
numbers no backtest produced.

This module is also the **only** assembly point of the three packages the Kelly
path spans (約束 37): ``app.advice`` owns the single fraction formula,
``app.backtest`` owns the round-trip sample and the intervals over it, and
``app.kelly`` owns the storage and the gates. None of the three imports another;
they meet here and nowhere else.

Three rules the endpoints below implement:

* out-of-range numbers are **refused, not clamped** (約束 6). ``win_rate``
  outside (0, 1) or a non-positive ``payoff_ratio`` is a 422 that states the
  bound and says the value was not adjusted, and the stored input keeps
  standing -- the same stance the settings router takes on the reported net
  worth.
* the write stamp is the server's. :class:`KellyManualInput` carries no
  timestamp at all, so an input cannot be backdated into looking fresh.
* editing an imported pair by hand does not erase the import. The row's source
  becomes ``backtest_overridden`` and the imported numbers stay beside the new
  ones (約束 4), so "the user changed this" remains visible.

``DELETE`` removes the input row and **nothing else**: the import-attempt log
is a different table in a different store and is not touched (約束 35).
Clearing an input the user no longer trusts must not also erase how many
imports they tried before keeping one.

Every import attempt that gets past request validation is appended to that log
first, refused or not (約束 29). A **422 is a normal outcome here**, not a
fault: most windows on most symbols do not produce twenty completed round
trips, so the refusal carries a ``reason_code`` and the numbers actually
measured, and the log carries the same verdict. If the log cannot be written,
the import fails with a 500 -- an import that proceeded unlogged would
permanently under-report ``K_observed``, the count the selection-bias
disclosure rests on.

The interval fields that get stored (``p_ci_*``, ``f_star``, ``f_star_ci_*``,
``low_sample_warning``) are **disclosure and audit only** (約束 34). They never
rewrite the effective pair, and cap 5 recomputes the fraction from that pair
rather than reading the stored ``f_star``.

It is also where the **display copy is chosen** (K4c-1). ``GET
.../{symbol}/disclosures`` returns one finished string per slot -- or ``None``
for "not shown" -- and the 422 body carries the three sentences a refused import
owes the user. That is a compliance requirement rather than a convenience:
落地條件 3 and 約束 21 forbid the front end from judging freshness, rewriting,
truncating or composing any of this text, and 分歧① required 2 makes the rule
mechanical by keeping the restricted term for a sampled frequency off its Kelly
surface altogether. A client choosing between (e) and (e-manual) would have to
hold both.

Freshness is stated, not acted on: this router reports ``age_days`` and which
band the input falls in (fresh / ageing / expired, D-4), and an input whose age
cannot be established at all is reported as expired with no age
(:func:`app.kelly.models.ageing_of`). Whether cap 5 still computes from an
expired input is the risk layer's decision, taken from the same helper, so the
two cannot drift into disagreeing about the same row.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict

from app.advice.book import kelly_inputs_of
from app.advice.limits import (
    LIMIT_NAMES,
    KellyInputs,
    PortfolioContext,
    RiskBudget,
    format_payoff_ratio,
    format_percent,
    format_win_rate,
    kelly_allowed_weight,
    kelly_fraction,
    kelly_usable,
)
from app.api.backtest import DIVIDEND_ADJUSTED_NOTE, BacktestRequest, execute_backtest
from app.api.common import now_iso
from app.api.deps import (
    get_dividend_store,
    get_kelly_attempt_store,
    get_kelly_input_store,
    get_market_resolver,
    get_settings_store,
)
from app.api.kelly_wording import (
    KELLY_BACKTEST_SAMPLE_DETAIL_INTRO,
    KELLY_BOUNDARY_TRIP_EXCLUSION,
    KELLY_DETAIL_DIVIDEND_LABEL,
    KELLY_DETAIL_EXCLUDED_BOUNDARY_TRIPS_LABEL,
    KELLY_DETAIL_LOSS_TRIPS_LABEL,
    KELLY_DETAIL_OBSERVATIONS_LABEL,
    KELLY_DETAIL_OOS_PERIOD_LABEL,
    KELLY_DETAIL_OPEN_TRIP_AT_END_LABEL,
    KELLY_DETAIL_RATES_VERIFIED_LABEL,
    KELLY_DETAIL_ROUND_TRIPS_LABEL,
    KELLY_DETAIL_STRATEGY_LABEL,
    KELLY_DETAIL_WIN_RATE_CI_LABEL,
    KELLY_DETAIL_WIN_TRIPS_LABEL,
    KELLY_F_STAR_INTERVAL_DISCLOSURE,
    KELLY_FRESHNESS_BADGE_ABSENT,
    KELLY_FRESHNESS_BADGE_AGEING,
    KELLY_FRESHNESS_BADGE_EXPIRED,
    KELLY_FRESHNESS_BADGE_FRESH,
    KELLY_MANUAL_INPUT_DISCLOSURE,
    KELLY_MANUAL_INPUT_TOOLTIP,
    KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY,
    KELLY_ORIGINAL_OOS_PERIOD_LABEL,
    KELLY_ORIGINAL_PAIR_DISCLOSURE,
    KELLY_OVERWRITE_CANCEL_LABEL,
    KELLY_OVERWRITE_CONFIRM_LABEL,
    KELLY_OVERWRITE_NOTICE_TITLE,
    KELLY_RATES_UNVERIFIED_NOTE,
    KELLY_REFUSAL_ATTEMPT_LOGGED,
    KELLY_REFUSAL_FRAME,
    KELLY_SELECTION_BIAS_FULL,
    KELLY_SELECTION_BIAS_SINGLE,
    KELLY_SELECTION_BIAS_UNLOGGED,
    KELLY_SOURCE_BACKTEST_LABEL,
    KELLY_SOURCE_BACKTEST_STATEMENT,
    KELLY_SOURCE_MANUAL_LABEL,
    KELLY_SOURCE_MANUAL_STATEMENT,
    KELLY_SOURCE_OVERRIDDEN_LABEL,
    KELLY_SOURCE_OVERRIDDEN_STATEMENT,
    KELLY_WALK_FORWARD_SCOPE,
    KELLY_WIN_RATE_IS_NOT_PROBABILITY,
    KELLY_WIN_RATE_ROUND_TRIP_QUALIFIER,
    kelly_dividend_note,
    kelly_overwrite_notice,
)
from app.backtest.episodes import (
    RoundTripAttribution,
    attribute_round_trips,
    bootstrap_fraction_ci,
    episode_returns,
    oos_window,
    wilson_interval,
)
from app.dividends.store import DividendEventStore
from app.kelly.attempts import KellyAttemptStore
from app.kelly.models import (
    KELLY_PAYOFF_RATIO_LABEL,
    KellyAttemptRecord,
    KellyFreshness,
    KellyGateReasonCode,
    KellyInputRecord,
    KellyInputRow,
    KellyManualInput,
    KellySource,
    ageing_of,
    normalize_symbol,
)
from app.kelly.sample_gate import (
    KellySampleGateReview,
    review_estimates,
    review_result_status,
    review_sample,
    review_symbol_match,
)
from app.kelly.store import KellyInputStore
from app.positions.models import Market
from app.services.market import MarketDataResolver
from app.settings.store import SettingsStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kelly-inputs", tags=["kelly"])

KellyStoreDep = Annotated[KellyInputStore, Depends(get_kelly_input_store)]
KellyAttemptsDep = Annotated[KellyAttemptStore, Depends(get_kelly_attempt_store)]
ResolverDep = Annotated[MarketDataResolver, Depends(get_market_resolver)]
SettingsDep = Annotated[SettingsStore, Depends(get_settings_store)]
DividendStoreDep = Annotated[DividendEventStore, Depends(get_dividend_store)]
MarketQuery = Annotated[Market, Query(description="市場別")]

KELLY_INPUT_NOT_FOUND_MESSAGE = "找不到 {symbol}（{market}）的 Kelly 輸入。"

#: Resamples per import. 2000 is the count the degenerate-draw analysis was run
#: against (quant-researcher 2026-08-19): with the 20/5/5 gate in force an
#: all-win or all-loss resample arrives roughly six times in two thousand, far
#: below the 2.5% tail the bounds are read off, so the degenerate draws move the
#: counters and not the stored interval.
BOOTSTRAP_DRAWS = 2000

KELLY_ATTEMPT_LOG_FAILED_MESSAGE = (
    "無法寫入 Kelly 匯入嘗試紀錄，本次匯入未完成，也未寫入 Kelly 輸入。"
)

#: 風控 2026-08-19 逐字定稿（第四輪，備案+修訂），字面含標點不得改動，漂移須重送風控。
#: The 500 body for 約束 27's should-not-happen. It stays in this module rather
#: than in :mod:`app.api.kelly_wording` because 落地條件 25 names this constant and
#: this line; :mod:`tests.test_kelly_wording` carries it in the same verbatim
#: inventory as the other twenty.
#:
#: Three things about the wording are rulings, not choices:
#:
#: * "至少有一端不是有限的數字", never "都不是". The guard below fires on *either*
#:   bound, and the reachable case is one-sided: a no-loss resample still returns
#:   a finite fraction, so the only non-finite value the bootstrap produces is the
#:   ``-inf`` of a no-win draw (``app/backtest/episodes.py``). A sentence saying
#:   both ends are non-finite would be false in the case that actually happens.
#: * "這次沒有寫入 Kelly 輸入", never "沒有數值被寫入". The attempt row *is*
#:   written, with its measured columns; what did not get written is the
#:   ``KellyInputRow``, and the sentence names that.
#: * No retry advice in either direction. "Try again" is an instruction, and
#:   "trying again will not help" is a claim about a future run this code cannot
#:   support -- reproducibility holds only for the same spec over the same bars,
#:   and bars are refetched.
#:
#: It also interpolates nothing. On this branch the bounds are non-finite by
#: construction, so the old ``.format()`` rendered ``inf`` / ``-inf`` / ``nan``
#: into a Chinese sentence -- the same fault 5-3 struck at the root in PB_NONE by
#: deleting the call rather than guarding it. The values go to ``logger.error``
#: below, which 落地條件 28 makes the one place they may not be dropped from.
#:
#: Display order is fixed (條件 27): this sentence first, then
#: :data:`app.api.kelly_wording.KELLY_NON_FINITE_ATTEMPT_LOGGED` (3-B) with (b)
#: beside it. If the surface cannot hold (b), 3-B is omitted and this sentence
#: stands alone -- which is why the fact that nothing was written lives here and
#: not only there.
KELLY_NON_FINITE_INTERVAL_MESSAGE = (
    "本次計算出的 f* 區間，其上界與下界之中至少有一端不是有限的數字，"
    "超出本系統可寫入的範圍，這次沒有寫入 Kelly 輸入。"
)


class KellyInputView(BaseModel):
    """One stored Kelly input plus the freshness facts about it.

    ``anchored_at`` is spelled out rather than left implicit because it differs
    by source: a manual input ages from when it was typed, an imported one from
    the end of the segment it was measured over (D-4). A reader who could not
    see which of the two ``age_days`` counts from would be unable to check it.

    Both are ``null`` together when the row has no anchor at all (an imported
    pair with no OOS end date). ``freshness`` is then ``expired``: no stand-in
    number is reported, because any number there would be read as evidence the
    input is current, and there is none.
    """

    model_config = ConfigDict(frozen=True)

    item: KellyInputRow
    anchored_at: str | None
    age_days: int | None
    freshness: KellyFreshness
    as_of: str


class KellyInputListView(BaseModel):
    """Every stored input, each with its own freshness verdict.

    The list is the same view object per row rather than a leaner summary: a
    caller that had to fetch each row again to learn its age would be one
    forgotten call away from showing a stale pair as if it were current.
    """

    model_config = ConfigDict(frozen=True)

    items: list[KellyInputView]
    as_of: str


class KellyImportRefusal(BaseModel):
    """The body of a refused import: which gate closed, and what it measured.

    A refusal is a normal outcome of this endpoint (D-3), so it is structured
    rather than prose-only: ``reason_code`` is what a client branches on and
    ``message`` states the numbers actually observed against the threshold.
    The message is a statement of measurement, never advice about what to do
    next.

    The three sentences around ``message`` are picked here rather than by the
    caller, because each one's condition is a fact about this refusal and not
    about the screen it lands on (約束 21: the front end renders and composes
    nothing):

    * ``frame`` -- (d-1 元件 A), and **only** for the three sample-size codes
      (落地條件 13). "這是常見情況" is true of a window that did not produce
      twenty round trips and false of ``symbol_mismatch``, which is a front-end
      bug, so attaching it to the other three would dress a fault up as normal.
    * ``attempt_logged`` -- (d-1 元件 B), for all six: every one of them appends
      to the log before raising, so the count really did move.
    * ``selection_bias`` -- 3-A requires (b) **on the same screen** as 元件 B,
      not merely a link, because ``k_distinct_specs`` was pushed up by this
      attempt too. It travels in the body because a refused import may leave no
      stored row at all, and a client that had to fetch one to obtain (b) would
      have nothing to fetch.
    """

    model_config = ConfigDict(frozen=True)

    reason_code: KellyGateReasonCode
    message: str
    frame: str | None = None
    attempt_logged: str = KELLY_REFUSAL_ATTEMPT_LOGGED
    selection_bias: str | None = None
    #: Both counts as they stand **after** this attempt was appended, which is
    #: what makes 元件 B's "已計入 K_observed" checkable on the same screen.
    k_observed: int = 0
    k_distinct_specs: int = 0


def _view(row: KellyInputRow) -> KellyInputView:
    ageing = ageing_of(row)
    return KellyInputView(
        item=row,
        anchored_at=None if ageing.anchored_at is None else ageing.anchored_at.isoformat(),
        age_days=ageing.age_days,
        freshness=ageing.freshness,
        as_of=now_iso(),
    )


# --------------------------------------------------------------------------
# Display supply: which approved sentence this row shows, decided here (K4c-1)
# --------------------------------------------------------------------------
#
# 落地條件 3 and 約束 21 together fix where the branching lives: the front end
# renders backend sentences **verbatim** and may not judge freshness, rewrite,
# truncate, or assemble Chinese of its own -- and 分歧① required 2 makes that
# mechanical by keeping the word 「勝率」 out of its Kelly surface entirely. A
# client that had to decide between (e) and (e-manual), or between (b 完整) and
# (b 短), would be holding the sentences to choose from.
#
# So every branch below is a *display rule from the review*, cited where it is
# applied, and what leaves this module is one finished string per slot or
# ``None`` for "this slot is not shown". Nothing here computes a statistic: the
# numbers are read from the stored row, and the effective cap comes from
# ``kelly_allowed_weight`` rather than a second copy of the min/max formula.

#: (d-1 元件 A) is limited to these three (落地條件 13). The other three codes are
#: faults or upstream conditions, and the frame's reassurance would misdescribe
#: them.
_SAMPLE_SIZE_REASON_CODES: Final[frozenset[str]] = frozenset(
    {"low_round_trips", "low_win_trips", "low_loss_trips"}
)

#: (任務 5) The badge over one input, per freshness band. "尚未輸入" is not in this
#: table because it is not a freshness: it is the absence of a row (條件 47 ①).
_FRESHNESS_BADGES: Final[dict[KellyFreshness, str]] = {
    "fresh": KELLY_FRESHNESS_BADGE_FRESH,
    "ageing": KELLY_FRESHNESS_BADGE_AGEING,
    "expired": KELLY_FRESHNESS_BADGE_EXPIRED,
}

#: The separator between two plain dates, the shape ``suggest_quantity_range``
#: already prints a range in. Both ends stay ``YYYY-MM-DD`` (6-A).
#:
#: 條件 90 (第十輪) approved exactly **two connector shapes for two uses** and
#: nothing else: this one between dates, and 「 至 」 between two percentages,
#: whose 出處 is (a-1)'s own approved text ("{f_star_ci_low_pct} 至
#: {f_star_ci_high_pct}"). A third shape, or either of these used for the other
#: purpose, is a red light -- ``tests/test_api_kelly_disclosures.py`` holds the
#: assertion.
_DATE_RANGE = "{start} ~ {end}"

#: The connector between two already-formatted percentages, taken from (a-1)
#: (條件 90). Used for 欄位 9's Wilson interval and for nothing else.
_PERCENT_RANGE = "{low} 至 {high}"

#: (fr6) The source disclosure as ``(sentence, label)``, one entry per source and
#: **no ``None`` fallback** (條件 84). The sixth round left the ``backtest`` cell
#: empty, K4c-1 reported it as a gap and the tenth round filled it directly, so
#: every source now states its own provenance. A missing entry here would be a
#: ``KeyError`` rather than a silent blank, which is the point: an empty cell and
#: a sentence nobody has written yet must not look the same.
_SOURCE_STATEMENTS: Final[dict[KellySource, tuple[str, str]]] = {
    "manual": (KELLY_SOURCE_MANUAL_STATEMENT, KELLY_SOURCE_MANUAL_LABEL),
    "backtest": (KELLY_SOURCE_BACKTEST_STATEMENT, KELLY_SOURCE_BACKTEST_LABEL),
    "backtest_overridden": (
        KELLY_SOURCE_OVERRIDDEN_STATEMENT,
        KELLY_SOURCE_OVERRIDDEN_LABEL,
    ),
}


class KellyDetailRow(BaseModel):
    """One row of the FR-5 sample detail: an approved label, a finished value.

    ``value`` is a string because every one of them is already formatted -- a
    percentage at the precision the sample supports, a plain ``YYYY-MM-DD``
    date, a count -- and handing a client a raw float would be handing it the
    formatting decision that 分歧① required 5 struck ``:g`` for.

    ``note`` carries the row's own approved sentence where one exists (欄位 10
    and 欄位 11 are sentences rather than values, and have no ``value`` at all).
    """

    model_config = ConfigDict(frozen=True)

    label: str
    value: str | None = None
    note: str | None = None


class KellyBacktestSampleDetail(BaseModel):
    """(任務 3) FR-5: the frame sentence and the rows under it.

    Only ever built for ``source == "backtest"`` (條件 42). A row whose value is
    not on the record is left out rather than rendered as a blank or a dash:
    the eleven labels were approved as labels over facts, and a label over
    nothing states that a measurement exists.
    """

    model_config = ConfigDict(frozen=True)

    intro: str
    rows: list[KellyDetailRow]


class KellyEffectiveCapView(BaseModel):
    """The cap actually in force, for the screen that shows the un-capped f*.

    落地條件 6: wherever f* or its interval is displayed, the same screen shows
    ``min(max(f*, 0) x 0.25, 0.10)`` at no lesser prominence -- otherwise the
    larger number reads as the position the system is putting forward, which is
    約束 11's red line.

    ``label`` is cap 5's own name from :data:`app.advice.limits.LIMIT_NAMES`,
    imported rather than retyped -- 條件 88 approved reusing it here rather than
    drafting a label of its own.

    ``value`` is computed from the **user's** risk budget
    (``settings.risk_budget``), never from :class:`RiskBudget`'s defaults
    (條件 87). The caps can only be tightened, so a default-budget figure would
    be greater than or equal to the one cap 5 actually enforces: the same
    quantity would read differently on two screens, and this one would read
    larger -- a bigger allowance than the system will grant.
    """

    model_config = ConfigDict(frozen=True)

    label: str
    value: str


class KellyOriginalValuesView(BaseModel):
    """(任務 7/任務 8) The imported pair kept beside an overridden one.

    The screen 落地條件 21 said could not exist until a distinguishing sentence
    was approved; 條件 65 puts that sentence (``statement``) and the OOS label on
    it together, and rules that the win-rate label **quotes** the already
    approved 口徑限定語 rather than minting a second wording.

    條件 54 is a reverse obligation and is asserted in the tests: FR-5 欄位 2's
    label may not appear here, so the original OOS period and the effective
    row's OOS period cannot be read as the same row.
    """

    model_config = ConfigDict(frozen=True)

    statement: str
    win_rate_label: str
    win_rate: str
    #: 條件 86: the payoff ratio's approved label, whose single definition is
    #: :data:`app.kelly.models.KELLY_PAYOFF_RATIO_LABEL` -- the same noun phrase
    #: the range refusal names the field by, so one screen cannot call it
    #: something the other does not.
    payoff_ratio_label: str
    payoff_ratio: str
    oos_period_label: str
    oos_period: str | None


class KellyOverwriteNoticeView(BaseModel):
    """(條件 53/68/71-83) What a surface must show before it re-imports.

    Supplied whole -- title, body, both button labels -- because every part of
    it is approved copy and none of it may be assembled by a client (條件 72,
    which also fixes the dialog's ``aria-label`` as the title **verbatim**).

    ``body`` is the source's own two paragraphs plus the shared close, **as
    three items in the approved order** (條件 82/93). They are delivered as a
    list and not as one joined string: 段二 is the paragraph naming what the
    user loses, and running the three together demotes it visually, which is
    the one thing this dialog cannot afford. The literals are untouched.

    It interpolates nothing and carries no win rate and no payoff ratio:
    條件 75 keeps every measured number off this dialog, and putting one back on
    it is a new submission, not a formatting choice.

    **條件 94**: the variant is chosen from the row's source *at read time*, so a
    client must show the variant belonging to the source it confirmed against.
    Caching a dialog across an edit that changes ``source`` -- a hand edit turns
    ``backtest`` into ``backtest_overridden`` -- would show the wrong one; the
    surface re-reads this endpoint before it opens the dialog.

    **條件 78**: the label on the *trigger* that opens this dialog is not
    approved and is deliberately absent from this model. It is a separate
    submission to risk-compliance -- neither this API nor the front end may
    invent one, and it is subject to the same banned literals as the title
    (條件 71/77, pinned in ``tests/test_kelly_wording.py``).
    """

    model_config = ConfigDict(frozen=True)

    title: str
    body: list[str]
    confirm_label: str
    cancel_label: str


class KellyDisclosuresView(BaseModel):
    """Every slot of one Kelly screen, already decided (落地條件 3).

    ``None`` means "this slot is not shown", never "the client picks something".
    The conditions are the review's, one per field.
    """

    model_config = ConfigDict(frozen=True)

    #: (任務 5) Always present: an absent input is its own badge state. 條件 97:
    #: this response does **not** carry (g) -- cap 5 owns those five sentences
    #: and ships them in its own detail -- so a surface may only render the
    #: ``expired`` badge on a screen that also shows cap 5's (g) sentence.
    freshness_badge_label: str
    #: (fr6) The source of the effective pair. All three sources have both a
    #: sentence and a short label (條件 84) -- the table they come from has no
    #: ``None`` fallback -- and 條件 85 bounds their display: provenance only,
    #: never in a slot that reads as verification, and never more prominent than
    #: (e)/(e-manual). The pair is ``None`` **only** where there is no row and so
    #: no source at all, which the badge already says in its own words.
    source_statement: str | None
    source_label: str | None
    #: (e) or (e-manual), by source: mutually exclusive and exhaustive (條件 18).
    win_rate_disclosure: str | None
    #: (f 完整) and (f tooltip), for the two hand-keyed sources (條件 20).
    manual_input_disclosure: str | None
    manual_input_tooltip: str | None
    #: (b 完整) or (b 短), by K (條件 5).
    selection_bias: str | None
    #: (c) walk-forward, beside the out-of-sample sample it describes.
    walk_forward: str | None
    #: (a-1), with both bounds already rendered as percentages (條件 12).
    f_star_interval: str | None
    #: 落地條件 6's partner to ``f_star_interval``; the two are shown or withheld
    #: together.
    effective_cap: KellyEffectiveCapView | None
    #: (h), beside FR-5 欄位 6/7, which are the counts it explains (條件 44).
    boundary_exclusion: str | None
    sample_detail: KellyBacktestSampleDetail | None
    original_values: KellyOriginalValuesView | None
    #: 條件 53/68/73: the dialog that must be shown before this input is
    #: re-imported, or ``None`` where the ninth round ruled there is none. The
    #: four cells are decided in :func:`_overwrite_notice` and are exhaustive.
    overwrite_notice: KellyOverwriteNoticeView | None
    #: The two counts (b) rests on, live rather than the ``k_observed_at_write``
    #: snapshot on the row: an attempt made after this input was stored still
    #: widened the search this disclosure describes.
    k_observed: int
    k_distinct_specs: int


class KellyInputDisclosuresView(BaseModel):
    """One instrument's Kelly screen: the row, its ageing, and every sentence.

    ``kelly_input`` is ``None`` when nothing was ever entered, and the response
    is still a 200 rather than the 404 ``GET /{symbol}`` returns: "never
    entered" is a state this screen has copy for (the ``尚未輸入`` badge, (g-1)
    from cap 5) and a count for -- refused imports leave attempts behind with no
    row to show, and (b) is exactly the disclosure that must survive them.
    """

    model_config = ConfigDict(frozen=True)

    kelly_input: KellyInputView | None
    disclosures: KellyDisclosuresView
    as_of: str


def _selection_bias(k_observed: int, k_distinct_specs: int) -> str | None:
    """(b), per the K branch (約束 30 / 落地條件 5), for callers with no row.

    ``K >= 2`` takes the full sentence and ``K == 1`` the short one; neither may
    be empty. ``K == 0`` returns nothing **here** on purpose: this selector is
    also what the 422 body and the "nothing has ever been entered" screen call,
    and 條件 96's sentence is false on both of them -- a refusal has just
    appended its own attempt, and a screen with no row is not owed (b) at all.
    條件 98 therefore puts that third cell at the assembly point, where the
    source is known: :func:`_selection_bias_for_row`.
    """
    if k_observed >= 2:
        return KELLY_SELECTION_BIAS_FULL.format(
            k_observed=k_observed, k_distinct_specs=k_distinct_specs
        )
    if k_observed == 1:
        return KELLY_SELECTION_BIAS_SINGLE
    return None


def _dividend_note(row: KellyInputRow) -> str | None:
    """(欄位 11) for one row, or ``None`` when the code says nothing to explain.

    ``adjusted`` keeps ``DIVIDEND_ADJUSTED_NOTE`` (第六輪, 沿用核可) and the four
    degraded codes take Kelly's own block. Reusing the backtester's note for the
    degraded branches is what 條件 62 forbids, and the two are kept apart by this
    one branch: the wording module imports nothing, so the choice lands here,
    the assembly point (D-8).
    """
    code = row.dividend_reason_code
    if code is None:
        return None
    if code == "adjusted":
        return DIVIDEND_ADJUSTED_NOTE
    return kelly_dividend_note(code, market=row.market)


def _sample_detail(row: KellyInputRow) -> KellyBacktestSampleDetail:
    """(任務 3) The eleven-column detail for an imported row (條件 42).

    Two guards shape what comes out:

    * 條件 43 -- rows 3/4/5 are displayed **only** if ``n == n_win + n_loss``.
      The three counts side by side assert a partition of the sample, and the
      review would not let a gap between them be shown as one.
    * 條件 45 -- row 10's sentence is bound to ``rates_verified is False``.
      ``None`` is "the run said nothing about its rates", which is a different
      finding with no approved sentence, and ``not rates_verified`` would merge
      the two.
    """
    rows: list[KellyDetailRow] = []
    if row.strategy_id is not None:
        rows.append(
            KellyDetailRow(label=KELLY_DETAIL_STRATEGY_LABEL, value=row.strategy_id)
        )
    if row.oos_start_date is not None and row.oos_end_date is not None:
        rows.append(
            KellyDetailRow(
                label=KELLY_DETAIL_OOS_PERIOD_LABEL,
                value=_DATE_RANGE.format(start=row.oos_start_date, end=row.oos_end_date),
            )
        )
    trips = (row.oos_round_trips, row.oos_win_trips, row.oos_loss_trips)
    if all(count is not None for count in trips):
        n, n_win, n_loss = (int(count) for count in trips if count is not None)
        if n == n_win + n_loss:
            rows.append(KellyDetailRow(label=KELLY_DETAIL_ROUND_TRIPS_LABEL, value=str(n)))
            rows.append(KellyDetailRow(label=KELLY_DETAIL_WIN_TRIPS_LABEL, value=str(n_win)))
            rows.append(
                KellyDetailRow(label=KELLY_DETAIL_LOSS_TRIPS_LABEL, value=str(n_loss))
            )
        else:
            # 條件 43: 「不成立禁三欄並列」. Not a crash and not a silent partial
            # display of two of the three -- all three are withheld, and the
            # discrepancy is reported where an operator will see it.
            logger.error(
                "kelly sample detail withheld: n != n_win + n_loss for symbol=%s "
                "market=%s n=%d n_win=%d n_loss=%d",
                row.symbol,
                row.market,
                n,
                n_win,
                n_loss,
            )
    if row.oos_excluded_boundary_trips is not None:
        rows.append(
            KellyDetailRow(
                label=KELLY_DETAIL_EXCLUDED_BOUNDARY_TRIPS_LABEL,
                value=str(row.oos_excluded_boundary_trips),
            )
        )
    if row.oos_open_trip_at_end is not None:
        rows.append(
            KellyDetailRow(
                label=KELLY_DETAIL_OPEN_TRIP_AT_END_LABEL,
                value=str(row.oos_open_trip_at_end),
            )
        )
    if row.oos_observations is not None:
        rows.append(
            KellyDetailRow(
                label=KELLY_DETAIL_OBSERVATIONS_LABEL, value=str(row.oos_observations)
            )
        )
    if row.p_ci_low is not None and row.p_ci_high is not None:
        rows.append(
            KellyDetailRow(
                label=KELLY_DETAIL_WIN_RATE_CI_LABEL,
                # The same fixed one-decimal shape cap 5 prints a win rate in:
                # this interval is over a count ratio, and 分歧① required 5
                # struck false precision on exactly that ground.
                value=_PERCENT_RANGE.format(
                    low=format_win_rate(row.p_ci_low), high=format_win_rate(row.p_ci_high)
                ),
            )
        )
    if row.rates_verified is False:
        rows.append(
            KellyDetailRow(
                label=KELLY_DETAIL_RATES_VERIFIED_LABEL, note=KELLY_RATES_UNVERIFIED_NOTE
            )
        )
    dividend_note = _dividend_note(row)
    if dividend_note is not None:
        rows.append(KellyDetailRow(label=KELLY_DETAIL_DIVIDEND_LABEL, note=dividend_note))
    return KellyBacktestSampleDetail(intro=KELLY_BACKTEST_SAMPLE_DETAIL_INTRO, rows=rows)


def _original_values(row: KellyInputRow) -> KellyOriginalValuesView | None:
    """(任務 7/任務 8) The imported pair beside an overridden effective one.

    Built for ``backtest_overridden`` rows whose ``backtest_*`` columns survived,
    and for nothing else: (任務 7) says in so many words that these two numbers
    were kept while the effective content moved, and a row that has no kept pair
    would make the sentence describe values it is not showing.
    """
    if row.source != "backtest_overridden":
        return None
    if row.backtest_win_rate is None or row.backtest_payoff_ratio is None:
        return None
    period = None
    if row.oos_start_date is not None and row.oos_end_date is not None:
        period = _DATE_RANGE.format(start=row.oos_start_date, end=row.oos_end_date)
    return KellyOriginalValuesView(
        statement=KELLY_ORIGINAL_PAIR_DISCLOSURE,
        win_rate_label=KELLY_WIN_RATE_ROUND_TRIP_QUALIFIER,
        win_rate=format_win_rate(row.backtest_win_rate),
        # 條件 86: the label the range refusal already names this field by,
        # imported from its single definition rather than written again here.
        payoff_ratio_label=KELLY_PAYOFF_RATIO_LABEL,
        payoff_ratio=format_payoff_ratio(row.backtest_payoff_ratio),
        oos_period_label=KELLY_ORIGINAL_OOS_PERIOD_LABEL,
        oos_period=period,
    )


def _f_star_interval(
    row: KellyInputRow, inputs: KellyInputs, budget: RiskBudget
) -> tuple[str | None, KellyEffectiveCapView | None]:
    """(a-1) and the effective cap that 落地條件 6 requires beside it.

    ``budget`` is the user's own (``settings.risk_budget``), passed in for the
    same reason every other call site loads it (條件 87): the caps can only be
    tightened, so computing this from :class:`RiskBudget`'s defaults would show a
    number greater than or equal to the one cap 5 enforces -- two figures for one
    quantity, with the *larger* one on the screen that also shows f*.

    Three conditions have to hold together, and failing any of them withholds
    **both** halves rather than one:

    * ``source == "backtest"``. The stored interval was measured on the imported
      pair; on an overridden row the effective numbers are the user's own, so
      the interval would qualify an estimate the screen is not using.
    * the interval columns are on the record. A manual pair has none, and there
      is nothing to state about a measurement nobody made.
    * the input is still usable (:func:`app.advice.limits.kelly_usable`). An
      expired pair has no cap in force, so there is no "生效上限" to put beside
      f* -- and 落地條件 6 does not allow the interval to be shown without one.
    """
    if row.source != "backtest":
        return (None, None)
    if row.f_star_ci_low is None or row.f_star_ci_high is None:
        return (None, None)
    if not kelly_usable(inputs):
        return (None, None)
    allowed = kelly_allowed_weight(
        budget, PortfolioContext(symbol=row.symbol, kelly=inputs)
    )
    if allowed is None:  # pragma: no cover - kelly_usable already established it
        return (None, None)
    sentence = KELLY_F_STAR_INTERVAL_DISCLOSURE.format(
        f_star_ci_low_pct=format_percent(row.f_star_ci_low),
        f_star_ci_high_pct=format_percent(row.f_star_ci_high),
    )
    cap = KellyEffectiveCapView(
        label=LIMIT_NAMES["kelly_fraction"], value=format_percent(allowed)
    )
    return (sentence, cap)


def _overwrite_notice(row: KellyInputRow | None) -> KellyOverwriteNoticeView | None:
    """The before-overwrite dialog for this row, over 條件 73's four cells.

    ``absent`` -- no row, so nothing can be overwritten and no dialog is shown.
    ``manual`` and ``backtest_overridden`` -- their own variant, from
    :func:`app.api.kelly_wording.kelly_overwrite_notice`. ``backtest`` -- an
    **explicit** no: 條件 73 forbids reaching that answer by falling off the end
    of a table, because a cell that is empty by accident and a cell that is
    empty by ruling look identical afterwards.
    """
    if row is None:
        return None
    if row.source == "backtest":
        return None
    paragraphs = kelly_overwrite_notice(row.source)
    if paragraphs is None:  # pragma: no cover - both hand-keyed sources build
        return None
    return KellyOverwriteNoticeView(
        title=KELLY_OVERWRITE_NOTICE_TITLE,
        # 條件 93: three paragraphs in the approved order, not one joined block.
        body=list(paragraphs),
        confirm_label=KELLY_OVERWRITE_CONFIRM_LABEL,
        cancel_label=KELLY_OVERWRITE_CANCEL_LABEL,
    )


def _selection_bias_for_row(
    row: KellyInputRow, *, k_observed: int, k_distinct_specs: int
) -> str | None:
    """(b) for a stored row, over 條件 98's four cells. No default.

    1. ``K >= 2`` -- (b 完整), with both counts.
    2. ``K == 1`` -- (b 短).
    3. ``K == 0`` and the row has backtest provenance -- 條件 96's sentence. The
       row was written after its own attempt was appended (and a hand edit
       carries that provenance forward), so no attempt means the log is missing
       what (b) rests on. Rows written before the attempt log existed upgrade
       into exactly this state, so it is reachable and may not be a hard
       failure; it may not be silent either, which is what that sentence is for.
    4. ``K == 0`` and the pair was typed -- the normal state of a manual input,
       and nothing is owed. (The fifth conceivable cell, "no row at all", never
       reaches this function: :func:`_disclosures` answers it before calling.)

    Cell 3 stays out of :func:`_selection_bias` under 條件 98, because that one
    is shared with paths where the sentence would be false.
    """
    if k_observed >= 2:
        return KELLY_SELECTION_BIAS_FULL.format(
            k_observed=k_observed, k_distinct_specs=k_distinct_specs
        )
    if k_observed == 1:
        return KELLY_SELECTION_BIAS_SINGLE
    if row.source in {"backtest", "backtest_overridden"}:
        return KELLY_SELECTION_BIAS_UNLOGGED
    return None


def _disclosures(
    row: KellyInputRow | None,
    *,
    budget: RiskBudget,
    k_observed: int,
    k_distinct_specs: int,
) -> KellyDisclosuresView:
    """Choose every sentence one Kelly screen shows, from the row and the counts.

    The source branches are the review's and are exhaustive by construction:
    (e) for ``backtest`` and (e-manual) for the two hand-keyed sources (條件 18),
    (f) for those same two and not for ``backtest`` (條件 20), FR-5 for
    ``backtest`` alone (條件 42), and the original-values view for
    ``backtest_overridden`` alone.

    (c) travels with (e) and, under 條件 92, with anything else that prints the
    words the tenth round bound it to: the original-values view carries (任務 8)'s
    "原始回測的樣本外期間", so (c) is attached there too. The ruling's other
    option -- dropping that period from the view -- would remove information the
    user can check, so the disclosure is added rather than the fact removed.
    tech-architect owns the written choice between the two; this is option one.

    (h) travels with FR-5 欄位 6/7, which are the two counts it explains (條件 44).
    """
    if row is None:
        # Nothing entered: the badge says so, cap 5 says the rest with (g-1),
        # and (b) still stands -- refused imports leave a K behind and no row.
        return KellyDisclosuresView(
            freshness_badge_label=KELLY_FRESHNESS_BADGE_ABSENT,
            source_statement=None,
            source_label=None,
            win_rate_disclosure=None,
            manual_input_disclosure=None,
            manual_input_tooltip=None,
            selection_bias=_selection_bias(k_observed, k_distinct_specs),
            walk_forward=None,
            f_star_interval=None,
            effective_cap=None,
            boundary_exclusion=None,
            sample_detail=None,
            original_values=None,
            overwrite_notice=_overwrite_notice(None),
            k_observed=k_observed,
            k_distinct_specs=k_distinct_specs,
        )

    imported = row.source == "backtest"
    hand_keyed = row.source in {"manual", "backtest_overridden"}
    inputs = kelly_inputs_of(row, ci_includes_no_edge=ci_includes_no_edge(row))
    assert inputs is not None  # a real row always builds one
    interval, cap = _f_star_interval(row, inputs, budget)
    detail = _sample_detail(row) if imported else None
    original = _original_values(row)

    selection_bias = _selection_bias_for_row(
        row, k_observed=k_observed, k_distinct_specs=k_distinct_specs
    )
    if selection_bias == KELLY_SELECTION_BIAS_UNLOGGED:
        # 條件 98 keeps this log beside the sentence (條件 28 precedent): the user
        # is told the record is missing, and an operator is told which row.
        logger.error(
            "kelly selection-bias counts unavailable: no attempt logged for a "
            "row with backtest provenance: symbol=%s market=%s source=%s",
            row.symbol,
            row.market,
            row.source,
        )

    source_statement, source_label = _SOURCE_STATEMENTS[row.source]
    return KellyDisclosuresView(
        freshness_badge_label=_FRESHNESS_BADGES[ageing_of(row).freshness],
        source_statement=source_statement,
        source_label=source_label,
        win_rate_disclosure=(
            KELLY_WIN_RATE_IS_NOT_PROBABILITY
            if imported
            else KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY
        ),
        manual_input_disclosure=KELLY_MANUAL_INPUT_DISCLOSURE if hand_keyed else None,
        manual_input_tooltip=KELLY_MANUAL_INPUT_TOOLTIP if hand_keyed else None,
        selection_bias=selection_bias,
        walk_forward=(
            KELLY_WALK_FORWARD_SCOPE if imported or original is not None else None
        ),
        f_star_interval=interval,
        effective_cap=cap,
        boundary_exclusion=KELLY_BOUNDARY_TRIP_EXCLUSION if detail is not None else None,
        sample_detail=detail,
        original_values=original,
        overwrite_notice=_overwrite_notice(row),
        k_observed=k_observed,
        k_distinct_specs=k_distinct_specs,
    )


def ci_includes_no_edge(row: KellyInputRow) -> bool:
    """Whether the stored f* interval covers "no edge" (約束 36).

    The whole of what the risk layer learns about the interval: one boolean,
    reduced here because ``app/advice/limits.py`` may branch but may not compute
    a statistic, and because handing it the bounds would put a clamp within
    reach of a module forbidden to have one (約束 34).

    ``f_star_ci_low <= 0`` is the test. A row with no interval at all -- every
    manual pair, and any import predating the interval columns -- is ``False``:
    the flag reports that the interval *was seen to* include zero, and (a-2)
    states it as a finding about this estimate. Reporting it for a row that has
    no interval would be a finding about a measurement nobody made.
    """
    return row.f_star_ci_low is not None and row.f_star_ci_low <= 0.0


def kelly_inputs_for(
    store: KellyInputStore, symbol: str, market: Market
) -> KellyInputs | None:
    """Cap 5's input for one holding, or ``None`` when none was ever entered.

    The one place the "read the row -> reduce the interval -> age it" chain is
    assembled, so the advice card, the portfolio overview and the alert loop
    all put the same pair in front of cap 5. It sits in this module because D-8
    makes it the single point allowed to touch the storage package and the risk
    package at once.
    """
    row = store.get(symbol, market)
    if row is None:
        return None
    return kelly_inputs_of(row, ci_includes_no_edge=ci_includes_no_edge(row))


def kelly_inputs_by_symbol(store: KellyInputStore) -> dict[tuple[str, Market], KellyInputs]:
    """Every stored pair, keyed the way the book-level caps group holdings.

    One read for the whole overview rather than one per holding. The key is the
    normalised symbol and the market, which is what
    ``app.advice.book_limits._group_positions`` groups on and what
    ``kelly_inputs`` is keyed on (D-1) -- the two normalisations are the same
    function (:func:`app.kelly.models.normalize_symbol`), so a pair and the
    holding it constrains cannot end up under two spellings of one ticker.
    """
    built: dict[tuple[str, Market], KellyInputs] = {}
    for row in store.list_all():
        inputs = kelly_inputs_of(row, ci_includes_no_edge=ci_includes_no_edge(row))
        if inputs is not None:  # pragma: no branch - a real row always builds
            built[(normalize_symbol(row.symbol), row.market)] = inputs
    return built


def _not_found(symbol: str, market: Market) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=KELLY_INPUT_NOT_FOUND_MESSAGE.format(symbol=symbol, market=market),
    )


@router.get("", response_model=KellyInputListView)
def list_kelly_inputs(store: KellyStoreDep) -> KellyInputListView:
    """Every Kelly input on file, in key order (D-8).

    Not filtered by freshness: an expired input is part of the answer to "what
    has been entered", and dropping it here would leave a caller unable to tell
    a stale pair from one that was never entered. Nothing is read from the
    import-attempt log (約束 35) -- what is in force is read from the input rows
    themselves.
    """
    return KellyInputListView(
        items=[_view(row) for row in store.list_all()], as_of=now_iso()
    )


@router.get("/{symbol}", response_model=KellyInputView)
def read_kelly_input(
    symbol: str, store: KellyStoreDep, market: MarketQuery = "TW"
) -> KellyInputView:
    """The input in force for one instrument, with its age.

    An expired input is returned like any other, carrying ``freshness:
    expired``. Withholding it would make "entered a long time ago" look like
    "never entered", and those two states are not the same thing to a user who
    has to decide what to do next.
    """
    row = store.get(symbol, market)
    if row is None:
        raise _not_found(normalize_symbol(symbol), market)
    return _view(row)


@router.get("/{symbol}/disclosures", response_model=KellyInputDisclosuresView)
def read_kelly_disclosures(
    symbol: str,
    store: KellyStoreDep,
    attempts: KellyAttemptsDep,
    settings_store: SettingsDep,
    market: MarketQuery = "TW",
) -> KellyInputDisclosuresView:
    """One instrument's Kelly screen, with every sentence already chosen.

    A second read beside ``GET /{symbol}`` rather than more fields on it: this
    one costs two counting queries against the attempt log, and the list
    endpoint would pay them per row for a summary that shows no disclosure at
    all. The row itself is returned here too, so a surface needs one call and
    cannot end up rendering a pair from one response and sentences from another.

    **200 with ``kelly_input: null`` where ``GET /{symbol}`` returns 404.** The
    two answer different questions: that one reports whether a pair exists, this
    one describes a screen, and "nothing has been entered" is a state the screen
    has copy for -- the ``尚未輸入`` badge, and (b), which outlives every refused
    import that left an attempt behind and no row.

    Both counts are read **after** the row (約束 30 order does not apply here --
    nothing is being written), and they are live rather than the
    ``k_observed_at_write`` snapshot: an attempt made since the input was stored
    still widened the search (b) discloses.

    The risk budget is loaded from the settings store, exactly as
    ``app/api/advice.py``, ``app/api/portfolio.py``, ``app/api/alerts.py`` and
    the scheduler load it (條件 87). The effective cap this endpoint reports and
    the one cap 5 enforces are then the same number by construction -- reading
    the defaults here would publish a larger allowance than the system grants.

    條件 94: the dialog variant is derived from the row read on this call, so a
    surface must re-read before it opens the dialog rather than caching a
    variant across an edit that changes the source.

    條件 97: no (g) sentence is in this response. Those five belong to cap 5 and
    ship in its detail, so the ``expired`` badge here may only be rendered on a
    screen that also carries cap 5's line.

    條件 101: both counts are read here, **after** any append that could have
    moved them, and the K branch is chosen from what is read. A cached count
    rendered before an append would let 條件 96's sentence and 元件 B's "已計入
    K_observed" appear together, and those two contradict each other.
    """
    row = store.get(symbol, market)
    stored_symbol = normalize_symbol(symbol)
    k_observed = attempts.k_observed(stored_symbol, market)
    return KellyInputDisclosuresView(
        kelly_input=None if row is None else _view(row),
        disclosures=_disclosures(
            row,
            budget=settings_store.load().risk_budget,
            k_observed=k_observed,
            k_distinct_specs=attempts.k_distinct_specs(stored_symbol, market),
        ),
        as_of=now_iso(),
    )


@router.put("/{symbol}", response_model=KellyInputView)
def write_kelly_input(
    symbol: str, body: KellyManualInput, store: KellyStoreDep, market: MarketQuery = "TW"
) -> KellyInputView:
    """Store a hand-entered pair for one instrument.

    A first write creates a ``manual`` row with no provenance -- there is none,
    and a fabricated ``strategy_id`` would make a typed number look measured.
    A write over an imported row keeps everything the import established and
    only moves the effective pair, marking the row ``backtest_overridden``.

    Range violations never reach this function: they are refused by
    :class:`KellyManualInput` as a 422 naming the field and its bound, and
    nothing is written, so the previously stored pair still stands.
    """
    current = store.get(symbol, market)
    if current is None or current.source == "manual":
        record = KellyInputRecord.manual(
            symbol=symbol,
            market=market,
            win_rate=body.win_rate,
            payoff_ratio=body.payoff_ratio,
        )
    else:
        record = KellyInputRecord.overriding(
            current, win_rate=body.win_rate, payoff_ratio=body.payoff_ratio
        )
    saved = store.upsert(record)
    # No history table (D-2), but the change does leave a trace.
    logger.info(
        "kelly input written: symbol=%s market=%s source=%s win_rate=%.4f "
        "payoff_ratio=%.4f previous_source=%s",
        saved.symbol,
        saved.market,
        saved.source,
        saved.win_rate,
        saved.payoff_ratio,
        None if current is None else current.source,
    )
    return _view(saved)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kelly_input(
    symbol: str, store: KellyStoreDep, market: MarketQuery = "TW"
) -> Response:
    """Remove the input in force for one instrument.

    Only the input row. The import-attempt log keeps every row it had, so
    ``K_observed`` is unchanged by this call (約束 35).
    """
    if not store.delete(symbol, market):
        raise _not_found(normalize_symbol(symbol), market)
    logger.info(
        "kelly input deleted: symbol=%s market=%s", normalize_symbol(symbol), market
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------
# Import path: re-run a backtest server-side and store what it produced (D-3)
# --------------------------------------------------------------------------


def _canonical_spec(body: BacktestRequest) -> tuple[str, str]:
    """The request as canonical JSON, plus its sha256.

    Key-sorted and separator-tight, so two bodies describing the same run
    serialise identically whatever order their fields arrived in. That matters
    twice: the hash is the identity of a spec (``K_distinct_specs`` counts
    distinct hashes) and it is the source of the bootstrap seed, so an unstable
    serialisation would make a re-import of the same spec unreproducible and
    inflate the distinct-spec count at the same time.

    The spec holds a symbol, a window, a strategy id and a cost model -- no
    credential of any kind -- so storing it indefinitely is safe.
    """
    spec = json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return spec, hashlib.sha256(spec.encode("utf-8")).hexdigest()


def _bootstrap_seed(spec_hash: str) -> int:
    """The seed for this spec's bootstrap: the first 32 bits of its hash (約束 27).

    Derived rather than random so the same spec re-run against the same bars
    reproduces the same interval. That is the exact and only claim: the bars are
    fetched again on every import and may have changed, so reproducibility is
    "same spec **and** same bars", never "same spec".
    """
    return int(spec_hash[:8], 16)


def _measured_columns(
    attribution: RoundTripAttribution, *, dates: list[str]
) -> dict[str, Any]:
    """The sample facts an attempt row and a stored row both carry.

    ``oos_observations`` is the number of **bars** the out-of-sample window
    spans, not the number of round trips. The two answer different questions --
    how long the segment was, versus how many completed trades it contained --
    and a sample of twenty-something round trips cannot be read without both.

    The dates are looked up by the same bar indices the attribution used, so the
    window described here is the window the sample was taken from rather than a
    date range that happens to agree with it (約束 23).
    """
    stats = attribution.stats
    return {
        "win_rate": stats.round_trip_win_rate,
        "payoff_ratio": stats.round_trip_payoff_ratio,
        "oos_round_trips": stats.n,
        "oos_win_trips": stats.n_win,
        "oos_loss_trips": stats.n_loss,
        "oos_excluded_boundary_trips": attribution.excluded_boundary_trips,
        "oos_open_trip_at_end": attribution.open_trip_at_end,
        "oos_start_date": dates[attribution.window_start],
        "oos_end_date": dates[attribution.window_stop - 1],
        "oos_observations": attribution.window_stop - attribution.window_start,
    }


def _append_attempt(
    attempts: KellyAttemptStore,
    *,
    symbol: str,
    market: Market,
    strategy_id: str,
    request_spec: str,
    spec_hash: str,
    reason_code: KellyGateReasonCode | None,
    measured: dict[str, Any],
) -> None:
    """Append one attempt to the log, or fail the whole import (約束 29).

    A failure here is never swallowed. An import that went ahead without its
    attempt being recorded would under-report ``K_observed`` permanently, and
    ``K_observed`` is the whole basis of the selection-bias disclosure: it is
    better to refuse an import that would otherwise have succeeded than to keep
    a number whose search history is missing a row.

    ``outcome`` follows the gate verdict, not the storage result (D-2): the row
    below is written before the input row exists, and it stays true whatever
    happens next.
    """
    record = KellyAttemptRecord(
        symbol=symbol,
        market=market,
        strategy_id=strategy_id,
        request_spec=request_spec,
        spec_hash=spec_hash,
        outcome="rejected" if reason_code is not None else "ok",
        reason_code=reason_code,
        **measured,
    )
    try:
        attempts.append(record)
    except Exception as error:
        logger.exception(
            "kelly import attempt could not be logged: symbol=%s market=%s spec_hash=%s",
            symbol,
            market,
            spec_hash,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=KELLY_ATTEMPT_LOG_FAILED_MESSAGE,
        ) from error


@router.post("/{symbol}/import-backtest", response_model=KellyInputView)
def import_kelly_input_from_backtest(
    symbol: str,
    body: BacktestRequest,
    store: KellyStoreDep,
    attempts: KellyAttemptsDep,
    resolver: ResolverDep,
    settings_store: SettingsDep,
    dividend_store: DividendStoreDep,
    market: MarketQuery = "TW",
) -> KellyInputView:
    """Re-run a backtest here and store the p/b **this server** computed (D-3).

    The body is a backtest request, not a result: there is no ``backtest_id`` to
    quote because runs are not stored, so the only way to attach a run's
    authority to a pair of numbers is to produce them here. Everything about the
    run travels with the row -- strategy, window, out-of-sample segment, whether
    rates were verified, whether 除權息 was restored -- because that provenance
    is all a later reader has.

    The order of the gates is the order that spends the least and says the most:
    the symbol check first (a request whose result could not be stored anywhere
    should not spend a data-provider call proving it), then whether the run
    produced a report at all, then the sample-size gates, whose message names
    the count that fell short. Each of them appends its verdict to the attempt
    log before refusing.

    p and b come from **completed round trips** of the out-of-sample window
    (:mod:`app.backtest.episodes`), never from the fill-level ``win_rate`` /
    ``profit_factor`` of the report: the daily rebalance emits a tail of tiny
    closing fills, and counting those as trades would both inflate the sample
    past the gate and distort the rate itself (ADR-0006 Context 事實 5).

    A successful import writes ``source="backtest"`` over whatever was there.
    An imported row later edited by hand becomes ``backtest_overridden`` through
    ``PUT``; re-importing is the user replacing the whole row with a fresh
    measurement, so the previous hand edit does not survive it.
    """
    stored_symbol = normalize_symbol(symbol)
    request_spec, spec_hash = _canonical_spec(body)

    def refuse(review: KellySampleGateReview, measured: dict[str, Any]) -> HTTPException:
        """Log the refusal, then hand back the 422 for the caller to raise.

        The three disclosure fields are filled **after** the append, in that
        order for a reason: 元件 B states that this attempt was counted, so the
        counts quoted beside it have to be the ones that already include it.
        """
        assert review.reason_code is not None and review.rejection is not None
        _append_attempt(
            attempts,
            symbol=stored_symbol,
            market=market,
            strategy_id=body.strategy,
            request_spec=request_spec,
            spec_hash=spec_hash,
            reason_code=review.reason_code,
            measured=measured,
        )
        logger.info(
            "kelly import refused: symbol=%s market=%s strategy=%s reason=%s",
            stored_symbol,
            market,
            body.strategy,
            review.reason_code,
        )
        k_observed = attempts.k_observed(stored_symbol, market)
        k_distinct_specs = attempts.k_distinct_specs(stored_symbol, market)
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=KellyImportRefusal(
                reason_code=review.reason_code,
                message=review.rejection,
                # 落地條件 13: the frame belongs to the three sample-size codes
                # and to no other. The membership test is the condition itself,
                # written out rather than inferred from the message.
                frame=(
                    KELLY_REFUSAL_FRAME
                    if review.reason_code in _SAMPLE_SIZE_REASON_CODES
                    else None
                ),
                attempt_logged=KELLY_REFUSAL_ATTEMPT_LOGGED,
                selection_bias=_selection_bias(k_observed, k_distinct_specs),
                k_observed=k_observed,
                k_distinct_specs=k_distinct_specs,
            ).model_dump(),
        )

    matched = review_symbol_match(
        path_symbol=symbol,
        path_market=market,
        body_symbol=body.symbol,
        body_market=body.market,
    )
    if not matched.passed:
        raise refuse(matched, {})

    run = execute_backtest(
        body,
        resolver=resolver,
        settings_store=settings_store,
        dividend_store=dividend_store,
    )
    ready = review_result_status(run.response.status)
    if not ready.passed:
        raise refuse(ready, {})
    result = run.result
    # ``status == "ok"`` is exactly the branch that produced both (see
    # :class:`app.api.backtest.BacktestRun`), and this is the only
    # ``BacktestResult`` this handler will ever hold (約束 31).
    assert result is not None and run.folds

    start, stop = oos_window(run.folds)
    attribution = attribute_round_trips(result, start=start, stop=stop)
    stats = attribution.stats
    measured = _measured_columns(attribution, dates=result.dates)

    sample = review_sample(stats.n, stats.n_win, stats.n_loss)
    if not sample.passed:
        raise refuse(sample, measured)
    pair = review_estimates(stats.round_trip_win_rate, stats.round_trip_payoff_ratio)
    if not pair.passed:
        # Unreachable through the gate above -- a missing p needs an empty
        # sample and a missing b needs an empty side, both of which the counts
        # already refused. Kept because "unreachable" is a property of today's
        # gate, and a pair of ``None``s must never reach the store.
        raise refuse(pair, measured)
    win_rate = stats.round_trip_win_rate
    payoff_ratio = stats.round_trip_payoff_ratio
    assert win_rate is not None and payoff_ratio is not None  # review_estimates

    p_ci = wilson_interval(stats.n_win, stats.n)
    assert p_ci is not None  # the gate guarantees a non-empty sample
    fraction = bootstrap_fraction_ci(
        episode_returns(attribution.episodes),
        fraction_fn=kelly_fraction,
        seed=_bootstrap_seed(spec_hash),
        draws=BOOTSTRAP_DRAWS,
    )

    if not (math.isfinite(fraction.low) and math.isfinite(fraction.high)):
        # 約束 27: a non-finite bound is a should-not-happen under the 20/5/5
        # gate (it takes a resample with no losses, or no wins, to land on the
        # 2.5% tail). Storing it would put an infinity into SQLite and into
        # every JSON response that later reads the row, so the import fails
        # instead. The attempt is still logged -- it happened, and its gate
        # verdict really was "ok" -- with the interval columns left null,
        # because a null reads as "not recorded" while an infinity would read
        # as a measurement.
        _append_attempt(
            attempts,
            symbol=stored_symbol,
            market=market,
            strategy_id=body.strategy,
            request_spec=request_spec,
            spec_hash=spec_hash,
            reason_code=None,
            measured=measured,
        )
        logger.error(
            "kelly import produced a non-finite f* interval: symbol=%s market=%s "
            "spec_hash=%s low=%s high=%s",
            stored_symbol,
            market,
            spec_hash,
            fraction.low,
            fraction.high,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=KELLY_NON_FINITE_INTERVAL_MESSAGE,
        )

    _append_attempt(
        attempts,
        symbol=stored_symbol,
        market=market,
        strategy_id=body.strategy,
        request_spec=request_spec,
        spec_hash=spec_hash,
        reason_code=None,
        measured={
            **measured,
            "kelly_fraction": fraction.point,
            "f_star_ci_low": fraction.low,
            "f_star_ci_high": fraction.high,
        },
    )
    # Counted after the append, so the row records the K that includes itself:
    # every attempt ever made on this key, refused ones included (約束 30).
    k_observed = attempts.k_observed(stored_symbol, market)

    saved = store.upsert(
        KellyInputRecord(
            symbol=stored_symbol,
            market=market,
            # The effective pair and the imported pair are the same thing at
            # write time (約束 4); a later hand edit moves the first and leaves
            # the second where it is.
            win_rate=win_rate,
            payoff_ratio=payoff_ratio,
            source="backtest",
            backtest_win_rate=win_rate,
            backtest_payoff_ratio=payoff_ratio,
            strategy_id=body.strategy,
            window_start=result.dates[0],
            window_end=result.dates[-1],
            oos_start_date=measured["oos_start_date"],
            oos_end_date=measured["oos_end_date"],
            produced_at=run.response.as_of,
            rates_verified=run.response.rates_verified,
            dividend_reason_code=str(run.response.dividend_adjustment["reason_code"]),
            adjust_dividends=body.adjust_dividends,
            oos_round_trips=stats.n,
            oos_win_trips=stats.n_win,
            oos_loss_trips=stats.n_loss,
            oos_excluded_boundary_trips=attribution.excluded_boundary_trips,
            oos_open_trip_at_end=attribution.open_trip_at_end,
            oos_observations=measured["oos_observations"],
            # Disclosure and audit only, all six of them (約束 34). The cap
            # recomputes its fraction from the effective pair above.
            p_ci_low=p_ci.low,
            p_ci_high=p_ci.high,
            f_star=fraction.point,
            f_star_ci_low=fraction.low,
            f_star_ci_high=fraction.high,
            bootstrap_seed=fraction.seed,
            bootstrap_draws=fraction.draws,
            bootstrap_degenerate_no_loss_draws=fraction.degenerate_no_loss_draws,
            bootstrap_degenerate_no_win_draws=fraction.degenerate_no_win_draws,
            spec_hash=spec_hash,
            low_sample_warning=sample.low_sample_warning,
            k_observed_at_write=k_observed,
        )
    )
    logger.info(
        "kelly input imported: symbol=%s market=%s strategy=%s win_rate=%.4f "
        "payoff_ratio=%.4f round_trips=%d k_observed=%d spec_hash=%s",
        saved.symbol,
        saved.market,
        body.strategy,
        saved.win_rate,
        saved.payoff_ratio,
        stats.n,
        k_observed,
        spec_hash,
    )
    return _view(saved)
