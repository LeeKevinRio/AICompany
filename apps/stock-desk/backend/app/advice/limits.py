"""The risk budget and the caps every recommendation is measured against.

:class:`RiskBudget` holds the numbers (conservative defaults, meant to be
editable later from a settings page -- hence a plain pydantic model that
round-trips to JSON rather than an env-only settings object).
:class:`PortfolioContext` holds everything about *this* symbol and the book
around it that a cap needs.

Two conventions that make the output honest rather than merely reassuring:

* A cap whose inputs are missing reports ``not_evaluable`` with the reason. It
  is never silently reported as ``passed``. Since FR-12 the sector cap has a
  field to read, so what may be missing is a value the user has not filed in.
* A cap is ``violated`` when the observed value **reaches or exceeds** the
  threshold (``>=``), not only when it strictly exceeds it: at exactly the cap
  the budget is already spent, so there is no room left to add.

Denominators are not interchangeable (FR-9 option B, risk-compliance decision
2026-08-05). ``total_equity_twd`` is the valued book and stays the denominator
of caps 1 and 4 exactly as before. The gross-exposure cap (cap 3) is the only
one that divides by :class:`SelfReportedNetWorth`, the figure the user typed in
themselves. Swapping the two would silently *widen* caps 1 and 4 -- a net worth
including cash is normally larger than the valued book, so ratios would shrink
and holdings that are ``violated`` today would turn into ``passed`` with no
visible cause. The two numbers therefore never meet.

Currency: book-level amounts are TWD (the reporting currency, as in
``app/portfolio``); ``close`` and ``atr`` are in the instrument's own currency
and are converted with ``fx_to_twd`` at the single point where share sizing
happens. Values here are ``float`` (like the signal layer), not ``Decimal``:
these are indicative ranges derived from statistics, not accounting figures.

Cap 5 imports its Chinese sentences from :mod:`app.api.kelly_wording` rather
than spelling them out here. That module imports nothing at all -- it is text
and nothing else -- so the direction costs no coupling, and it is what 落地條件
2 requires: every risk-approved Kelly sentence has exactly one copy in the repo,
and a second one retyped into this file would drift away from the approved
inventory without failing a build. What this module may **not** import is
``app/kelly`` (約束 12): the pair reaches cap 5 already aged, through
:class:`KellyInputs`, because a risk cap that could read the clock or the
database would be a risk cap whose verdict depends on when it was asked.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.api.kelly_wording import (
    KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE,
    KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY,
    KELLY_NON_POSITIVE_FRACTION_DETAIL,
    KELLY_NOT_EVALUABLE_BACKTEST_EXPIRED,
    KELLY_NOT_EVALUABLE_MANUAL_EXPIRED,
    KELLY_NOT_EVALUABLE_NO_INPUT,
    KELLY_NOT_EVALUABLE_NO_OOS_END_DATE,
    KELLY_NOT_EVALUABLE_OVERRIDDEN_EXPIRED,
    KELLY_NOT_EVALUABLE_OVERRIDDEN_NO_OOS_END_DATE,
    KELLY_WIN_RATE_IS_NOT_PROBABILITY,
    KELLY_ZERO_ALLOWANCE_RANGE_NOTE,
)

LimitStatus = Literal["passed", "violated", "not_evaluable"]

#: A cap's verdict as ``(status, detail, observed, threshold)``.
CheckResult = tuple[LimitStatus, str, float | None, float | None]

#: Fixed order of the caps; the 1-based index in this tuple is the "第 X 條上限"
#: quoted on the advice card when a cap blocks an ``add``.
LIMIT_IDS: tuple[str, ...] = (
    "single_position_weight",
    "sector_weight",
    "gross_exposure",
    "per_trade_loss",
    "kelly_fraction",
)

LIMIT_NAMES: dict[str, str] = {
    "single_position_weight": "單一標的佔比上限",
    "sector_weight": "單一產業佔比上限",
    "gross_exposure": "總曝險上限",
    "per_trade_loss": "單筆最大可承受虧損",
    "kelly_fraction": "分數 Kelly 部位上限",
}

#: The action label quoted at the head of every quantity-range ``basis``, one
#: entry per action that can produce a range (``hold`` and ``insufficient_data``
#: never do). The values are contract-bound to ``HELD_ACTION_LABELS`` in
#: ``frontend/app/lib/adviceWording.ts``: the card headline and this sentence
#: name the same action, so two spellings of it would read as two verdicts.
#: ``test_advice_limits.py`` reads that file and compares the four keys, so the
#: tables cannot drift apart silently.
#:
#: 風控核可文案,修改須重新送審(2026-08-09)
RANGE_ACTION_LABELS: dict[str, str] = {
    "add": "加碼參考",
    "reduce": "減碼參考",
    "take_profit": "分批獲利了結參考",
    "stop_loss": "停損評估",
}

#: Tolerance used when comparing an observed ratio against a cap, so that a
#: value that is mathematically equal to the cap is not missed by float noise.
EPSILON = 1e-9

#: The lower edge of a suggested quantity range is this fraction of the upper
#: edge -- a range, never a single "correct" number.
RANGE_LOWER_RATIO = 0.5

#: How many single-share steps a suggested quantity may be walked back (or up)
#: while verifying it against the binding cap. The arithmetic edge is already
#: within one share of the answer; the bound only stops a pathological budget
#: from spinning, and giving up yields "no suggestion" rather than a bad one.
MAX_SIZING_ADJUSTMENTS = 8

#: Hard ceiling on ``RiskBudget.max_position_weight``. Past half of total equity
#: a single name *is* the portfolio, so diversification has stopped meaning
#: anything and the remaining caps would be measuring a book of one.
#:
#: Both ceilings below were approved in writing by the CEO on 2026-07-26 after
#: risk-compliance review. Raising either one is a governance decision, not a
#: code change: get risk sign-off and a fresh CEO approval first, then edit the
#: constant and record it here. Never widen one to make a test or a demo pass.
MAX_POSITION_WEIGHT_CEILING = 0.50
MAX_POSITION_WEIGHT_REASON = "單一標的超過總資產的一半時，分散化已無實質意義。"

#: Hard ceiling on ``RiskBudget.max_gross_exposure``. Moderate leverage is a
#: legitimate preference; 2x is a different risk profile than the quantities
#: this engine sizes.
MAX_GROSS_EXPOSURE_CEILING = 1.50
MAX_GROSS_EXPOSURE_REASON = "此處容許適度槓桿，但不容許 2 倍的總曝險。"

#: How long a self-reported net worth may serve as the gross-exposure
#: denominator, and when its reader starts being told it is ageing (FR-9 (b)).
#: A net worth moves with both market value and cash flows, so past about one
#: reconciliation cycle it no longer describes the account it claims to; the
#: cap then reports ``not_evaluable`` rather than a ``passed`` derived from a
#: figure nobody has confirmed lately. The soft notice exists so the cap does
#: not simply vanish one morning without warning.
#:
#: Governed like the two ceilings above: these are risk parameters, and
#: **extending the 30 days needs written CEO approval** on top of risk
#: sign-off. Never widen either one to make a test or a demo pass.
NET_WORTH_STALE_AFTER_DAYS = 30
NET_WORTH_SOFT_NOTICE_DAYS = 7

#: How long a Kelly input may drive cap 5 (D-4). A **separate** constant from
#: the net-worth pair above even though the two share a value today: they
#: answer different questions and either may move without the other (the same
#: reason :mod:`app.kelly.models` gives for its own pair).
#:
#: It is declared here, and not imported, because 約束 12 keeps ``app/kelly``
#: out of the risk layer -- and it is *used* here, not in the builder, because
#: D-6 puts the expiry decision inside :func:`_check_kelly_fraction`, exactly
#: where :data:`NET_WORTH_EXPIRED_DETAIL` puts the net worth's. The age itself
#: is handed in: this module owns no clock.
#:
#: ``app.kelly.models.KELLY_STALE_AFTER_DAYS`` is the same window seen from the
#: storage side, so the two are pinned equal by ``tests/test_advice_limits.py``.
#: They may not drift: cap 5 would then refuse a pair the settings page still
#: shows as usable, or keep computing from one it calls expired.
KELLY_STALE_AFTER_DAYS = 30

#: AC-12.3: the states this cap can be missing an industry in are different
#: problems and must not share a sentence. ``sector is None`` covers five of
#: them, and only one is fixed by filing a value:
#:
#: * ``no_position`` -- nothing is held, so there is no position to classify;
#: * ``unfiled`` -- a TW *stock* holding carries no category yet (the
#:   actionable one);
#: * ``etf_instrument`` -- every TW holding behind the symbol is an ETF
#:   (``etf`` / ``leveraged_etf`` / ``futures_etf``). TWSE's industry taxonomy
#:   classifies individual companies, not funds, so "fill the industry in" is
#:   an instruction the owner cannot meaningfully follow (D6, CEO 實測回報
#:   2026-08-13: 00631L/00685L/00981A were shown the ``unfiled`` guidance).
#:   The ETF stays excluded from the cap exactly as before -- only the stated
#:   cause changes;
#: * ``unsupported_market`` -- the holding is in a market this product has no
#:   taxonomy for. Telling its owner to "fill the industry in" would point at a
#:   write the API answers with a 422 (:mod:`app.positions.sectors`), so that
#:   promise is absent from this sentence on purpose;
#: * ``mixed`` -- the same symbol was filed under two categories, which is not
#:   "not stated" at all, so it reuses :data:`SECTOR_MIXED_NOTE` rather than
#:   telling the user they left a field empty.
#:
#: The five are told apart by :attr:`PortfolioContext.sector_gap`, which the
#: book adapter sets: this module never infers a market or a holding.
#:
#: Wording reviewed and approved by risk-compliance on 2026-08-09 (FR-12 句 1
#: 修正句), recorded in ``work/reviews/c1-phase8-review.md``. Those four
#: sentences are risk-approved copy: changing any of them needs a fresh review.
#: :data:`NO_SECTOR_ETF_DETAIL` (added 2026-08-16 for D6) was approved by
#: risk-compliance on the same terms, and R-D6-1 of that same review required a
#: second sentence after it (see :data:`NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL`).
#: The ``unsupported_market`` residual disclosure (D8 句 2, approved 2026-08-19)
#: is governed the same way -- see
#: :data:`NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL`.
SectorGap = Literal[
    "no_position", "unfiled", "etf_instrument", "unsupported_market", "mixed"
]

NO_SECTOR_CANDIDATE_DETAIL = (
    "此標的目前沒有持倉，單一產業佔比上限沒有可分類的部位，本次不計算，回報 not_evaluable。"
)
NO_SECTOR_UNFILED_DETAIL = (
    "此標的的持倉尚未填寫產業別，單一產業佔比上限本次不計算，回報 not_evaluable。"
    "可在持倉編輯或 CSV 匯入填入台灣證交所產業別後啟用這條上限。"
)
#: D6 句 1, approved verbatim by risk-compliance on 2026-08-16: the cap is not
#: computed because the taxonomy classifies companies rather than funds.
NO_SECTOR_ETF_CAUSE_DETAIL = (
    "此標的的持倉為 ETF；台灣證交所產業別分類僅適用於個股，不適用於 ETF，"
    "單一產業佔比上限本次不計算，回報 not_evaluable。"
)

#: R-D6-1 (``work/reviews/2026-08-16-品質債清償批-覆核.md``), wording drafted in
#: ``work/stock-desk-D4-資料來源措辭.md`` 六 and confirmed verbatim by
#: risk-compliance on 2026-08-16. The cause sentence alone lets "the cap did
#: not run" be read as "there is nothing to worry about" -- an index ETF (a
#: leveraged one in particular) is frequently concentrated in a single
#: industry, and this product cannot see through the fund to say so. This
#: sentence states that limit of the system instead of leaving the silence to
#: be read as reassurance. It carries **no** action guidance on purpose.
#:
#: Concatenated into :data:`NO_SECTOR_ETF_DETAIL` rather than emitted by a
#: separate branch so the two sentences cannot come apart: every caller reads
#: the single mapping entry below, so there is no code path that publishes the
#: cause without this disclosure. The same gap on ``unsupported_market``,
#: 列管 here on 2026-08-16, now carries its own disclosure approved verbatim by
#: risk-compliance on 2026-08-19 (D8 句 2 CONFIRMED,
#: ``work/reviews/2026-08-19-三句補充揭露-風控批審.md``) -- see
#: :data:`NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL`. The two residual
#: constants are deliberately separate even though they differ only in subject
#: ("此 ETF" vs "此持倉"): each state's approved copy is pinned verbatim by its
#: own tests, so neither sentence can be edited through the other.
NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL = (
    "本上限不計算，不代表此 ETF 沒有產業集中風險；系統目前無法就此評估。"
)

NO_SECTOR_ETF_DETAIL = NO_SECTOR_ETF_CAUSE_DETAIL + NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL

#: The cause half of the ``unsupported_market`` sentence, unchanged from the
#: FR-12 wording approved on 2026-08-09: the taxonomy only covers TWSE, so the
#: cap is not computed, and no fill-in guidance is offered because that write
#: is answered with a 422 (:mod:`app.positions.sectors`).
NO_SECTOR_UNSUPPORTED_MARKET_CAUSE_DETAIL = (
    "此標的為非台股持倉；系統目前只提供台灣證交所產業別分類，"
    "尚未決定其他市場的分類方式，單一產業佔比上限本次不計算，回報 not_evaluable。"
)

#: D8 句 2, approved verbatim by risk-compliance on 2026-08-19
#: (``work/reviews/2026-08-19-三句補充揭露-風控批審.md``): "the cap did not
#: run" must not be readable as "there is no concentration risk" on this state
#: either, and "無法評估" is true here for its own reason -- no classification
#: scheme for other markets has been decided. Same rules as the ETF residual
#: sentence: it carries **no** action guidance on purpose, it is concatenated
#: below rather than emitted by a separate branch so the cause can never ship
#: without it, and it applies to ``unsupported_market`` only -- never to
#: ``unfiled`` / ``mixed`` / ``no_position``, whose wording was not reviewed
#: for it. This is its own constant, not a reuse of
#: :data:`NO_SECTOR_ETF_RESIDUAL_RISK_DETAIL` (subject "此持倉", not "此 ETF").
NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL = (
    "本上限不計算，不代表此持倉沒有產業集中風險；系統目前無法就此評估。"
)

NO_SECTOR_UNSUPPORTED_MARKET_DETAIL = (
    NO_SECTOR_UNSUPPORTED_MARKET_CAUSE_DETAIL
    + NO_SECTOR_UNSUPPORTED_MARKET_RESIDUAL_RISK_DETAIL
)

#: The same symbol held twice under two different categories: which one the
#: industry bucket belongs to is undecidable, so the question is refused rather
#: than answered with one of them (the mixed-currency precedent in
#: :mod:`app.advice.book`). Approved verbatim by risk-compliance on 2026-08-09
#: (FR-12 句 3), with the guidance sentence below added at their own suggestion;
#: it lives here rather than in ``book.py`` because cap 2's ``detail`` says the
#: same thing as the context note and the two must not drift apart.
SECTOR_MIXED_NOTE = (
    "此標的的持倉填了不只一種產業別，無法決定單一產業，單一產業佔比上限不計算。"
)
SECTOR_MIXED_GUIDANCE = "請將同一標的的持倉統一為同一種產業別後恢復計算。"
SECTOR_MIXED_DETAIL = SECTOR_MIXED_NOTE + SECTOR_MIXED_GUIDANCE

#: One sentence per state, so a new state cannot silently fall back to another
#: state's claim.
NO_SECTOR_DETAILS: dict[SectorGap, str] = {
    "no_position": NO_SECTOR_CANDIDATE_DETAIL,
    "unfiled": NO_SECTOR_UNFILED_DETAIL,
    "etf_instrument": NO_SECTOR_ETF_DETAIL,
    "unsupported_market": NO_SECTOR_UNSUPPORTED_MARKET_DETAIL,
    "mixed": SECTOR_MIXED_DETAIL,
}

#: AC-9.2: what cap 3 said before FR-9 existed, kept verbatim as the opening
#: sentence so a user who never entered a net worth sees no change at all, with
#: the one input that would make the cap evaluable named after it.
NO_NET_WORTH_DETAIL = (
    "缺少組合總市值，無法計算總曝險。"
    "可在設定頁輸入「帳戶總淨值（新台幣）」後啟用這條上限。"
)

#: AC-9.4. Wording is fixed: the reader has to be told the input expired, not
#: merely that something is missing.
NET_WORTH_EXPIRED_DETAIL = (
    "淨值輸入已超過 {days} 天未更新，最後輸入時間為 {reported_at}，距今 {age_days} 天；"
    "這條上限不以過期的淨值計算，請至設定頁更新帳戶總淨值後再評估。"
)

#: FR-9 (a-附加): the numerator only covers positions that could be valued, and
#: a short numerator makes the exposure look *lower* than it is -- the one
#: direction option B must never err in. So the cap is withheld rather than
#: reported from an incomplete book.
GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL = (
    "有部位無法估值，總曝險的分子不完整。分子漏算只會讓曝險看起來偏低，"
    "因此這條上限不計算，而不是以偏低的比率回報通過。"
)

#: FR-9 (a-附加) required disclosure, attached to every gross-exposure verdict
#: computed from a self-reported net worth. The three sentences cover the three
#: ways this particular ratio can mislead: its two halves come from different
#: places, its numerator is only as complete as the position list, and its
#: denominator is as old as the last time the user typed it in.
GROSS_EXPOSURE_MIXED_SOURCE_NOTE = (
    "分子（已估值部位市值合計）由系統計算，分母（帳戶總淨值）由使用者自報，兩者來源不同。"
)
GROSS_EXPOSURE_COVERAGE_NOTE = (
    "本比率假設持倉清單完整；未登錄的部位不計入分子，會讓曝險看起來偏低。"
)
GROSS_EXPOSURE_REPORTED_AT_NOTE = "自報淨值的輸入時間為 {reported_at}。"

#: The soft half of the freshness rule: still evaluated, but said out loud.
NET_WORTH_AGEING_NOTE = "此淨值已 {age_days} 天未更新，滿 {days} 天後這條上限將不再計算。"

#: Every human-readable timestamp in these disclosures is rendered in this zone
#: and labelled with it. Taipei because the reporting currency, the market and
#: the reader are all Taiwanese, and because the frontend already renders every
#: other timestamp the same way (``app/lib/format.ts``). Labelled because an
#: unlabelled local time is indistinguishable from an unconverted UTC one, and
#: those are eight hours apart -- on a freshness disclosure, that is exactly the
#: kind of ambiguity the sentence exists to remove.
DISCLOSURE_TZ = ZoneInfo("Asia/Taipei")
DISCLOSURE_TZ_LABEL = "台北時間"


def format_reported_at(reported_at: str) -> str:
    """An ISO timestamp as a sentence can carry it: local, to the minute, labelled.

    The stored value stays ISO-8601 UTC -- that is what machines read, and it is
    what :func:`app.advice.book.self_reported_net_worth` measures the age from.
    This is only for the prose the caps produce, where a bare
    ``2026-08-05T15:51:56.015754+00:00`` costs the reader something to decode and
    tells them nothing the minute does not: the rule it feeds is measured in
    days, so seconds and microseconds are noise.

    A real timezone conversion, never string surgery -- truncating the offset
    away would silently relabel a UTC instant as a local one. An unparseable
    value comes back untouched rather than half-formatted into something that
    looks like a time somebody checked.
    """
    try:
        moment = datetime.fromisoformat(reported_at)
    except ValueError:
        return reported_at
    if moment.tzinfo is None:
        # The same assumption ``app.advice.book`` makes about the same string,
        # and what ``app.settings.store`` writes.
        moment = moment.replace(tzinfo=UTC)
    return f"{moment.astimezone(DISCLOSURE_TZ):%Y-%m-%d %H:%M}（{DISCLOSURE_TZ_LABEL}）"


def _ceiling_message(label: str, ceiling: float, reason: str) -> str:
    """The 422 message for a cap a request tried to raise past its ceiling.

    It states the ceiling, why it sits there, and what it would actually take to
    move it -- a code change reviewed by risk-compliance and approved by the
    CEO. There is deliberately no request-level escape hatch to mention.
    """
    return (
        f"{label}最高只能設為 {ceiling:.2f}（{ceiling * 100:.0f}%）。{reason}"
        "這是硬性上界，放寬必須修改 app/advice/limits.py 的程式碼，"
        "並經風控（risk-compliance-officer）審查與 CEO 同意，"
        "無法由設定頁或 API 繞過。"
    )


def _ceiling_description(what: str, ceiling: float, reason: str) -> str:
    """The field ``description`` that carries a ceiling into the OpenAPI schema.

    The ceilings are enforced by field validators rather than ``le=`` (a ``le``
    failure would replace the message :func:`_ceiling_message` produces with
    pydantic's generic English one), and a validator contributes no ``maximum``
    keyword to the generated schema. Anyone reading ``/openapi.json`` or
    generating a client from it would therefore see an unbounded ``number``, so
    the bound is stated here in prose from the very same constants.
    """
    return (
        f"{what}上界 {ceiling:.2f}（{ceiling * 100:.0f}%），"
        f"超過即回 422：{reason}"
        "此上界由 field_validator 強制（不是 schema 的 maximum），"
        "放寬需修改 app/advice/limits.py 並經風控審查與 CEO 同意。"
    )


class RiskBudget(BaseModel):
    """The risk caps applied to every suggestion. Defaults are conservative.

    Every bound here is **policy, not preference**. The settings page writes
    this model verbatim (see :mod:`app.settings.models`), so whatever a field
    accepts is what a user can set with a single ``PUT``. Four fields therefore
    carry a hard ceiling that no request can pass:

    * ``max_position_weight`` -- at most :data:`MAX_POSITION_WEIGHT_CEILING`;
    * ``max_gross_exposure`` -- at most :data:`MAX_GROSS_EXPOSURE_CEILING`;
    * ``kelly_fraction_cap`` / ``kelly_position_cap`` -- a quarter of full Kelly
      and 10% of equity, unchanged.

    The first two used to accept 1.0 and 2.0, which let the settings page put a
    whole portfolio into one name, or 2x gross, with no gate at all. They are
    now enforced in validators that *say* what they are: a 422 quoting the
    ceiling and the reason. Not clamped (a silently clamped cap is a number the
    user would later believe they had set), not a dismissible warning, and not
    overridable through a flag a request could send -- raising them is a code
    change reviewed by risk-compliance and approved by the CEO.

    Because a validator leaves no ``maximum`` in the generated JSON schema,
    those two fields also state their ceiling in ``description`` (built from the
    same constants by :func:`_ceiling_description`), so a reader of
    ``/openapi.json`` sees the bound the API will actually enforce.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Bounded by :data:`MAX_POSITION_WEIGHT_CEILING`, not by 1.0.
    max_position_weight: float = Field(
        default=0.15,
        gt=0.0,
        description=_ceiling_description(
            "單一標的佔總資產的",
            MAX_POSITION_WEIGHT_CEILING,
            MAX_POSITION_WEIGHT_REASON,
        ),
    )
    max_sector_weight: float = Field(default=0.30, gt=0.0, le=1.0)
    #: Bounded by :data:`MAX_GROSS_EXPOSURE_CEILING`, not by 2.0.
    max_gross_exposure: float = Field(
        default=1.00,
        gt=0.0,
        description=_ceiling_description(
            "組合總曝險佔總資產的",
            MAX_GROSS_EXPOSURE_CEILING,
            MAX_GROSS_EXPOSURE_REASON,
        ),
    )
    #: Largest acceptable loss on one position, as a fraction of total equity.
    max_loss_per_trade: float = Field(default=0.01, gt=0.0, le=0.1)
    #: Stop distance = this multiple of ATR(14).
    atr_stop_multiple: float = Field(default=2.0, gt=0.0, le=10.0)
    #: Only fractional Kelly is allowed, at most a quarter of full Kelly.
    kelly_fraction_cap: float = Field(default=0.25, gt=0.0, le=0.25)
    #: Hard ceiling on any Kelly-derived position, whatever the edge estimate.
    kelly_position_cap: float = Field(default=0.10, gt=0.0, le=0.10)

    @field_validator("max_position_weight")
    @classmethod
    def _position_weight_within_ceiling(cls, value: float) -> float:
        if value > MAX_POSITION_WEIGHT_CEILING:
            raise ValueError(
                _ceiling_message(
                    LIMIT_NAMES["single_position_weight"],
                    MAX_POSITION_WEIGHT_CEILING,
                    MAX_POSITION_WEIGHT_REASON,
                )
            )
        return value

    @field_validator("max_gross_exposure")
    @classmethod
    def _gross_exposure_within_ceiling(cls, value: float) -> float:
        if value > MAX_GROSS_EXPOSURE_CEILING:
            raise ValueError(
                _ceiling_message(
                    LIMIT_NAMES["gross_exposure"],
                    MAX_GROSS_EXPOSURE_CEILING,
                    MAX_GROSS_EXPOSURE_REASON,
                )
            )
        return value


class SelfReportedNetWorth(BaseModel):
    """The account net worth the user typed in, as the gross-exposure cap sees it.

    All three fields travel together on purpose. An amount with no report time
    cannot be judged for freshness, and FR-9 (b) forbids computing a ``passed``
    from an unconfirmed figure -- so "how old is this" is part of the input,
    not an optional extra. ``age_days`` is handed in rather than derived
    because this module owns no clock (the rest of the risk layer has none
    either, which is what keeps it testable without freezing time).

    ``amount_twd`` must be positive here as well as at the settings boundary:
    a zero or negative denominator is not a preference to be clamped, it is a
    number no ratio can be built from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: TWD only. No FX conversion is ever applied to this field (FR-9 (f)).
    amount_twd: float = Field(gt=0.0)
    #: When the user reported it, as an ISO 8601 string, for the reader.
    reported_at: str
    #: Whole days between the report and the caller's "now", never negative.
    age_days: int = Field(ge=0)


#: The three ways a stored Kelly pair can have come about, spelled out again
#: rather than imported from :data:`app.kelly.models.KellySource`: 約束 12 keeps
#: ``app/kelly`` out of this module. ``tests/test_advice_limits.py`` asserts the
#: two literals hold the same values, so the copy cannot drift into a source
#: this layer would not recognise -- and mis-recognising one is not cosmetic,
#: because it decides whether (e) or (e-manual) is attached to a shown win rate
#: (落地條件 18: 互斥且窮盡).
KellyInputSource = Literal["manual", "backtest", "backtest_overridden"]


class KellyInputs(BaseModel):
    """The stored Kelly pair as cap 5 sees it: aged, sourced, and nothing more.

    One field on :class:`PortfolioContext` replaces the two bare ``win_rate`` /
    ``payoff_ratio`` columns cap 5 used to read (D-6). The reason is the pair
    was never the whole input: whether it may be used at all depends on where it
    came from and how old it is, and two loose floats let a caller supply the
    numbers while silently dropping the facts that qualify them.

    What is **not** here is as deliberate as what is. The stored interval
    bounds (for p and for ``f*``), the bootstrap parameters and the rest of the
    sample structure stay in storage (約束 34/36): they are disclosure material,
    and a risk layer holding them would be one edit away from clamping a cap
    with them. The single fact cap 5 gets from that family is
    :attr:`ci_includes_no_edge`, already reduced to a boolean by
    ``app/api/kelly.py``, because this module may branch but may not compute a
    statistic of any kind (約束 12/36).

    ``age_days`` is handed in for the reason :class:`SelfReportedNetWorth` gives:
    no clock lives here. **Whether that age is too old is decided here though**
    (D-6), against :data:`KELLY_STALE_AFTER_DAYS`, so the same rule that names
    the freshness window also enforces it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The effective pair -- what the user's cap is actually computed from. For
    #: ``backtest_overridden`` these are the hand-keyed values, not the imported
    #: ones (約束 4), which is why the source has to travel with them.
    win_rate: float = Field(ge=0.0, le=1.0)
    payoff_ratio: float = Field(gt=0.0)
    source: KellyInputSource
    #: Whole days since :attr:`anchored_at`, or ``None`` when the row has no
    #: anchor to count from (an imported pair carrying no OOS end date). The
    #: two are ``None`` together, and ``None`` is treated as expired rather than
    #: as young: an age nobody could establish is not evidence of freshness.
    age_days: int | None = Field(default=None, ge=0)
    #: The day the age counts from, as a plain ``YYYY-MM-DD`` calendar date and
    #: never an ISO datetime (6-A). A backtest anchor's time of day is padded,
    #: so showing it would be precision the measurement does not have; the
    #: builder in :mod:`app.advice.book` renders it, and the (g-2)/(g-3)
    #: sentences interpolate it verbatim.
    anchored_at: str | None = None
    #: Which strategy produced the pair; ``None`` for a hand-typed one (約束 2).
    strategy_id: str | None = None
    #: The out-of-sample segment the imported pair was measured over. 1-A wants
    #: both dates on the same screen as (e), so they travel with the pair.
    oos_start_date: str | None = None
    oos_end_date: str | None = None
    #: Complete round trips behind the estimate -- never a fill-level count
    #: (約束 25: fill counts are inflated by the daily rebalance).
    oos_round_trips: int | None = Field(default=None, ge=0)
    #: Whether the stored ``f*`` interval reaches zero or below, computed by
    #: ``app/api/kelly.py`` (約束 36). True means the interval covers "no edge",
    #: and cap 5 attaches (a-2) to say so.
    #: ``False`` also covers "no interval was ever stored" (every manual pair):
    #: the flag asserts that the interval was seen to exclude zero only when it
    #: is ``True``, and the sentence it gates is worded as a positive finding.
    ci_includes_no_edge: bool = False

    @model_validator(mode="after")
    def _age_and_anchor_travel_together(self) -> KellyInputs:
        """An age with no anchor (or an anchor with no age) is not a state.

        ``app.kelly.models.KellyAgeing`` produces the two together or neither,
        and the (g-2)/(g-3) sentences print both. Half a pair would leave one
        of them rendered from nothing.
        """
        if (self.age_days is None) != (self.anchored_at is None):
            raise ValueError("Kelly 輸入的錨點日期與計齡天數必須同時存在或同時不存在")
        return self


class PortfolioContext(BaseModel):
    """Everything the caps need about one symbol and the book around it.

    Every field except ``symbol`` is optional: a missing input turns the caps
    that need it into ``not_evaluable`` instead of producing a fabricated pass.
    A *candidate* (not yet held) is expressed as
    ``position_market_value_twd=0`` and ``quantity=0``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    total_equity_twd: float | None = Field(default=None, ge=0.0)
    position_market_value_twd: float | None = Field(default=None, ge=0.0)
    position_cost_twd: float | None = Field(default=None, ge=0.0)
    #: Numerator of cap 3: the whole book's valued market value in TWD. It is
    #: **not** divided by ``total_equity_twd`` (that would be 100% by
    #: construction) but by ``net_worth`` below.
    gross_exposure_twd: float | None = Field(default=None, ge=0.0)
    #: The user's own account net worth -- the only denominator cap 3 accepts,
    #: and a denominator no other cap may borrow (FR-9 option B). ``None`` (the
    #: normal state until the user fills the settings field in) leaves cap 3
    #: ``not_evaluable`` exactly as it was before FR-9.
    net_worth: SelfReportedNetWorth | None = None
    #: Whether *every* stored position could be valued. Cap 3 requires an
    #: explicit ``True``: unknown coverage is not evidence of a complete book,
    #: and an incomplete numerator understates exposure (FR-9 (a-附加)).
    book_fully_valued: bool | None = None
    quantity: float | None = Field(default=None, ge=0.0)
    #: Latest close in the instrument's own currency (what the rules compare).
    close: float | None = Field(default=None, gt=0.0)
    #: Instrument currency -> TWD; 1.0 for a TWD instrument.
    fx_to_twd: float = Field(default=1.0, gt=0.0)
    #: ATR(14) in the instrument's own currency; drives the stop distance.
    atr: float | None = Field(default=None, ge=0.0)
    #: TWSE industry category of this symbol's holdings (FR-12). ``None`` when
    #: the user has not filed this symbol under one -- the field exists, the
    #: value does not -- and the sector cap then reports ``not_evaluable``
    #: naming that specific gap.
    sector: str | None = None
    sector_market_value_twd: float | None = Field(default=None, ge=0.0)
    #: Which of the five ways a category can be missing applies here, set by
    #: :func:`app.advice.book.build_book_context` -- the only layer that can see
    #: the holdings behind the symbol and the market they sit in. ``None`` means
    #: the caller did not say, and cap 2 then falls back to the single thing
    #: this model can establish on its own (see :func:`_inferred_sector_gap`).
    sector_gap: SectorGap | None = None
    #: Cap 5's input, as one field rather than two loose floats (D-6). ``None``
    #: means **no pair has ever been entered for this symbol**, which is a
    #: different statement from "the pair is too old to use" -- the row is still
    #: there in that case and arrives here with its age, so cap 5 can say which
    #: of the two it is. Built by :func:`app.advice.book.kelly_inputs_of` from
    #: the stored row; ``None`` for every hand-assembled context, which is why
    #: the field defaults to it.
    kelly: KellyInputs | None = None

    def position_weight(self) -> float | None:
        """This symbol's share of total equity, or ``None`` if not computable."""
        if self.total_equity_twd is None or not self.total_equity_twd > 0.0:
            return None
        if self.position_market_value_twd is None:
            return None
        return self.position_market_value_twd / self.total_equity_twd

    def unrealized_pnl_pct(self) -> float | None:
        """Unrealized P&L as a fraction of cost, or ``None`` without a cost."""
        if self.position_cost_twd is None or not self.position_cost_twd > 0.0:
            return None
        if self.position_market_value_twd is None:
            return None
        return self.position_market_value_twd / self.position_cost_twd - 1.0

    def price_twd(self) -> float | None:
        """Latest close converted to TWD, used for share sizing."""
        if self.close is None:
            return None
        return self.close * self.fx_to_twd

    def held_shares(self) -> float | None:
        """Shares held: the explicit quantity, else derived from market value."""
        if self.quantity is not None:
            return self.quantity
        price = self.price_twd()
        if price is None or price <= 0.0 or self.position_market_value_twd is None:
            return None
        return self.position_market_value_twd / price


class LimitCheck(BaseModel):
    """One cap's verdict, with the numbers behind it."""

    model_config = ConfigDict(frozen=True)

    index: int
    id: str
    name: str
    status: LimitStatus
    detail: str
    observed: float | None
    threshold: float | None


class QuantityRange(BaseModel):
    """A share-count range implied by the binding cap, plus how it was derived.

    ``restores_compliance`` is the machine-readable half of what ``basis`` says
    in prose: whether acting on the suggested quantity actually leaves the
    binding cap non-violated. It is always ``True`` on the buy side (a buy that
    breaches the cap is never suggested) and can be ``False`` on the sell side
    when the cap is driven by *other* positions, so selling this whole holding
    still does not clear it.
    """

    model_config = ConfigDict(frozen=True)

    min_shares: int
    max_shares: int
    restores_compliance: bool
    basis: str


def kelly_fraction(win_rate: float, payoff_ratio: float) -> float | None:
    """Full Kelly fraction ``w - (1 - w) / b``.

    ``w`` is the win rate, ``b`` the payoff ratio (average win / average loss).
    Returns ``None`` for inputs outside their domain; a negative edge yields a
    negative fraction, which the caller floors at zero.
    """
    if not 0.0 <= win_rate <= 1.0 or payoff_ratio <= 0.0:
        return None
    return win_rate - (1.0 - win_rate) / payoff_ratio


def kelly_usable(kelly: KellyInputs | None) -> bool:
    """Whether cap 5 may compute from this pair at all (D-4/D-6).

    Three states say no, and they are three different sentences on the card
    ((g-1) to (g-4)): no pair was ever entered, the pair has no anchor to be
    aged from, or it is past :data:`KELLY_STALE_AFTER_DAYS`. The predicate is
    public and shared so :func:`kelly_allowed_weight`,
    :func:`_check_kelly_fraction` and :func:`notional_caps` cannot disagree
    about which pairs are live -- a sizing suggestion derived from a pair the
    card reports as ``not_evaluable`` is the failure this prevents.
    """
    if kelly is None or kelly.age_days is None:
        return False
    return kelly.age_days < KELLY_STALE_AFTER_DAYS


def kelly_allowed_weight(budget: RiskBudget, ctx: PortfolioContext) -> float | None:
    """Position weight allowed by fractional Kelly, or ``None`` without inputs."""
    kelly = ctx.kelly
    if not kelly_usable(kelly) or kelly is None:  # narrow for the type checker
        return None
    full = kelly_fraction(kelly.win_rate, kelly.payoff_ratio)
    if full is None:  # pragma: no cover - the field validators already pin the domain
        return None
    fractional = max(full, 0.0) * budget.kelly_fraction_cap
    return min(fractional, budget.kelly_position_cap)


def atr_max_shares(budget: RiskBudget, ctx: PortfolioContext) -> float | None:
    """Largest share count whose stop-out loss stays inside the per-trade cap.

    Stop distance is ``atr_stop_multiple x ATR(14)`` converted to TWD; the
    acceptable loss is ``max_loss_per_trade x total equity``.
    """
    if ctx.total_equity_twd is None or not ctx.total_equity_twd > 0.0 or ctx.atr is None:
        return None
    stop_distance_twd = budget.atr_stop_multiple * ctx.atr * ctx.fx_to_twd
    if stop_distance_twd <= 0.0:
        return None
    return budget.max_loss_per_trade * ctx.total_equity_twd / stop_distance_twd


def format_percent(value: float) -> str:
    """A ratio as a percentage, in the one shape every disclosure prints it in.

    Public because :mod:`app.advice.book` states a share of total equity in its
    own notes: two definitions of "how a percentage looks" would drift, and the
    reader sees both strings on the same card.
    """
    return f"{value * 100:.2f}%"


def format_win_rate(value: float) -> str:
    """Cap 5's win rate, at a precision the sample behind it can support.

    Not :func:`format_percent`, and the difference is the point. The other caps
    print ratios of money, which are continuous; this one prints a **count
    ratio**. ``MIN_OOS_ROUND_TRIPS`` is 20, so the finest step an imported
    estimate can move in is 1/20 = 5 percentage points, and a hand-typed pair is
    an estimate the user rounded themselves. Two decimals of a percentage
    (``62.50%``) claims resolution to a hundredth of a point, roughly five
    hundred times finer than the measurement -- the false precision 分歧①
    required 5 struck at in the payoff ratio's ``:g``. One decimal is still
    generous and is kept only so the digit does not read as a rounded integer.
    """
    return f"{value * 100:.1f}%"


def format_payoff_ratio(value: float) -> str:
    """Cap 5's payoff ratio, fixed at two decimals.

    ``:g`` printed six significant digits of a quotient of two sample means
    (``1.83274``), which 分歧① required 5 named as false precision: at n=20 the
    third decimal is noise. Two decimals is the shape the ratio is read in and
    is the same fixed-width promise :func:`format_win_rate` makes -- fixed,
    because ``:g`` also switches to scientific notation on extreme inputs and
    silently drops trailing zeros, so the same quantity would appear in three
    different shapes on three different cards.
    """
    return f"{value:.2f}"


def _breaches(observed: float, threshold: float) -> bool:
    """True when ``observed`` has reached or passed ``threshold``."""
    return observed >= threshold - EPSILON


def _check_single_position_weight(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    threshold = budget.max_position_weight
    weight = ctx.position_weight()
    if weight is None:
        return ("not_evaluable", "缺少總資產或部位市值，無法計算單一標的佔比。", None, threshold)
    if _breaches(weight, threshold):
        return (
            "violated",
            f"{ctx.symbol} 佔總資產 {format_percent(weight)}，"
            f"已達或超過上限 {format_percent(threshold)}。",
            weight,
            threshold,
        )
    return (
        "passed",
        f"{ctx.symbol} 佔總資產 {format_percent(weight)}，低於上限 {format_percent(threshold)}。",
        weight,
        threshold,
    )


def _inferred_sector_gap(ctx: PortfolioContext) -> SectorGap:
    """The state to report when the caller supplied no ``sector_gap``.

    Every context the product builds carries the signal (``app.advice.book``
    sets it on all five states), so this is the fallback for a context assembled
    by hand -- the alert vocabulary's bare context, and tests. Only the two
    states this model can establish from its own fields are reachable: a book
    with nothing in this symbol, and a holding with no category. It never
    guesses ``unsupported_market`` (the market is not a field here), nor
    ``etf_instrument`` (the instrument type is not a field here either), nor
    ``mixed`` (that is a fact about several holdings), because any such guess
    would put a claim about the user's book into a sentence.
    """
    held = ctx.position_market_value_twd
    if (held is None or held <= 0.0) and not ctx.quantity:
        return "no_position"
    return "unfiled"


def _check_sector_weight(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    threshold = budget.max_sector_weight
    if ctx.sector is None or ctx.sector_market_value_twd is None:
        gap = ctx.sector_gap if ctx.sector_gap is not None else _inferred_sector_gap(ctx)
        return (
            "not_evaluable",
            NO_SECTOR_DETAILS[gap],
            None,
            threshold,
        )
    if ctx.total_equity_twd is None or not ctx.total_equity_twd > 0.0:
        return ("not_evaluable", "缺少總資產，無法計算產業佔比。", None, threshold)
    weight = ctx.sector_market_value_twd / ctx.total_equity_twd
    if _breaches(weight, threshold):
        return (
            "violated",
            f"{ctx.sector} 產業佔總資產 {format_percent(weight)}，"
            f"已達或超過上限 {format_percent(threshold)}。",
            weight,
            threshold,
        )
    return (
        "passed",
        f"{ctx.sector} 產業佔總資產 {format_percent(weight)}，"
        f"低於上限 {format_percent(threshold)}。",
        weight,
        threshold,
    )


def _net_worth_disclosure(net_worth: SelfReportedNetWorth) -> str:
    """The three sentences every computed gross-exposure verdict must carry.

    Plus the ageing notice once the report passes
    :data:`NET_WORTH_SOFT_NOTICE_DAYS`, which is the warning half of FR-9 (b):
    the cap still answers, and says how close it is to no longer answering.
    """
    parts = [
        GROSS_EXPOSURE_MIXED_SOURCE_NOTE,
        GROSS_EXPOSURE_COVERAGE_NOTE,
        GROSS_EXPOSURE_REPORTED_AT_NOTE.format(
            reported_at=format_reported_at(net_worth.reported_at)
        ),
    ]
    if net_worth.age_days >= NET_WORTH_SOFT_NOTICE_DAYS:
        parts.append(
            NET_WORTH_AGEING_NOTE.format(
                age_days=net_worth.age_days, days=NET_WORTH_STALE_AFTER_DAYS
            )
        )
    return "".join(parts)


def _check_gross_exposure(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    """Cap 3: the valued book against the net worth the user reported.

    The order of the guards is the order of the questions a reader would ask --
    is there a net worth at all, is it recent enough to mean anything, is the
    numerator complete -- and each one that fails says which input is missing
    instead of falling through to a number. ``total_equity_twd`` is deliberately
    absent from this function: FR-9 option B keeps the valued book out of cap
    3's denominator, and cap 3 out of caps 1 and 4.
    """
    threshold = budget.max_gross_exposure
    net_worth = ctx.net_worth
    if net_worth is None:
        return ("not_evaluable", NO_NET_WORTH_DETAIL, None, threshold)
    if net_worth.age_days >= NET_WORTH_STALE_AFTER_DAYS:
        return (
            "not_evaluable",
            NET_WORTH_EXPIRED_DETAIL.format(
                days=NET_WORTH_STALE_AFTER_DAYS,
                reported_at=format_reported_at(net_worth.reported_at),
                age_days=net_worth.age_days,
            ),
            None,
            threshold,
        )
    if ctx.gross_exposure_twd is None:
        return ("not_evaluable", "缺少組合總市值，無法計算總曝險。", None, threshold)
    if ctx.book_fully_valued is not True:
        return (
            "not_evaluable",
            GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL + _net_worth_disclosure(net_worth),
            None,
            threshold,
        )
    exposure = ctx.gross_exposure_twd / net_worth.amount_twd
    disclosure = _net_worth_disclosure(net_worth)
    if _breaches(exposure, threshold):
        return (
            "violated",
            f"組合總曝險 {format_percent(exposure)}（已估值部位市值合計 ÷ 自報帳戶總淨值），"
            f"已達或超過上限 {format_percent(threshold)}。{disclosure}",
            exposure,
            threshold,
        )
    return (
        "passed",
        f"組合總曝險 {format_percent(exposure)}（已估值部位市值合計 ÷ 自報帳戶總淨值），"
        f"低於上限 {format_percent(threshold)}。{disclosure}",
        exposure,
        threshold,
    )


def _check_per_trade_loss(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    threshold = budget.max_loss_per_trade
    if ctx.atr is None:
        return ("not_evaluable", "缺少 ATR(14)，無法推導停損距離與部位上限。", None, threshold)
    if ctx.total_equity_twd is None or not ctx.total_equity_twd > 0.0:
        return ("not_evaluable", "缺少總資產，無法換算單筆可承受虧損。", None, threshold)
    shares = ctx.held_shares()
    if shares is None:
        return ("not_evaluable", "缺少持股數或部位市值，無法估算停損時的損失。", None, threshold)
    stop_distance_twd = budget.atr_stop_multiple * ctx.atr * ctx.fx_to_twd
    if stop_distance_twd <= 0.0:
        return ("not_evaluable", "ATR(14) 為 0，停損距離無法定義。", None, threshold)
    loss_ratio = shares * stop_distance_twd / ctx.total_equity_twd
    basis = f"以 {budget.atr_stop_multiple:g}×ATR(14) 為停損距離"
    if _breaches(loss_ratio, threshold):
        return (
            "violated",
            f"{basis}，觸及停損時的損失約佔總資產 {format_percent(loss_ratio)}，"
            f"已達或超過上限 {format_percent(threshold)}。",
            loss_ratio,
            threshold,
        )
    return (
        "passed",
        f"{basis}，觸及停損時的損失約佔總資產 {format_percent(loss_ratio)}，"
        f"低於上限 {format_percent(threshold)}。",
        loss_ratio,
        threshold,
    )


#: The (g) branch table (條件 51), keyed on ``(source, anchor state)`` -- the two
#: facts that decide which sentence is true, and the only two. Mutually
#: exclusive and exhaustive over the six cells; a wrong cell is a false statement
#: about where the user's number came from, which the review classes as BLOCKING
#: rather than cosmetic.
#:
#: ``None`` for the source is the "no row at all" cell, where there is nothing to
#: describe the origin of. The expired cells all interpolate their anchor; the
#: unanchorable ones cannot and do not (6-B).
_KELLY_EXPIRED_DETAILS: dict[KellyInputSource, str] = {
    "manual": KELLY_NOT_EVALUABLE_MANUAL_EXPIRED,
    "backtest": KELLY_NOT_EVALUABLE_BACKTEST_EXPIRED,
    "backtest_overridden": KELLY_NOT_EVALUABLE_OVERRIDDEN_EXPIRED,
}

#: The unanchorable half of the table, closed by the eighth round (條件 66).
#: ``backtest_overridden`` has its own sentence now: the cell is as reachable as
#: ``backtest``'s -- :meth:`KellyInputRecord.overriding` copies the provenance
#: column by column, so a row that had no anchor still has none after a hand
#: edit -- and (g-4)'s source parenthesis understated it by omitting that the
#: effective numbers are the user's own.
#:
#: ``manual`` is deliberately absent rather than mapped to a fallback: a
#: hand-typed pair always carries the server's write stamp, so
#: :func:`app.kelly.models.anchor_moment` never returns ``None`` for one and
#: this cell is unreachable. If it ever becomes reachable, the lookup below
#: raises instead of borrowing a sentence that would name the wrong source --
#: 第八輪 E2: a silent fallback here is a false statement about where a number
#: came from, and there is no approved sentence for the state.
_KELLY_UNANCHORED_DETAILS: dict[KellyInputSource, str] = {
    "backtest": KELLY_NOT_EVALUABLE_NO_OOS_END_DATE,
    "backtest_overridden": KELLY_NOT_EVALUABLE_OVERRIDDEN_NO_OOS_END_DATE,
}


def _kelly_not_evaluable_detail(kelly: KellyInputs | None) -> str:
    """Which cell of the (g) table this unusable pair falls in (條件 51).

    The sentences are one per *cause*, and the causes are genuinely different
    things to tell someone: nothing was ever entered, a typed pair went stale,
    an imported pair went stale, an imported pair the user then edited went
    stale, or an imported pair cannot be aged at all. Each is risk-approved
    verbatim and imported whole; nothing here composes or edits one, and the
    only values interpolated are the ones the approval names.

    The anchor half of the key mirrors :func:`app.kelly.models.anchor_moment`
    exactly -- ``manual`` ages from the write stamp, every other source from the
    end of the out-of-sample segment -- because these sentences *describe* the
    anchor ("上次更新於" vs "樣本外區段結束於") and would misstate it if the two
    rules diverged.
    """
    if kelly is None:
        return KELLY_NOT_EVALUABLE_NO_INPUT
    if kelly.age_days is None or kelly.anchored_at is None:
        detail = _KELLY_UNANCHORED_DETAILS.get(kelly.source)
        if detail is None:
            # 第八輪 E2. Only ``manual`` can land here, and only if the anchor
            # rule changed underneath this table. Failing is the conservative
            # branch: every sentence that exists names a source this row does
            # not have, and reporting one of them would misstate the origin of
            # the user's own number -- the failure the (g) table exists to make
            # impossible (條件 51).
            raise ValueError(
                f"Kelly 輸入來源 {kelly.source!r} 缺少錨點時無對應的定稿說明句，"
                "本狀態未經風控核可，不得以其他來源的句子替代"
            )
        return detail
    return _KELLY_EXPIRED_DETAILS[kelly.source].format(
        anchored_on=kelly.anchored_at,
        age_days=kelly.age_days,
        # 落地條件 9: the window is interpolated from the constant in force,
        # never written out, so moving it cannot leave the sentence behind.
        days=KELLY_STALE_AFTER_DAYS,
    )


def _kelly_disclosures(kelly: KellyInputs) -> str:
    """The sentences that must travel with a *shown* win rate, in order.

    Two attachments, both mandatory when their condition holds:

    * (e) or (e-manual), by source. 落地條件 18 makes them mutually exclusive and
      exhaustive: a sampled frequency and a number the user typed are different
      claims, and (e)'s opening clause is simply false of the second. The branch
      reads :attr:`KellyInputs.source` and nothing else -- the source is fed in
      with the pair, and deriving it from anything else here would be a second
      channel that could disagree with the stored row.
    * (a-2), when the f* interval covers "no edge". 約束 36 allows this module a
      boolean branch and no more, which is exactly what this is.

    Order is (e)/(e-manual) first: it qualifies the win rate printed immediately
    before it, and (a-2) then qualifies the estimate as a whole.
    """
    parts = [
        KELLY_WIN_RATE_IS_NOT_PROBABILITY
        if kelly.source == "backtest"
        else KELLY_MANUAL_WIN_RATE_IS_NOT_PROBABILITY
    ]
    if kelly.ci_includes_no_edge:
        parts.append(KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE)
    return "".join(parts)


def _check_kelly_fraction(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    kelly = ctx.kelly
    if not kelly_usable(kelly) or kelly is None:  # narrow for the type checker
        # Expiry is decided here rather than upstream (D-6), beside the sentence
        # that reports it, exactly as NET_WORTH_EXPIRED_DETAIL is.
        return ("not_evaluable", _kelly_not_evaluable_detail(kelly), None, None)
    allowed = kelly_allowed_weight(budget, ctx)
    if allowed is None:  # pragma: no cover - kelly_usable already established it
        return ("not_evaluable", _kelly_not_evaluable_detail(kelly), None, None)
    weight = ctx.position_weight()
    if allowed <= 0.0:
        # D-5: a non-positive edge is ``violated`` with a sentence of its own.
        # It is decided before the weight is needed, because the finding does
        # not depend on one -- the allowance is 0 whatever the holding is -- and
        # because the general phrasing ("目前佔比 X 已達或超過該上限") reads as a
        # demand to sell down to 0 when the cap is 0. The reported observed value
        # is still the weight, so the card has the same two numbers as elsewhere.
        #
        # 條件 41: this sentence first, then (a-2) if the interval is flagged.
        # (e)/(e-manual) are *not* attached: they qualify a win rate that was
        # printed, and this branch prints none (落地條件 11's condition).
        detail = KELLY_NON_POSITIVE_FRACTION_DETAIL
        if kelly.ci_includes_no_edge:
            detail += KELLY_F_STAR_INTERVAL_FLAG_DISCLOSURE
        return ("violated", detail, weight, allowed)
    if weight is None:
        return ("not_evaluable", "缺少總資產或部位市值，無法比較 Kelly 部位上限。", None, allowed)
    detail_head = (
        f"以勝率 {format_win_rate(kelly.win_rate)}、"
        f"盈虧比 {format_payoff_ratio(kelly.payoff_ratio)} 計算，"
        f"{budget.kelly_fraction_cap:g} 分數 Kelly 與 {format_percent(budget.kelly_position_cap)} "
        f"硬上限取小後為 {format_percent(allowed)}"
    )
    # A single string, assembled once: the verdict clause belongs to the numbers
    # in front of it, and the disclosures belong to the win rate just printed.
    disclosures = _kelly_disclosures(kelly)
    if _breaches(weight, allowed):
        return (
            "violated",
            f"{detail_head}，目前佔比 {format_percent(weight)} 已達或超過該上限。{disclosures}",
            weight,
            allowed,
        )
    return (
        "passed",
        f"{detail_head}，目前佔比 {format_percent(weight)} 低於該上限。{disclosures}",
        weight,
        allowed,
    )


_CHECKS: dict[str, Callable[[RiskBudget, PortfolioContext], CheckResult]] = {
    "single_position_weight": _check_single_position_weight,
    "sector_weight": _check_sector_weight,
    "gross_exposure": _check_gross_exposure,
    "per_trade_loss": _check_per_trade_loss,
    "kelly_fraction": _check_kelly_fraction,
}


def evaluate_limits(budget: RiskBudget, ctx: PortfolioContext) -> list[LimitCheck]:
    """Run every cap in :data:`LIMIT_IDS` order, numbered from 1."""
    checks: list[LimitCheck] = []
    for index, limit_id in enumerate(LIMIT_IDS, start=1):
        status, detail, observed, threshold = _CHECKS[limit_id](budget, ctx)
        checks.append(
            LimitCheck(
                index=index,
                id=limit_id,
                name=LIMIT_NAMES[limit_id],
                status=status,
                detail=detail,
                observed=observed,
                threshold=threshold,
            )
        )
    return checks


def _kelly_allowance_is_zero(budget: RiskBudget, ctx: PortfolioContext) -> bool:
    """Whether cap 5 has a usable pair whose allowance works out to zero.

    The single expression of D-5's condition, so :func:`notional_caps` (which
    drops the cap) and :func:`suggest_quantity_range` (which has to say that it
    did, and must not describe it as missing data) cannot disagree about which
    state they are in. ``False`` for a pair the cap will not use at all: that is
    the "no usable data" case the standing skipped sentence already covers.
    """
    allowed = kelly_allowed_weight(budget, ctx)
    return allowed is not None and allowed <= 0.0


def notional_caps(budget: RiskBudget, ctx: PortfolioContext) -> dict[str, float]:
    """Per-cap TWD ceilings on *this symbol's* market value.

    Only the caps whose inputs are present appear in the result; the caller
    takes the minimum of what is there and reports what was left out.
    """
    caps: dict[str, float] = {}
    equity = ctx.total_equity_twd
    if equity is None or not equity > 0.0:
        return caps
    current = ctx.position_market_value_twd

    caps["single_position_weight"] = budget.max_position_weight * equity

    if ctx.sector is not None and ctx.sector_market_value_twd is not None and current is not None:
        others = max(ctx.sector_market_value_twd - current, 0.0)
        caps["sector_weight"] = max(budget.max_sector_weight * equity - others, 0.0)

    # Cap 3's headroom is measured against the *net worth*, never against
    # ``equity``. The gate is :func:`_check_gross_exposure` itself rather than a
    # copy of its conditions, so a sizing suggestion can never be derived from a
    # cap the card reports as ``not_evaluable``.
    if ctx.net_worth is not None and ctx.gross_exposure_twd is not None and current is not None:
        if _check_gross_exposure(budget, ctx)[0] != "not_evaluable":
            others = max(ctx.gross_exposure_twd - current, 0.0)
            caps["gross_exposure"] = max(
                budget.max_gross_exposure * ctx.net_worth.amount_twd - others, 0.0
            )

    max_shares = atr_max_shares(budget, ctx)
    price = ctx.price_twd()
    if max_shares is not None and price is not None:
        caps["per_trade_loss"] = max_shares * price

    # D-5's exclusion rule. ``allowed`` is already ``None`` for a pair cap 5
    # will not use (absent, unanchorable or expired), which keeps a sizing
    # suggestion from being derived from a cap the card reports as
    # ``not_evaluable`` -- the same guarantee the gross-exposure entry above
    # gets from calling its own check. The extra condition is the non-positive
    # edge: ``allowed`` is then exactly ``0``, and a zero binding cap would be
    # turned into a share count by :func:`suggest_quantity_range` -- i.e. into a
    # "sell the entire holding" quantity, which is trading advice derived from
    # an estimate that says nothing more than "no edge was measured". Cap 5
    # still reports ``violated`` in that state; it just does not size anything.
    allowed = kelly_allowed_weight(budget, ctx)
    if allowed is not None and allowed > 0.0:
        caps["kelly_fraction"] = allowed * equity

    return caps


def project_position(ctx: PortfolioContext, *, share_delta: float) -> PortfolioContext:
    """The same book after buying (``+``) or selling (``-``) ``share_delta`` shares.

    Used to *verify* a suggested quantity against the caps instead of trusting
    the arithmetic that produced it. Only the amounts a trade in this symbol
    actually moves are adjusted: the position, the gross exposure and the
    symbol's sector bucket. Equity is untouched -- a trade at market price
    swaps cash for shares and does not change the book's value -- and so is the
    self-reported net worth, for exactly the same reason.
    """
    price = ctx.price_twd()
    if price is None:  # pragma: no cover - callers check the price first
        return ctx
    delta_value = share_delta * price
    updates: dict[str, float] = {
        "position_market_value_twd": max((ctx.position_market_value_twd or 0.0) + delta_value, 0.0)
    }
    held = ctx.held_shares()
    if held is not None:
        updates["quantity"] = max(held + share_delta, 0.0)
    if ctx.gross_exposure_twd is not None:
        updates["gross_exposure_twd"] = max(ctx.gross_exposure_twd + delta_value, 0.0)
    if ctx.sector_market_value_twd is not None:
        updates["sector_market_value_twd"] = max(ctx.sector_market_value_twd + delta_value, 0.0)
    return ctx.model_copy(update=updates)


def limit_status_after(
    budget: RiskBudget, ctx: PortfolioContext, *, limit_id: str, share_delta: float
) -> LimitStatus:
    """Status of one cap after a hypothetical trade of ``share_delta`` shares."""
    status, _, _, _ = _CHECKS[limit_id](budget, project_position(ctx, share_delta=share_delta))
    return status


def suggest_quantity_range(
    budget: RiskBudget, ctx: PortfolioContext, *, action: str
) -> QuantityRange | None:
    """Share range implied by the binding cap, or ``None`` when undefined.

    * ``add`` -- how many more shares fit under the tightest cap. ``None`` when
      there is no headroom.
    * ``reduce`` / ``stop_loss`` / ``take_profit`` -- how many shares must go to
      get back under the tightest cap, never more than the whole holding. When
      even selling the lot leaves the cap breached (the cap is driven by other
      positions), the range still stops at the holding but
      ``restores_compliance`` is ``False`` and ``basis`` says so instead of
      promising a return to compliance. ``None`` when nothing is above a cap
      (trimming a compliant position is not something the risk budget can
      size), when the holding is **less than one whole share** (any integer
      suggestion would exceed it), or when no quantity could be verified within
      the step bound.
    * anything else -- ``None``.

    Every returned edge is **verified against the cap it came from**, and a cap
    counts as breached at equality (see :func:`_breaches`), so a quantity
    landing exactly on the threshold would be flagged ``violated`` the moment it
    was acted on. The arithmetic edge is therefore re-checked through
    :func:`limit_status_after` and walked one share at a time until the
    resulting position sits strictly inside the cap. Verification demands an
    explicit ``passed``: ``not_evaluable`` is never taken for a pass.

    The rule behind every ``None`` above is the same one: **no suggestion beats
    a suggestion that cannot be stated truthfully.** No returned quantity is
    ever larger than the holding, and no ``basis`` claims an outcome the trade
    does not produce.
    """
    price = ctx.price_twd()
    if price is None or price <= 0.0:
        return None
    caps = notional_caps(budget, ctx)
    if not caps:
        return None
    binding_id, binding_value = min(caps.items(), key=lambda item: item[1])
    # 條件 35: cap 5 dropped out for a non-positive edge is **not** a cap that
    # lacked usable data, and the standing sentence below says exactly that. It
    # had its pair, computed with it, and arrived at a definite zero. So it is
    # excluded from ``skipped`` on that branch only -- an absent, unanchorable or
    # expired pair still belongs there -- and the (任務 2) sentence carries it
    # instead. Neither the standing sentence nor the two ``basis`` texts change
    # by a character.
    zero_allowance = _kelly_allowance_is_zero(budget, ctx)
    skipped = [
        LIMIT_NAMES[i]
        for i in LIMIT_IDS
        if i not in caps and not (i == "kelly_fraction" and zero_allowance)
    ]
    # A whole sentence appended after the basis's final full stop, never a
    # trailing clause: a cap left out of the arithmetic is not a cap that
    # passed, and the reader has to be told that in its own sentence rather
    # than in a footnote glued to the end of another one. "缺少可用資料" and not
    # "資料不足" because a cap can also drop out on inputs that exist but have
    # gone stale (cap 3's net-worth path).
    #
    # 風控核可文案,修改須重新送審(2026-08-09)
    skipped_note = (
        f"以下上限本次缺少可用資料,未參與這個區間的計算:{'、'.join(skipped)}。"
        f"未參與計算不等於已通過,這個區間沒有檢查過這幾條。"
        if skipped
        else ""
    )
    # 條件 37: a whole sentence at the very end of the basis, after the skipped
    # note, never a clause spliced into either. 條件 36 makes it mandatory
    # wherever it is reachable -- in practice the sell-direction range, since the
    # advice engine refuses an ``add`` while any cap is violated and cap 5 is
    # violated on this branch -- so it is attached in every direction rather than
    # conditioned on one, which would leave it silently absent if that changed.
    zero_allowance_note = KELLY_ZERO_ALLOWANCE_RANGE_NOTE if zero_allowance else ""
    trailing_note = f"{skipped_note}{zero_allowance_note}"
    current = ctx.position_market_value_twd or 0.0

    if action == "add":
        upper = _largest_compliant_buy(
            budget, ctx, binding_id=binding_id, start=math.floor((binding_value - current) / price)
        )
        if upper is None:
            return None
        lower = max(1, math.floor(upper * RANGE_LOWER_RATIO))
        return QuantityRange(
            min_shares=lower,
            max_shares=upper,
            restores_compliance=True,
            # The lower edge is explained as a range-making device, not as a
            # floor: "最少要買" is the reading this sentence exists to close.
            #
            # 風控核可文案,修改須重新送審(2026-08-09)
            basis=(
                f"規則評估:{RANGE_ACTION_LABELS['add']},"
                f"區間為再買進 {lower:,} ~ {upper:,} 股。"
                f"目前有納入計算的上限中,額度最緊的是「{LIMIT_NAMES[binding_id]}」;"
                f"以它換算,買進後這條上限仍為通過的最大股數是 {upper:,} 股,也就是區間上緣。"
                f"下緣 {lower:,} 股取上緣的一半,用意是給出一個範圍而不是單一數字,"
                f"不是「最少要買」的數量。{trailing_note}"
            ),
        )

    if action in {"reduce", "stop_loss", "take_profit"}:
        if current - binding_value <= 0.0:
            return None
        held = ctx.held_shares()
        sellable = math.floor(held) if held is not None else None
        if sellable is None or sellable < 1:
            # Fewer than one whole share (quantity is a Decimal, so 0.5 shares
            # is a legal holding). Every integer suggestion would be larger than
            # what the user owns, and rounding up to 1 while calling it "持股全數"
            # is exactly the false claim this branch exists to prevent. No
            # quantity, no claim.
            return None
        result = _smallest_compliant_sell(
            budget,
            ctx,
            binding_id=binding_id,
            start=max(1, math.ceil((current - binding_value) / price)),
            sellable=sellable,
        )
        if result is None:
            # Could not verify any quantity within the step bound -- same
            # outcome as the buy side: no suggestion rather than an unverified
            # one. See :func:`_smallest_compliant_sell`.
            return None
        lower, compliant = result
        upper = max(lower, sellable)
        limit_name = LIMIT_NAMES[binding_id]
        # The two branches are the whole point of returning ``compliant``:
        # claiming a return to compliance when the cap is driven by other
        # positions would be a false statement about what the trade achieves.
        # Both branches are only reachable with a verified quantity that is at
        # most the holding, so both sentences are true where they are used.
        # They are two separate sentences by design -- the compliant one has to
        # say what the upper edge is *not* (a quantity the cap demands), the
        # other one has to say the sale does not clear the cap at all.
        #
        # 風控核可文案,修改須重新送審(2026-08-09)
        basis = (
            (
                f"規則評估:{RANGE_ACTION_LABELS[action]},"
                f"區間為賣出 {lower:,} ~ {upper:,} 股。"
                f"目前部位已超出「{limit_name}」這條上限,"
                f"賣出 {lower:,} 股後可回到這條上限的範圍內;"
                f"區間上緣 {upper:,} 股是目前持股全數,是這個區間的上界,"
                f"不是這條上限要求賣到的數量。{trailing_note}"
            )
            if compliant
            else (
                f"規則評估:{RANGE_ACTION_LABELS[action]},"
                f"這個區間只有一個數字:{lower:,} 股,也就是目前持股全數。"
                f"目前部位已超出「{limit_name}」這條上限,"
                f"但這條上限主要由其他部位造成,把這一檔全部賣出後仍然超標。{trailing_note}"
            )
        )
        return QuantityRange(
            min_shares=lower,
            max_shares=upper,
            restores_compliance=compliant,
            basis=basis,
        )

    return None


def _passes(
    budget: RiskBudget, ctx: PortfolioContext, *, binding_id: str, share_delta: float
) -> bool:
    """Whether the binding cap explicitly **passes** after a hypothetical trade.

    ``passed`` only -- ``not_evaluable`` is not treated as a pass. A cap whose
    inputs went missing tells us nothing about whether the trade is inside the
    budget, and sizing a suggestion off "we could not check" would put the
    engine's name to a quantity it never verified.
    """
    return (
        limit_status_after(budget, ctx, limit_id=binding_id, share_delta=share_delta) == "passed"
    )


def _largest_compliant_buy(
    budget: RiskBudget, ctx: PortfolioContext, *, binding_id: str, start: int
) -> int | None:
    """Largest buy at or below ``start`` that leaves the binding cap passing.

    Falls through to ``None`` ("no suggestion") only if the loop bound is
    exhausted. That cannot happen with the shipped budget -- the arithmetic
    edge from :func:`notional_caps` is already within one share of the answer,
    so at most one step back is ever needed -- and the bound is a safety valve
    against an inconsistent budget rather than a live code path. The fall-through
    is pinned by a white-box test that shrinks
    :data:`MAX_SIZING_ADJUSTMENTS` to zero.
    """
    shares = start
    for _ in range(MAX_SIZING_ADJUSTMENTS):
        if shares < 1:
            return None
        if _passes(budget, ctx, binding_id=binding_id, share_delta=float(shares)):
            return shares
        shares -= 1
    return None


def _smallest_compliant_sell(
    budget: RiskBudget, ctx: PortfolioContext, *, binding_id: str, start: int, sellable: int
) -> tuple[int, bool] | None:
    """Smallest sale from ``start`` up that leaves the binding cap passing.

    ``sellable`` is the whole holding rounded down to shares, and is at least 1
    (the caller rejects a smaller holding outright). Returns
    ``(shares, restores_compliance)`` where ``shares <= sellable`` always: a
    quantity larger than the holding is never produced.

    ``restores_compliance`` is ``False`` when even selling the lot leaves the
    cap breached -- something other than this position is driving it. The
    honest answer is then still "sell the lot", never a quantity the user does
    not own, and the caller says the sale does *not* bring the cap back inside
    its limit instead of implying it does.

    Returns ``None`` when the step bound is exhausted without verifying any
    quantity. That is unreachable with a consistent budget (the arithmetic edge
    is within one share of the answer), and it deliberately mirrors
    :func:`_largest_compliant_buy`: an unverified quantity is not offered, and
    in particular the "已為持股全數／由其他部位驅動" wording is not reused here,
    because neither of those facts is established on this path.
    """
    shares = start
    for _ in range(MAX_SIZING_ADJUSTMENTS):
        if shares >= sellable:
            return sellable, _passes(
                budget, ctx, binding_id=binding_id, share_delta=-float(sellable)
            )
        if _passes(budget, ctx, binding_id=binding_id, share_delta=-float(shares)):
            return shares, True
        shares += 1
    return None
