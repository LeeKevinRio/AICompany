"""The risk budget and the caps every recommendation is measured against.

:class:`RiskBudget` holds the numbers (conservative defaults, meant to be
editable later from a settings page -- hence a plain pydantic model that
round-trips to JSON rather than an env-only settings object).
:class:`PortfolioContext` holds everything about *this* symbol and the book
around it that a cap needs.

Two conventions that make the output honest rather than merely reassuring:

* A cap whose inputs are missing reports ``not_evaluable`` with the reason. It
  is never silently reported as ``passed``. The sector cap is ``not_evaluable``
  in practice today because positions carry no sector field yet.
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
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    "淨值輸入已超過 {days} 天未更新（最後輸入時間 {reported_at}，距今 {age_days} 天），"
    "這條上限不以過期的淨值計算；請至設定頁更新帳戶總淨值後再評估。"
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
    #: Sector label. Positions have no sector field yet, so this is normally
    #: ``None`` and the sector cap honestly reports ``not_evaluable``.
    sector: str | None = None
    sector_market_value_twd: float | None = Field(default=None, ge=0.0)
    #: Kelly inputs. No source produces them yet; absent -> ``not_evaluable``.
    win_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    payoff_ratio: float | None = Field(default=None, gt=0.0)

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


def kelly_allowed_weight(budget: RiskBudget, ctx: PortfolioContext) -> float | None:
    """Position weight allowed by fractional Kelly, or ``None`` without inputs."""
    if ctx.win_rate is None or ctx.payoff_ratio is None:
        return None
    full = kelly_fraction(ctx.win_rate, ctx.payoff_ratio)
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


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


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
            f"{ctx.symbol} 佔總資產 {_pct(weight)}，已達或超過上限 {_pct(threshold)}。",
            weight,
            threshold,
        )
    return (
        "passed",
        f"{ctx.symbol} 佔總資產 {_pct(weight)}，低於上限 {_pct(threshold)}。",
        weight,
        threshold,
    )


def _check_sector_weight(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    threshold = budget.max_sector_weight
    if ctx.sector is None or ctx.sector_market_value_twd is None:
        return (
            "not_evaluable",
            "持倉資料目前沒有產業別欄位，這條上限未實際檢查。",
            None,
            threshold,
        )
    if ctx.total_equity_twd is None or not ctx.total_equity_twd > 0.0:
        return ("not_evaluable", "缺少總資產，無法計算產業佔比。", None, threshold)
    weight = ctx.sector_market_value_twd / ctx.total_equity_twd
    if _breaches(weight, threshold):
        return (
            "violated",
            f"{ctx.sector} 產業佔總資產 {_pct(weight)}，已達或超過上限 {_pct(threshold)}。",
            weight,
            threshold,
        )
    return (
        "passed",
        f"{ctx.sector} 產業佔總資產 {_pct(weight)}，低於上限 {_pct(threshold)}。",
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
        GROSS_EXPOSURE_REPORTED_AT_NOTE.format(reported_at=net_worth.reported_at),
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
                reported_at=net_worth.reported_at,
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
            f"組合總曝險 {_pct(exposure)}（已估值部位市值合計 ÷ 自報帳戶總淨值），"
            f"已達或超過上限 {_pct(threshold)}。{disclosure}",
            exposure,
            threshold,
        )
    return (
        "passed",
        f"組合總曝險 {_pct(exposure)}（已估值部位市值合計 ÷ 自報帳戶總淨值），"
        f"低於上限 {_pct(threshold)}。{disclosure}",
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
            f"{basis}，觸及停損時的損失約佔總資產 {_pct(loss_ratio)}，"
            f"已達或超過上限 {_pct(threshold)}。",
            loss_ratio,
            threshold,
        )
    return (
        "passed",
        f"{basis}，觸及停損時的損失約佔總資產 {_pct(loss_ratio)}，低於上限 {_pct(threshold)}。",
        loss_ratio,
        threshold,
    )


def _check_kelly_fraction(budget: RiskBudget, ctx: PortfolioContext) -> CheckResult:
    allowed = kelly_allowed_weight(budget, ctx)
    if allowed is None or ctx.win_rate is None or ctx.payoff_ratio is None:
        return (
            "not_evaluable",
            "缺少勝率或盈虧比，無法計算 Kelly 部位上限（目前沒有資料來源提供這兩項輸入）。",
            None,
            None,
        )
    weight = ctx.position_weight()
    if weight is None:
        return ("not_evaluable", "缺少總資產或部位市值，無法比較 Kelly 部位上限。", None, allowed)
    detail_head = (
        f"以勝率 {_pct(ctx.win_rate)}、盈虧比 {ctx.payoff_ratio:g} 計算，"
        f"{budget.kelly_fraction_cap:g} 分數 Kelly 與 {_pct(budget.kelly_position_cap)} "
        f"硬上限取小後為 {_pct(allowed)}"
    )
    if _breaches(weight, allowed):
        return (
            "violated",
            f"{detail_head}，目前佔比 {_pct(weight)} 已達或超過該上限。",
            weight,
            allowed,
        )
    return ("passed", f"{detail_head}，目前佔比 {_pct(weight)} 低於該上限。", weight, allowed)


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

    allowed = kelly_allowed_weight(budget, ctx)
    if allowed is not None:
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
    skipped = [LIMIT_NAMES[i] for i in LIMIT_IDS if i not in caps]
    skipped_note = f"；未納入計算的上限：{'、'.join(skipped)}" if skipped else ""
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
            basis=(
                f"以「{LIMIT_NAMES[binding_id]}」為最小可用額度換算，"
                f"最多可再買進 {upper} 股（買進後該上限仍為通過），"
                f"區間下緣取上緣的一半{skipped_note}。"
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
        # claiming "減去 N 股可回到該上限之內" when the cap is driven by other
        # positions would be a false statement about what the trade achieves.
        # Both branches are only reachable with a verified quantity that is at
        # most the holding, so both sentences are true where they are used.
        basis = (
            f"目前部位超出「{limit_name}」，"
            f"減去 {lower} 股可回到該上限之內，上緣為目前持股全數{skipped_note}。"
            if compliant
            else (
                f"目前部位超出「{limit_name}」，"
                f"建議量 {lower} 股已為持股全數；該上限由其他部位驅動，"
                f"賣出後仍為違反{skipped_note}。"
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
