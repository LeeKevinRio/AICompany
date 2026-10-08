"""Build a :class:`PortfolioContext` from stored positions and their valuations.

This is the adapter between the *bookkeeping* layer (``app/positions`` +
``app/portfolio``, Decimal money, per-position valuations that may individually
be ``insufficient_data``) and the *risk-budget* layer (``app/advice/limits``,
float ratios). It exists so both the advice endpoint and the alert engine build
the same context from the same rules instead of each inventing its own.

Three honesty rules govern what is filled in:

1. **Only ``ok`` valuations are aggregated.** A position that could not be
   valued (no price, or no FX rate) contributes nothing to the book total and
   is listed in ``notes``, so a partial book is never presented as a whole one.
2. **Equity is the valued book, and says so.** There is no cash or account
   balance anywhere in this product, so ``total_equity_twd`` is the market
   value of the successfully valued positions. That is an assumption, and it is
   stated in ``notes`` rather than left for the reader to infer.
3. **Gross exposure needs a denominator the user supplied.** Nothing in this
   product knows the account's cash or margin balances, so the only figure that
   can sit under the exposure ratio is the net worth the user reports on the
   settings page (FR-9). Without one the cap stays ``not_evaluable`` exactly as
   it always was -- the equity figure is *not* substituted, because dividing
   the valued book by itself would force the ratio to 100% and turn an unknown
   into a permanent "violated". With one, the numerator is the valued book and
   the denominator is the reported net worth, and the two different origins are
   disclosed on the verdict itself (:mod:`app.advice.limits`).

   The valued book is used as the numerator **only when every position could be
   valued**: a short numerator makes exposure look lower than it is, and that is
   the single direction this cap must never err in, so an incomplete book yields
   ``not_evaluable`` instead (FR-9 (a-附加)).

4. **A sector total only counts what was actually classified.** ``sector`` is
   the category the user typed on the holding itself (FR-12); positions with no
   category are counted into no industry at all, and the fact that some were
   left out travels with the context in ``notes`` (AC-12.5). Nothing is
   inferred from a symbol, and an unclassified book is never presented as a
   diversified one. *Why* this symbol has no category -- nothing held, nothing
   filed, an ETF the taxonomy does not apply to, a market with no taxonomy, or
   two categories on one symbol -- travels with it in ``sector_gap``, because
   the five are different problems and only this layer can tell them apart
   (AC-12.3).

   Since ADR-0022 a category belongs to the *holding* (one symbol in one
   market), not to the lot: an unfiled lot beside a filed one counts in that
   industry, and a holding filed under several counts in each. The unvalued
   lots are classified the same way against the card's industry
   (:class:`app.advice.limits.UnvaluedComposition`), because a lot missing
   from the industry's numerator makes its share read *low* -- which is why
   the notes' "比率會因此偏高" is chosen per response by :func:`book_notes`
   rather than fixed.

5. **The Kelly pair is passed in, never fetched.** Since C5 there *is* a source
   for it (``kelly_inputs``, ADR-0006 D-2), but reading it here would put a
   database call inside the one purely-computational assembly point. The caller
   resolves the row and hands it to :func:`kelly_inputs_of`, which is where the
   clock is read and where an expired pair keeps its age instead of being
   flattened into an absence -- cap 5 has four different sentences for the ways
   an input can be unusable, and it can only choose between them if the
   difference survives this layer.

FX (ADR-0005 decision 5): this module stays a pure function and **never imports
an adapter**. The caller resolves the rate (``app/services/fx.py``) and passes a
:class:`FxQuote` in; letting this layer fetch would put I/O into the one
purely-computational risk assembly point and force every test to mock a
network. The red line is unchanged: no quote, no rate, or a quote for the wrong
pair all yield ``None`` -- the price is then withheld so the price-based caps
report ``not_evaluable``, and **no default rate is ever substituted for a
non-TWD currency**. The reason text distinguishes "no price" from "no FX
conversion", because they call for different things from the reader.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.advice.limits import (
    LIMIT_NAMES,
    NET_WORTH_STALE_AFTER_DAYS,
    SECTOR_MIXED_DETAIL,
    KellyInputs,
    PortfolioContext,
    SectorGap,
    SelfReportedNetWorth,
    UnknownSectorLots,
    UnvaluedComposition,
    format_percent,
    format_reported_at,
    sector_numerator_gaps,
    symbol_has_unvalued_lots,
)
from app.data.interface import DataStatus
from app.data.price_guard import usable_price
from app.kelly.models import KellyInputRow, ageing_of
from app.portfolio.summary import PortfolioSummary, SummaryPosition
from app.portfolio.valuation import CURRENCY_MARKET_MISMATCH, PRICE_NOT_QUERIED, FxInfo
from app.positions.models import InstrumentType, Market, currency_matches_market

logger = logging.getLogger(__name__)

#: The markets whose holdings may carry an industry category at all. TWSE's
#: taxonomy is TW-only by decision (AC-12.6, :mod:`app.positions.sectors`), and
#: a holding outside this set is not "missing a value" -- there is nothing it
#: could be filed under yet, which is why cap 2 says something different about
#: it (:data:`app.advice.limits.NO_SECTOR_UNSUPPORTED_MARKET_DETAIL`).
SECTOR_CLASSIFIED_MARKETS: frozenset[Market] = frozenset({"TW"})

#: The instrument types that are funds rather than individual companies. A TW
#: holding of one of these with no category is not "not filled in yet": TWSE's
#: industry taxonomy classifies listed companies, so an ETF has nothing true it
#: could be filed under, and cap 2 must say that instead of directing its owner
#: to fill the field (D6, :data:`app.advice.limits.NO_SECTOR_ETF_DETAIL`).
ETF_INSTRUMENT_TYPES: frozenset[InstrumentType] = frozenset({"etf", "leveraged_etf", "futures_etf"})

#: Stated on every context so the equity assumption travels with the numbers.
EQUITY_BASIS_NOTE = (
    "總資產以「已成功估值的部位市值合計」為代表，系統沒有現金與帳戶淨值資料，"
    "因此所有以總資產為分母的比率都建立在這個假設上。"
)

#: Stated whenever gross exposure is deliberately left out.
GROSS_EXPOSURE_NOTE = (
    "缺少現金與融資餘額資料，總曝險無法計算；該上限會回報 not_evaluable，"
    "不以總資產代入而讓比率恆為 100%。"
)

#: Stated instead, once the user has supplied a net worth for the cap to use.
#: It names both halves of the ratio and where each came from, because the two
#: numbers no longer share an origin.
GROSS_EXPOSURE_SELF_REPORTED_NOTE = (
    "總曝險以「已估值部位市值合計」為分子、使用者自報的帳戶總淨值"
    "新台幣 {amount:,.0f} 元為分母，輸入時間為 {reported_at}；"
    "此淨值由使用者自行輸入，系統未加以查核。"
)

#: And stated when the report is past its freshness rule. The present-tense
#: sentence above would otherwise sit next to a cap reporting ``not_evaluable``
#: for that very reason, describing a division this context does not perform.
GROSS_EXPOSURE_EXPIRED_NOTE = (
    "使用者自報的帳戶總淨值新台幣 {amount:,.0f} 元，輸入時間為 {reported_at}，"
    "已超過 {days} 天未更新，本次不以它為分母計算總曝險；"
    "該上限回報 not_evaluable，待使用者更新淨值後才會恢復計算。"
)

#: AC-12.5: the sector ratio was computed while some holdings sat outside every
#: industry bucket, so it is a floor rather than the whole picture -- and says so
#: instead of quietly reporting ``passed``. The count travels with the market
#: value and the share of equity it stands for, because a number of rows hides
#: the size of the hole: "3 筆" reads the same whether those rows are 1% or 40%
#: of the book. The last clause is the one
#: :data:`app.advice.limits.GROSS_EXPOSURE_INCOMPLETE_BOOK_DETAIL` already makes
#: about its own numerator -- a ``passed`` derived from an understated ratio is
#: still an understated ratio.
#:
#: Wording reviewed and approved by risk-compliance on 2026-08-09 (FR-12 句 2
#: 修正句), recorded in ``work/reviews/c1-phase8-review.md``; changing it needs a
#: fresh review.
SECTOR_UNCLASSIFIED_NOTE = (
    "組合中有 {count} 筆已估值持倉未填產業別，合計市值新台幣 {amount:,.0f} 元、"
    "佔總資產 {share}，未計入任何產業的市值合計；單一產業佔比可能被低估，"
    "這條上限的通過判定也可能建立在偏低的比率上。"
)

#: Rule 1 stated on the book as a whole: positions that could not be valued are
#: outside every total. Since ADR-0022 the sentence is "{cause}；{direction}":
#: the cause half (W4 here, W5 below) is the 2026-09-18 wording unchanged, and
#: the direction half is chosen per card / per overview, because "every ratio
#: reads high" is only true when no unvalued lot may belong to the industry
#: cap 2 measures. Constants rather than inline f-strings because the
#: book-level assembly (:func:`build_book_level_context`) states the same fact
#: about the same books.
#:
#: Live (W4) and cache-only (W5) cause halves: unchanged from 2026-09-18; the
#: fixed sentences were turned into this conditional form and re-approved by
#: risk-compliance on 2026-10-07. Under the ratios-read-high direction the
#: output is byte-identical to the 2026-09-18 sentences
#: (:data:`UNVALUED_POSITIONS_NOTE`, :data:`UNVALUED_POSITIONS_NOTE_CACHE_ONLY`).
#: 風控核可文案,修改須重新送審(2026-10-07;live／cache_only 條件式重新核可)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (W4, W5, 組合方式)
UNVALUED_POSITIONS_CAUSE = "組合中有 {count} 筆部位無法估值（缺價格或匯率），未計入總資產"
#: The same fact for the positions whose price was *not asked for this time*
#: (a cache-only book, ADR-0010 D-1; ``Valuation.missing`` carries
#: ``price_not_queried``) -- a different cause from "asked, nothing there",
#: which the sentence above keeps describing. The two groups are counted
#: separately (風控 A-5): a book may hold both.
#: Wording by creative-lead (`work/stock-desk-ADR-0010-揭露句-文案.md`), fixed
#: verbatim by risk-compliance-officer 2026-09-18 (三審); any change goes back
#: to them. 列管: if an FX cache layer ever makes a *rate* "not asked" too, the
#: parenthetical must be re-reviewed.
#: 風控核可文案,修改須重新送審(2026-10-07;live／cache_only 條件式重新核可)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (W5)
UNVALUED_POSITIONS_CAUSE_CACHE_ONLY = (
    "組合中有 {count} 筆部位無法估值（本次未向來源查詢，本機尚無可用的價格或匯率），未計入總資產"
)
#: The third cause group (task X-3c, KX-A9): rows the valuator refused because
#: their currency is not their market's (``Valuation.missing`` carries
#: :data:`app.portfolio.valuation.CURRENCY_MARKET_MISMATCH`). Nothing was asked
#: of any source for them, in either price mode, so the sentence is the same
#: live and cache-only (RX-4); it is never folded into W4/W5's "缺價格或匯率"
#: (KX-A10). Joined to the same direction clause as W4/W5, after them.
#: 風控核可文案,修改須重新送審(2026-10-08)
#: ``work/reviews/2026-10-08-X-3c-幣別與市場不符-揭露字面-風控審查.md`` (第二段 (b), 75 字版)
#: ``work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md`` (X-3c 第二段裁定)
CURRENCY_MARKET_MISMATCH_CAUSE = (
    "組合中有 {count} 筆部位因幣別與市場不符而無法估值（紀錄不一致，非價格或匯率中斷），"
    "可於庫存頁的「更多」視窗更正幣別與平均成本；系統不猜幣別而未計入總資產"
)
#: "{成因}；{方向子句}" -- the one way a cause and its direction become one note.
#: 風控核可文案,修改須重新送審(2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (組合方式)
UNVALUED_NOTE_TEMPLATE = "{cause}；{direction}"
#: D-a: every ratio built on the valued book reads high. True whenever no
#: unvalued lot is, or may be, in the industry cap 2 measures.
#: 風控核可文案,修改須重新送審(2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (D-a)
UNVALUED_DIRECTION_READS_HIGH = "比率會因此偏高。"
#: D-P: caps 1, 4 and 5 still read high, but cap 2's industry share may read
#: *low*, because an unvalued lot may be in that very industry. ``{target}`` is
#: :data:`UNVALUED_DIRECTION_TARGET_SYMBOL` on the card and
#: :data:`UNVALUED_DIRECTION_TARGET_BOOK` on the overview.
#: 風控核可文案,修改須重新送審(2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (D-P)
UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW = (
    "第 1、4、5 條上限的比率會因此偏高；第 2 條上限（單一產業佔比上限）則不一定偏高，"
    "因為部分無法估值的持倉可能屬於{target}，使該產業的佔比偏低。"
)
#: D-P's ``{target}`` on the card: the card's own industry, with the leading
#: half-width space the approval specifies.
#: 風控核可文案,修改須重新送審(2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (D-P target)
UNVALUED_DIRECTION_TARGET_SYMBOL = " {sector} 產業"
#: D-P's ``{target}`` on the overview (``/api/portfolio/limits``).
#: 風控核可文案,修改須重新送審(2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (D-P target)
UNVALUED_DIRECTION_TARGET_BOOK = "已納入比較的產業"

#: The caps whose ratio sits on this symbol's own position (caps 1, 4 and 5):
#: an unvalued lot of the symbol itself is missing from their numerator. Named
#: from :data:`app.advice.limits.LIMIT_NAMES`, never typed (risk-compliance required).
_OWN_POSITION_LIMIT_IDS: tuple[str, ...] = (
    "single_position_weight",
    "per_trade_loss",
    "kelly_fraction",
)
#: The joiner between those names inside D-d1 / D-d2's parenthesis.
_OWN_POSITION_NAME_SEPARATOR = "、"
_OWN_POSITION_LIMIT_NAMES = _OWN_POSITION_NAME_SEPARATOR.join(
    LIMIT_NAMES[limit_id] for limit_id in _OWN_POSITION_LIMIT_IDS
)

#: D-d1: this symbol's own lots are the only unvalued lots in the book. Caps
#: 1, 4 and 5 then read *low* -- a definite floor, cap 4 included, because
#: ``held_shares`` counts only the valued shares while the stop distance does
#: not depend on valuation (risk-compliance D-d1 correction, tech-architect's proof). Card only.
#: ``{names}`` is filled from :data:`LIMIT_NAMES` below.
#:
#: Deleted-clause version (ADR-0023 Decision 4, R-6): since 6-a none of caps
#: 1, 4 and 5 can report ``passed`` while the symbol has unvalued lots of its
#: own, so the former clause about a below-cap result had nothing left to
#: qualify and was removed. If those caps can ever pass again in this state
#: (ADR-0023 F-5), the wording goes back to review -- it is not restored from
#: version control.
#: 風控核可文案,修改須重新送審(2026-10-07;D-d1 第二次核可（更正）2026-10-07;刪除版核可 2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (D-d1 更正節)
#: ``work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md`` (D-d1 刪除版)
UNVALUED_DIRECTION_OWN_ONLY_TEMPLATE = (
    "因本標的自身的持倉無法估值，第 1、4、5 條上限（{names}）的比率會偏低。"
)
UNVALUED_DIRECTION_OWN_ONLY = UNVALUED_DIRECTION_OWN_ONLY_TEMPLATE.format(
    names=_OWN_POSITION_LIMIT_NAMES
)
#: D-d2: this symbol's own lots *and* other holdings' lots are unvalued. The
#: two push caps 1, 4 and 5 in opposite directions, so the direction is not
#: known. Card only. Deleted-clause version, for the same reason as D-d1 above
#: (ADR-0023 Decision 4, R-6).
#: 風控核可文案,修改須重新送審(2026-10-07;刪除版核可 2026-10-07)
#: ``work/reviews/2026-10-07-產業上限-同產業未估值-揭露字面-風控審查.md`` (D-d2)
#: ``work/reviews/2026-10-07-上限分子不完整-非對稱判定-揭露字面-風控審查.md`` (D-d2 刪除版)
UNVALUED_DIRECTION_OWN_AND_OTHERS_TEMPLATE = (
    "因本標的自身與其他標的的持倉皆無法估值，第 1、4、5 條上限（{names}）的比率方向不定，"
    "可能偏高也可能偏低。"
)
UNVALUED_DIRECTION_OWN_AND_OTHERS = UNVALUED_DIRECTION_OWN_AND_OTHERS_TEMPLATE.format(
    names=_OWN_POSITION_LIMIT_NAMES
)

#: The 2026-09-18 live sentence, kept as the cause joined to D-a -- what every
#: book whose unvalued lots cannot touch cap 2's industry still reads, byte for
#: byte (K-11). Fixed verbatim by risk-compliance-officer 2026-09-18 (三審).
UNVALUED_POSITIONS_NOTE = UNVALUED_NOTE_TEMPLATE.format(
    cause=UNVALUED_POSITIONS_CAUSE, direction=UNVALUED_DIRECTION_READS_HIGH
)
#: The 2026-09-18 cache-only sentence, likewise (K-11).
UNVALUED_POSITIONS_NOTE_CACHE_ONLY = UNVALUED_NOTE_TEMPLATE.format(
    cause=UNVALUED_POSITIONS_CAUSE_CACHE_ONLY, direction=UNVALUED_DIRECTION_READS_HIGH
)

#: The same fact about *one* symbol's own lots. Extracted for the same reason:
#: the book-level caps name this as the ground for leaving a symbol out of a
#: per-symbol comparison, and the two statements must not drift apart.
SYMBOL_UNVALUED_NOTE = "此標的有 {count} 筆持倉無法估值，未計入本標的的部位市值與成本。"

#: No quote at all reached this layer for a non-TWD holding.
NO_FX_QUOTE_NOTE = (
    "計價幣別為 {currency}，本次沒有取得任何匯率報價，"
    "價格與 ATR 相關的上限不計算；這是「無法取得匯率換算」，與「無法取得價格」不同，"
    "且不以 1.0 匯率代入。"
)

#: A quote arrived but carries no usable rate.
FX_UNAVAILABLE_NOTE = (
    "計價幣別為 {currency}，{pair} 匯率報價沒有可用數值"
    "（資料狀態 {status}、來源 {source}、匯率日期 {as_of}），"
    "價格與 ATR 相關的上限不計算；這是「無法取得匯率換算」，與「無法取得價格」不同，"
    "且不以 1.0 匯率代入。"
)

#: A quote arrived for a different pair than the holding needs.
FX_PAIR_MISMATCH_NOTE = (
    "計價幣別為 {currency}，需要的匯率是 {expected}，但取得的報價是 {pair}；"
    "不以不相符的匯率換算，價格與 ATR 相關的上限不計算。"
)

#: One symbol's lots are held in more than one currency, so no single rate
#: applies and the close and ATR are withheld together. Names the caps the way
#: the three FX notes above do ("價格與 ATR 相關的上限"): the caps that read the
#: price or the ATR (:data:`app.advice.limits.PRICE_INPUT_LIMIT_IDS`), not cap 1,
#: which reads the valuator's market value and is still computed.
#: 風控核可文案,修改須重新送審(2026-10-07;
#: PR-0 ruling: minimal substitution reusing the FX-note phrase)
#: ``work/dispatch/2026-10-07-任務單-PR-0-決策卡第4條ATR回填繞過book層撤下.md`` (風控裁定 R0-4)
MIXED_CURRENCY_NOTE = (
    "此標的的持倉橫跨多種計價幣別，無法決定單一匯率，價格與 ATR 相關的上限不計算。"
)

#: This symbol's lots share one currency, but it is not the one their market is
#: quoted in (task X-3c, KX-A4): no rate is looked up for them, the close and
#: the ATR are withheld together, and no FX sentence or source methodology is
#: stated, because nothing was converted. Same frame as
#: :data:`MIXED_CURRENCY_NOTE` (R0-4), which takes precedence when the lots are
#: in more than one currency. Also the alert snapshot's ``price_cap_cause``
#: through :attr:`BookContext.price_withheld_note` (KX-A11, RX-6).
#: 風控核可文案,修改須重新送審(2026-10-08)
#: ``work/reviews/2026-10-08-X-3c-幣別與市場不符-揭露字面-風控審查.md`` (第二段 (c))
#: ``work/dispatch/2026-10-07-任務單-X-3-持倉幣別與市場不符的legacy列.md`` (X-3c 第二段裁定)
CURRENCY_MARKET_MISMATCH_NOTE = "此標的的持倉幣別與市場不符，價格與 ATR 相關的上限不計算。"

#: The rate actually used, with the freshness the reader needs to judge it.
FX_APPLIED_NOTE = (
    "價格與 ATR 以 {pair} 匯率 {rate} 換算為台幣"
    "（資料狀態 {status}、來源 {source}、匯率日期 {as_of}）。"
)

#: Follows the two source sentences when the applied quote and the valuator's
#: rate came from two different sources (task RK-2, (d)): the figures then mix
#: both, and the Yahoo sentence's "本次台灣銀行來源不可用" held for one of the two
#: lookups only. The attribution is positional, so the order the sentences are
#: appended in (quote first, valuator second) is part of this wording's meaning.
#: 風控核可文案,修改須重新送審(2026-10-08)
#: ``work/reviews/2026-10-08-RK-2-銜接句逐字審與X-10核對-風控審查.md`` (RK2-R2, RK2-R2a)
FX_MIXED_SOURCES_NOTE = (
    "此處數字混用兩個來源的匯率，緊接在前的兩項來源說明依序對應價格與 ATR 的換算、"
    "持倉市值與總資產；「本次台灣銀行來源不可用」僅適用於部分查詢。"
)

#: Precedes the valuator's source sentence(s) when no quote was applied to this
#: context's figures but this symbol's own valued lots were converted (task
#: RK-4, (B) without (A′)): it scopes the sentence(s) after it to the converted
#: market value and total equity, so they are not read as covering the price
#: and the ATR. Its premise (risk RK4-E1b-2) is that the surface it appears on
#: shows no figure the applied quote was multiplied into: the card and the push
#: state it only when they show none (PR-RK4c,
#: :func:`app.advice.limits.shows_price_input_figure`), ``/limits`` only when
#: its G1 is empty; the one exception is the test-only cell of risk RK4-C4.
#: Always the first item of the disclosure, immediately before the sentence(s)
#: it scopes, and never next to :data:`FX_MIXED_SOURCES_NOTE` (RK4-R2).
#: 風控核可文案,修改須重新送審(2026-10-08)
#: ``work/reviews/2026-10-08-W-RK4-1-W-RK5-1逐字審與X-11-X-12核對-風控審查.md`` (W-RK4-1, 替代案 A)
FX_VALUATION_SCOPE_NOTE = (
    "此處來源說明所指的匯率，只對應持倉市值與總資產中經換算的部分，不含價格與 ATR。"
)


@dataclass(frozen=True)
class FxQuote:
    """One instrument-currency -> TWD rate with the provenance it must carry.

    ``rate`` is ``None`` when the source had nothing usable: the failure is
    still delivered as a quote so its ``status``/``as_of``/``source`` can reach
    ``notes`` instead of collapsing into a silent absence (ADR-0005 F-3).

    ``as_of`` is the **date of the rate that was used**, not the time the fetch
    happened -- a rate from three days ago used today is exactly what a reader
    needs to see. ``source_note`` carries the source's own standing disclosure
    (unverified endpoint, mid-point model value, ...) so this module does not
    have to know which adapter produced the number (F-4).
    """

    pair: str
    rate: float | None
    as_of: str | None
    source: str
    status: DataStatus
    source_note: str = ""


#: The ``symbol`` a book-level context carries (:func:`build_book_level_context`).
#: Nothing reads it: the only cap evaluated against such a context is the one
#: whose verdict is about the whole book rather than about a holding -- gross
#: exposure -- and its sentence names no symbol. (Cap 5 was the second such cap
#: until C5 gave it a per-symbol input; it is aggregated per holding now, D-7.)
#: It is spelled as a visible label rather than left
#: blank so that a value leaking into prose would be recognisable as this
#: placeholder instead of reading like a ticker.
BOOK_LEVEL_SYMBOL = "（整體帳本）"


#: Which response a :class:`BookContext` was built for: one symbol's advice
#: card (``symbol``) or the whole-book overview (``book``). The two choose the
#: notes' direction clause by different rules (ADR-0022 Decision 5).
BookScope = Literal["symbol", "book"]


@dataclass(frozen=True)
class SectorComparison:
    """What the overview's cap 2 aggregate reported, as its notes need it.

    ``reported_sector`` is the industry the aggregate's verdict was read from
    (the "回報產業 Y" of ADR-0022), or ``None`` when no industry could be
    compared at all. It only exists once the aggregate has been computed,
    which is why the overview's notes are assembled after it (ADR-0022 M-5,
    ADR-0023 Decision 8-1).
    """

    reported_sector: str | None


@dataclass(frozen=True)
class BookContext:
    """A :class:`PortfolioContext` plus what had to be assumed or left out.

    The notes are not stored: what they say depends on verdicts that do not
    exist yet when the context is built (the overview's reported industry; in
    a later change, cap 3's status), so the context keeps the *inputs* and the
    caller assembles the notes with :func:`book_notes` once those verdicts are
    known (ADR-0023 Decision 8-1).
    """

    context: PortfolioContext
    held: bool
    #: The summary every book-level note is stated about.
    summary: PortfolioSummary
    scope: BookScope
    position_ids: list[int] = field(default_factory=list)
    #: Currency of the matched holding(s), or ``None`` for a candidate.
    currency: str | None = None
    #: The notes about this symbol (or, for the book scope, about the book's
    #: classification) that follow the book-level ones, already final. The
    #: version for a response that shows a figure the applied quote was
    #: multiplied into (PR-RK4c, R4c-5): its FX tail is :attr:`fx_note` -- the
    #: applied-rate sentence only when the close was usable (R4c-5 (b)) -- then
    #: the items of :attr:`fx_disclosure`.
    symbol_notes: tuple[str, ...] = ()
    #: The same notes for a response that shows no such figure (R4c-5 (a)): the
    #: applied-rate sentence is left out (a failed-conversion sentence stays),
    #: and the FX tail is the items of :attr:`fx_disclosure_without_quote`.
    #: Symbol scope only; :func:`book_notes` picks between the two.
    symbol_notes_without_quote: tuple[str, ...] = ()
    #: The rate applied (``1.0`` for TWD), or ``None`` when none could be.
    fx_rate: float | None = None
    #: The single FX sentence from the notes, for callers whose output shape
    #: has no notes list of its own (the alert snapshot).
    fx_note: str | None = None
    #: The FX sources' standing disclosures, joined by single spaces, for a
    #: response that shows a figure the applied quote was multiplied into (the
    #: version *with* the quote, PR-RK4c). Present if and only if (risk RK4-R1,
    #: second revision of X3-R1):
    #:
    #: * (A′) the quote reached this context -- applied, to a usable close, and
    #:   carrying a sentence -- the quote's sentence first; when the book's
    #:   valued rows of the same pair were converted on another source, that
    #:   source's sentence and :data:`FX_MIXED_SOURCES_NOTE` follow (task RK-2);
    #:   or
    #: * (B) otherwise, at least one of this symbol's own lots is ``ok`` with a
    #:   valuator rate that is not ``UNAVAILABLE`` and carries a sentence --
    #:   :data:`FX_VALUATION_SCOPE_NOTE` first, then the valuator's sentences
    #:   (task RK-4), never the quote's and never the bridge.
    #:
    #: ``None`` otherwise: a TWD symbol, a candidate, lots that are not valued
    #: or whose rate failed, and lots whose currency is not their market's
    #: (KX-A11). (A′) is only a necessary condition for the quote's sentences
    #: (risk RK4-E1b-1): the response picks this field or
    #: :attr:`fx_disclosure_without_quote` with
    #: :func:`app.advice.limits.shows_price_input_figure`, from what it shows.
    fx_disclosure: str | None = None
    #: The same disclosure for a response that shows no figure the quote was
    #: multiplied into (PR-RK4c, R4c-4): (B)'s content when (B) holds, else
    #: ``None`` -- never the quote's sentence, never the bridge. Equal to
    #: :attr:`fx_disclosure` whenever :attr:`disclosed_quote` is ``None``.
    fx_disclosure_without_quote: str | None = None
    #: Why this layer withheld the close and the ATR, when it can name the
    #: cause: a failed FX conversion (the same sentence as ``fx_note``) or lots
    #: whose currency is not their market's (:data:`CURRENCY_MARKET_MISMATCH_NOTE`,
    #: task X-3 KX-A11). ``None`` when the rate was applied or not needed, and
    #: for a holding in more than one currency (K-1). The alert snapshot reads
    #: it as ``price_cap_cause`` and states no condition of its own (RX-6).
    price_withheld_note: str | None = None
    #: The quote that reached this context under (A′), or ``None`` (task RK-4,
    #: R4-22): whether it is disclosed is each response's call, through
    #: :func:`app.advice.limits.shows_price_input_figure` (PR-RK4c, R4c-9).
    #: Set by :func:`build_book_context` only; the overview
    #: (:mod:`app.advice.book_limits`) collects it from the holdings it compares
    #: and hands it to :func:`limits_fx_disclosures`. Nothing else reads it.
    disclosed_quote: FxQuote | None = None
    #: ``(source, source_note)`` of every rate the valuator multiplied into the
    #: book's total -- ``ok`` rows whose rate is neither ``None`` nor
    #: ``UNAVAILABLE`` and carries a sentence -- one per source id, in summary
    #: order (task RK-4, R4-22 / R4-24: the book scope's (B)). Set by
    #: :func:`build_book_level_context` only, and read by
    #: :func:`limits_fx_disclosures` only.
    valued_fx_sources: tuple[tuple[str, str], ...] = ()

    @property
    def notes(self) -> list[str]:
        """Compatibility view: :func:`book_notes` for a symbol-scope context.

        Production code does not read this (ADR-0023 KD-2): every response is
        assembled through :func:`book_notes` at the point its verdicts are
        known. A book-scope context has no notes before its aggregate exists,
        so reading this on one raises rather than guessing the reported
        industry.
        """
        return book_notes(self)


def _matching(
    summary: PortfolioSummary, symbol: str, market: Market | None
) -> list[SummaryPosition]:
    """Positions in ``summary`` for ``symbol`` (optionally pinned to a market)."""
    wanted = symbol.strip().upper()
    return [
        position
        for position in summary.positions
        if position.symbol.strip().upper() == wanted
        and (market is None or position.market == market)
    ]


def _book_equity(summary: PortfolioSummary) -> tuple[float, int, int]:
    """Return ``(valued market value, valued count, total count)``.

    The market value comes from ``totals``, which the summary layer already
    restricts to the ``ok`` valuations.
    """
    total = len(summary.positions)
    valued = sum(1 for position in summary.positions if position.valuation.status == "ok")
    return float(summary.totals.market_value_twd), valued, total


def _fully_valued(summary: PortfolioSummary) -> bool:
    """Whether every stored position could be valued.

    An empty book is ``True``: nothing failed to value, and an exposure of zero
    against a reported net worth is a fact, not a gap.
    """
    return all(position.valuation.status == "ok" for position in summary.positions)


def _gross_exposure_note(net_worth: SelfReportedNetWorth | None) -> str:
    """The standing sentence about the exposure cap, in whichever state it is in.

    Three states, three sentences: no figure at all, a usable one, and one the
    freshness rule has retired. The third exists because the second is written
    in the present tense -- claiming a division that an expired report does not
    get to perform, right beside a cap saying it could not perform it.
    """
    if net_worth is None:
        return GROSS_EXPOSURE_NOTE
    if net_worth.age_days >= NET_WORTH_STALE_AFTER_DAYS:
        return GROSS_EXPOSURE_EXPIRED_NOTE.format(
            reported_at=format_reported_at(net_worth.reported_at),
            amount=net_worth.amount_twd,
            days=NET_WORTH_STALE_AFTER_DAYS,
        )
    return GROSS_EXPOSURE_SELF_REPORTED_NOTE.format(
        reported_at=format_reported_at(net_worth.reported_at), amount=net_worth.amount_twd
    )


def _position_rollup(
    positions: list[SummaryPosition],
) -> tuple[float, float | None, float, int]:
    """Roll up the ``ok``-valued rows: ``(market value, cost, quantity, skipped)``.

    Both money figures are the position's **own TWD contribution** as the
    summary layer computed it, for the same reason ``_sector_rollup`` uses them:
    these two feed ``position_market_value_twd`` / ``position_cost_twd``, which
    sit over TWD denominators (``total_equity_twd``, and the TWD price used for
    share sizing). Multiplying quantity by a close in the instrument's own
    currency would put a USD numerator over a TWD denominator and make a foreign
    holding's share of the book read low by the exchange rate -- "risk looks
    smaller than it is", the one direction these caps must never err in -- and
    the same mixed unit would then travel into every suggested share count via
    :func:`app.advice.limits.notional_caps`. Only the share count stays as it
    is: a quantity has no currency.

    ``cost`` is ``None`` when no row carried one, so the unrealized-P&L ratio
    reports "no cost" instead of a zero that would read as a -100% loss.
    """
    market_value = Decimal(0)
    cost = Decimal(0)
    quantity = Decimal(0)
    has_cost = False
    skipped = 0
    for position in positions:
        if position.valuation.status != "ok" or position.market_value_twd is None:
            skipped += 1
            continue
        market_value += position.market_value_twd
        if position.cost_twd is not None:
            cost += position.cost_twd
            has_cost = True
        quantity += position.quantity
    return (
        float(market_value),
        float(cost) if has_cost else None,
        float(quantity),
        skipped,
    )


def sector_categories(positions: list[SummaryPosition]) -> frozenset[str]:
    """The distinct industry categories filed on ``positions`` -- categories(G).

    ADR-0022 M-1/M-3: the one definition of "which industries a holding was
    filed under", read by every per-group rule (the industry numerators, the
    unvalued classification, the AC-12.5 rollup, the overview's exclusion
    sentences). A set, not a sequence: anything that prints these in an order
    sorts them itself (:func:`app.advice.book_limits.format_sector_list`).
    """
    return frozenset(position.sector for position in positions if position.sector)


def _resolve_sector(matched: list[SummaryPosition]) -> tuple[str | None, SectorGap | None]:
    """The symbol's industry category -> ``(sector, gap)``.

    ``gap`` is ``None`` exactly when a category was resolved; otherwise it names
    *which* of the five states left this symbol unclassified, so cap 2 can say
    the one true thing about each instead of one sentence covering all five
    (see :data:`app.advice.limits.SectorGap`). Only this layer can tell them
    apart: it is the one that sees whether anything is held, in which market,
    with which instrument type, and whether the holdings agree with each other.
    """
    if not matched:
        return None, "no_position"
    categories = sorted(sector_categories(matched))
    if len(categories) > 1:
        return None, "mixed"
    if categories:
        return categories[0], None
    classifiable = [
        position for position in matched if position.market in SECTOR_CLASSIFIED_MARKETS
    ]
    if not classifiable:
        return None, "unsupported_market"
    if all(position.instrument_type in ETF_INSTRUMENT_TYPES for position in classifiable):
        # Every TW lot behind this symbol is a fund: there is no company-level
        # industry it could truthfully be filed under, so the "fill it in"
        # guidance would be an instruction the owner cannot follow (D6). The
        # symbol stays excluded from cap 2 exactly as before.
        return None, "etf_instrument"
    # At least one holding *could* carry a category, so naming the action is
    # a true statement. A symbol held in both markets lands here too: the TW
    # leg is the one that would turn the cap on. A stock lot alongside an ETF
    # lot keeps this state as well -- the stock lot is the one the guidance
    # sentence is true for.
    return None, "unfiled"


#: The sub-type an unclassified group is counted under, by the gap
#: :func:`_resolve_sector` gives it. A group with no category can only be in
#: one of these three states (``no_position`` needs no holding, ``mixed`` needs
#: two categories), and valued and unvalued lots read the same table, so an
#: ETF can never count as "may belong" while unvalued and "does not" once
#: valued (ADR-0022 Decision 4, C-1).
_UNKNOWN_SUBTYPE: dict[SectorGap, Literal["tw_unfiled", "etf", "non_tw"]] = {
    "unfiled": "tw_unfiled",
    "etf_instrument": "etf",
    "unsupported_market": "non_tw",
}


@dataclass(frozen=True)
class _SectorGroup:
    """One ``(symbol, market)`` group of the book with its industry facts.

    ADR-0022 classifies per holding, not per lot: a lot with no category
    beside a lot filed under X is an X lot, and a holding filed under X and Y
    counts in both. ``gap`` is :func:`_resolve_sector`'s answer for the group,
    so the sub-type of an unclassified group is decided by the same rules as
    cap 2's own sentence for that holding.
    """

    positions: tuple[SummaryPosition, ...]
    categories: frozenset[str]
    gap: SectorGap | None

    def unknown_subtype(self) -> Literal["tw_unfiled", "etf", "non_tw"]:
        """Which kind of "no industry" this group is; only for an empty group."""
        if self.gap is None:  # pragma: no cover - callers check ``categories`` first
            raise ValueError("a group with a resolved category has no unknown sub-type")
        return _UNKNOWN_SUBTYPE[self.gap]


def _sector_groups(summary: PortfolioSummary) -> list[_SectorGroup]:
    """The book as ``(symbol, market)`` groups, each classified once.

    The single per-holding resolution ADR-0022 Decision 1 requires: the
    industry numerators (:func:`_sector_rollup`), the AC-12.5 rollup
    (:func:`_valued_unclassified`) and the unvalued classification
    (:func:`_unvalued_composition`) all read these groups and nothing else.
    The key matches :func:`app.advice.book_limits._group_positions`.
    """
    grouped: dict[tuple[str, Market], list[SummaryPosition]] = {}
    for position in summary.positions:
        grouped.setdefault((position.symbol.strip().upper(), position.market), []).append(position)
    return [
        _SectorGroup(
            positions=tuple(positions),
            categories=sector_categories(positions),
            gap=_resolve_sector(positions)[1],
        )
        for positions in grouped.values()
    ]


def _is_valued(position: SummaryPosition) -> bool:
    """Whether ``position`` contributes to the book's totals (rule 1)."""
    return position.valuation.status == "ok" and position.market_value_twd is not None


def _sector_rollup(groups: list[_SectorGroup], sector: str) -> float:
    """``sector``'s TWD market value across the whole book.

    Only ``ok`` valuations are summed (rule 1) and only their own TWD
    contribution is used, so the numerator and ``total_equity_twd`` come from
    the same figures. Per holding (ADR-0022 M-1, K-2): every valued lot of a
    holding filed under ``sector`` counts, its unfiled lots included, and a
    holding filed under several categories counts in full in each of them --
    the conservative reading, which can only make a share read high. Shares of
    different industries therefore may not be added up: nothing in the
    product does (M-1 required).
    """
    total = Decimal(0)
    for group in groups:
        if sector not in group.categories:
            continue
        for position in group.positions:
            if _is_valued(position) and position.market_value_twd is not None:
                total += position.market_value_twd
    return float(total)


def _valued_unclassified(groups: list[_SectorGroup]) -> tuple[UnknownSectorLots, float]:
    """Valued lots of holdings filed under no category: ``(sub-types, value)``."""
    counts: Counter[str] = Counter()
    value = Decimal(0)
    for group in groups:
        if group.categories:
            continue
        for position in group.positions:
            if _is_valued(position) and position.market_value_twd is not None:
                counts[group.unknown_subtype()] += 1
                value += position.market_value_twd
    return UnknownSectorLots(**counts), float(value)


def _unclassified_rollup(groups: list[_SectorGroup]) -> tuple[int, float]:
    """Valued holdings that sit outside every industry: ``(count, market value)``.

    This is what AC-12.5 requires disclosing: valued holdings that belong to
    *some* industry the user has not named, and therefore make every industry's
    share look smaller than it is. The value is carried beside the count because
    the count alone does not say how much of the book is missing from the ratio.
    Only holdings with no category at all count (ADR-0022 M-1): an unfiled lot
    beside a filed one is already in that industry's numerator.
    """
    lots, value = _valued_unclassified(groups)
    return lots.total(), value


def _unvalued_composition(
    groups: list[_SectorGroup], matched: list[SummaryPosition], sector: str | None
) -> UnvaluedComposition:
    """Partition the book's unvalued lots relative to industry ``sector``.

    ADR-0022 Decision 1 / M-3: this symbol's own lots are ``own`` whatever
    ``sector`` is; another holding is ``same`` when ``sector`` is among its
    categories, ``unknown`` (by sub-type) when it has none, ``other``
    otherwise. "Unvalued" is a valuation that is not ``ok`` -- the same test
    the book-level note counts with, so the four counts add up to that note's.
    """
    own_ids = {id(position) for position in matched}
    own = same = other = 0
    unknown: Counter[str] = Counter()
    for group in groups:
        for position in group.positions:
            if position.valuation.status == "ok":
                continue
            if id(position) in own_ids:
                own += 1
            elif sector is not None and sector in group.categories:
                same += 1
            elif not group.categories:
                unknown[group.unknown_subtype()] += 1
            else:
                other += 1
    return UnvaluedComposition(
        own_lots=own,
        same_sector_lots=same,
        unknown_sector_lots=UnknownSectorLots(**unknown),
        other_sector_lots=other,
    )


def unvalued_lots_in_sector(summary: PortfolioSummary, sector: str) -> int:
    """Unvalued lots of every holding filed under ``sector`` (ADR-0022 M-3/M-5).

    What "the reported industry Y has same" means on the overview: a holding
    filed under several categories counts for each of them.
    """
    return sum(
        1
        for group in _sector_groups(summary)
        if sector in group.categories
        for position in group.positions
        if position.valuation.status != "ok"
    )


def _sector_unclassified_note(groups: list[_SectorGroup], equity: float) -> str | None:
    """AC-12.5's disclosure, or ``None`` when there is nothing to disclose.

    The share is only stated when there is a denominator to state it against. An
    unclassified *valued* row is itself part of ``equity``, so a non-zero count
    with a zero book is not reachable in practice; when it is, every
    equity-based cap already reports ``not_evaluable`` and this disclosure would
    have nothing to qualify.
    """
    count, value = _unclassified_rollup(groups)
    if not count or equity <= 0.0:
        return None
    return SECTOR_UNCLASSIFIED_NOTE.format(
        count=count, amount=value, share=format_percent(value / equity)
    )


def self_reported_net_worth(
    amount_twd: float | None,
    updated_at: str | None,
    *,
    now: datetime | None = None,
) -> SelfReportedNetWorth | None:
    """Turn the stored settings pair into the risk layer's view of it.

    This is the single place the clock is read for FR-9, so the freshness the
    settings page displays and the freshness the cap enforces can never drift
    apart. ``None`` comes back when there is nothing usable to report:

    * no amount, or a non-positive one (the settings boundary already rejects
      those with a 422; this is the second line, not the first);
    * no timestamp, or one that cannot be parsed -- an amount whose age is
      unknown cannot be shown to be fresh, and FR-9 (b) forbids using it
      anyway, so it is withheld rather than passed on as if it were current.

    A naive stored timestamp is read as UTC, matching what
    :meth:`app.settings.store.SettingsStore.save` writes.
    """
    if amount_twd is None or amount_twd <= 0.0 or updated_at is None:
        return None
    try:
        reported = datetime.fromisoformat(updated_at)
    except ValueError:
        return None
    if reported.tzinfo is None:
        reported = reported.replace(tzinfo=UTC)
    moment = now if now is not None else datetime.now(UTC)
    # A timestamp in the future (clock skew, or an edited database) is treated
    # as "reported now" rather than as a negative age.
    age_days = max((moment - reported).days, 0)
    return SelfReportedNetWorth(amount_twd=amount_twd, reported_at=updated_at, age_days=age_days)


def kelly_inputs_of(
    row: KellyInputRow | None,
    *,
    ci_includes_no_edge: bool = False,
    now: datetime | None = None,
) -> KellyInputs | None:
    """Turn one stored Kelly row into the risk layer's view of it (D-6).

    The Kelly half of what :func:`self_reported_net_worth` does for FR-9, and
    for the same reason: this is the single place the clock is read for cap 5,
    so the age the settings page shows and the age the cap enforces cannot
    drift apart. Ageing itself is delegated to
    :func:`app.kelly.models.ageing_of` -- the one place the "no anchor means
    expired" rule lives -- rather than re-derived here, where a second
    derivation could land on a friendlier answer.

    ``None`` in gives ``None`` out, and that ``None`` carries a specific
    meaning downstream: **no pair has ever been entered**. An expired row is
    *not* collapsed into it. Cap 5 has four different things to say about an
    unusable input ((g-1) to (g-4)) and could not tell them apart from an
    absence, so the row travels on with its age and source and the cap decides
    (D-6 puts the expiry判定 in ``_check_kelly_fraction``).

    ``ci_includes_no_edge`` is passed in, never computed here: 約束 36 makes
    ``app/api/kelly.py`` the one place that reduces the stored interval to that
    boolean.

    This function reads no database. The caller resolves the row, exactly as it
    resolves prices and FX rates, so this module stays the pure function
    ADR-0005 decision 5 requires.
    """
    if row is None:
        return None
    ageing = ageing_of(row, now=now)
    return KellyInputs(
        win_rate=row.win_rate,
        payoff_ratio=row.payoff_ratio,
        source=row.source,
        age_days=ageing.age_days,
        # 6-A: a plain calendar day, never an ISO datetime. The backtest
        # anchor's time of day is padded, so rendering it would show precision
        # the measurement does not have; the manual anchor is truncated to the
        # same shape so the two sentences cannot be told apart by their format.
        anchored_at=None if ageing.anchored_at is None else ageing.anchored_at.date().isoformat(),
        strategy_id=row.strategy_id,
        oos_start_date=row.oos_start_date,
        oos_end_date=row.oos_end_date,
        oos_round_trips=row.oos_round_trips,
        ci_includes_no_edge=ci_includes_no_edge,
    )


def _book_level_notes(
    summary: PortfolioSummary, net_worth: SelfReportedNetWorth | None, *, direction: str
) -> list[str]:
    """The notes that describe the book itself, whatever symbol is being asked about.

    Assembled in one place so the per-symbol context and the book-level context
    state the same three things about the same book: what stands in for total
    equity, which state the exposure cap's denominator is in, and how much of
    the book could not be valued at all.

    ``direction`` is the clause that says which way the unvalued lots bend the
    ratios (ADR-0022 Decision 5), chosen once per response by the caller --
    :func:`book_notes` -- from the rule for that response's scope. Every cause
    sentence takes the same clause.
    """
    notes = [EQUITY_BASIS_NOTE, _gross_exposure_note(net_worth)]
    _, valued_count, total_count = _book_equity(summary)
    if total_count and valued_count < total_count:
        # Counted by cause (風控 A-5): a cache-only book (ADR-0010 D-1) marks a
        # price it did not ask for with ``price_not_queried``, while a missing
        # FX rate was really asked for -- the two must not share one sentence.
        # A row whose currency is not its market's is a third cause (task
        # X-3c, KX-A9): counted first, so it lands in no other group, and
        # stated last (W4 -> W5 -> (b)).
        unvalued = [item for item in summary.positions if item.valuation.status != "ok"]
        mismatched = [
            item for item in unvalued if CURRENCY_MARKET_MISMATCH in item.valuation.missing
        ]
        not_queried = sum(
            PRICE_NOT_QUERIED in item.valuation.missing
            for item in unvalued
            if CURRENCY_MARKET_MISMATCH not in item.valuation.missing
        )
        asked = len(unvalued) - len(mismatched) - not_queried
        if asked:
            notes.append(
                UNVALUED_NOTE_TEMPLATE.format(
                    cause=UNVALUED_POSITIONS_CAUSE.format(count=asked), direction=direction
                )
            )
        if not_queried:
            notes.append(
                UNVALUED_NOTE_TEMPLATE.format(
                    cause=UNVALUED_POSITIONS_CAUSE_CACHE_ONLY.format(count=not_queried),
                    direction=direction,
                )
            )
        if mismatched:
            notes.append(
                UNVALUED_NOTE_TEMPLATE.format(
                    cause=CURRENCY_MARKET_MISMATCH_CAUSE.format(count=len(mismatched)),
                    direction=direction,
                )
            )
    return notes


def _symbol_direction(context: PortfolioContext) -> str:
    """The direction clause for one symbol's advice card (ADR-0022 Decision 5).

    Order of the rules, first match wins:

    1. This symbol has unvalued lots of its own
       (:func:`app.advice.limits.symbol_has_unvalued_lots`, the predicate caps
       1, 4 and 5 read) -> D-d1 when they are the book's only unvalued lots
       (the other three counts are 0), else D-d2 -- ahead of every rule below
       and whatever X is.
    2. The card has no industry (X is ``None``) -> D-a.
    3. Some unvalued lot is, or may be, in X (same or unknown) -> D-P.
    4. Otherwise -> D-a.

    "Same" and "unknown" are read through
    :func:`app.advice.limits.sector_numerator_gaps`, the reading cap 2's own
    verdict uses, so the clause and the verdict cannot disagree.
    """
    composition = context.unvalued
    if composition is None:
        raise ValueError("a symbol-scope context must carry its unvalued composition")
    if symbol_has_unvalued_lots(context):
        others = (
            composition.same_sector_lots
            + composition.unknown_sector_lots.total()
            + composition.other_sector_lots
        )
        return UNVALUED_DIRECTION_OWN_ONLY if others == 0 else UNVALUED_DIRECTION_OWN_AND_OTHERS
    if context.sector is None:
        return UNVALUED_DIRECTION_READS_HIGH
    gaps = sector_numerator_gaps(context)
    if gaps.same > 0 or gaps.unknown:
        return UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(
            target=UNVALUED_DIRECTION_TARGET_SYMBOL.format(sector=context.sector)
        )
    return UNVALUED_DIRECTION_READS_HIGH


def _book_direction(book: BookContext, comparison: SectorComparison) -> str:
    """The direction clause for the overview (ADR-0022 Decision 5, M-5).

    First match wins (risk-compliance 2026-10-07 correction: "Y undefined"
    comes first, otherwise D-P would name compared industries that do not
    exist, right beside a cap 2 that says none could be compared):

    1. No industry could be compared (Y undefined,
       ``comparison.reported_sector is None``) -> D-a.
    2. The book holds an unvalued lot in no industry, or the reported industry
       Y has an unvalued lot (a holding filed under several categories counts
       for each, M-3 / M-5) -> D-P.
    3. Otherwise -> D-a.

    Whether anything was compared is read off ``comparison`` only -- the
    aggregate in :mod:`app.advice.book_limits` is its single source -- and
    never recomputed here.
    """
    composition = book.context.unvalued
    if composition is None:
        raise ValueError("a book-scope context must carry its unvalued composition")
    reported = comparison.reported_sector
    if reported is None:
        return UNVALUED_DIRECTION_READS_HIGH
    if (
        composition.unknown_sector_lots.total() > 0
        or unvalued_lots_in_sector(book.summary, reported) > 0
    ):
        return UNVALUED_DIRECTION_SECTOR_MAY_READ_LOW.format(target=UNVALUED_DIRECTION_TARGET_BOOK)
    return UNVALUED_DIRECTION_READS_HIGH


def book_notes(
    book: BookContext,
    *,
    sector_comparison: SectorComparison | None = None,
    quote_shown: bool | None = None,
) -> list[str]:
    """Every note of one response, assembled once its verdicts are known.

    The finalizer ADR-0023 Decision 8-1 asks for: both responses -- the advice
    card and the overview -- build their ``notes`` here and nowhere else, after
    the caps have been evaluated, in the same order :attr:`BookContext.notes`
    always had (book-level notes first, then the symbol's own).

    ``sector_comparison`` is the overview's cap 2 result and is required for a
    book-scope context (its D-P rule reads the reported industry, which only
    the aggregate knows) and refused for a symbol-scope one (the card's rule
    does not read it). A later change adds cap 3's status the same way, as a
    keyword-only argument.

    ``quote_shown`` is the response's own answer to
    :func:`app.advice.limits.shows_price_input_figure` (PR-RK4c, R4c-6):
    ``False`` picks :attr:`BookContext.symbol_notes_without_quote`, ``True``
    or ``None`` (the compatibility view) :attr:`BookContext.symbol_notes`. It
    is refused for a book-scope context, whose FX sentences are stated by
    :func:`limits_fx_disclosures` instead. Every production symbol-scope call
    passes it (``tests/test_rk4c_quote_shown.py``).
    """
    if book.scope == "symbol":
        if sector_comparison is not None:
            raise ValueError("a symbol-scope context takes no sector comparison")
        direction = _symbol_direction(book.context)
    else:
        if sector_comparison is None:
            raise ValueError("a book-scope context needs the aggregate's sector comparison")
        if quote_shown is not None:
            raise ValueError("a book-scope context takes no quote_shown")
        direction = _book_direction(book, sector_comparison)
    symbol_notes = book.symbol_notes_without_quote if quote_shown is False else book.symbol_notes
    return [
        *_book_level_notes(book.summary, book.context.net_worth, direction=direction),
        *symbol_notes,
    ]


def build_book_level_context(
    summary: PortfolioSummary, *, net_worth: SelfReportedNetWorth | None = None
) -> BookContext:
    """The whole book as one context, for the cap that is not about a holding.

    One of the five caps asks a question with a single book-level answer: gross
    exposure, the valued book over the reported net worth. It reads no
    per-symbol field, so it needs no symbol -- the context therefore carries
    :data:`BOOK_LEVEL_SYMBOL` and leaves every per-symbol field unset, which is
    exactly what makes caps 1, 2, 4 and 5 report ``not_evaluable`` if anyone
    evaluates them here. **They must not be read from this context**: their
    book-level verdicts are aggregated per symbol by
    :mod:`app.advice.book_limits`, and a ``not_evaluable`` produced by an unset
    field would look like a fact about the user's book.

    ``kelly`` is unset here and there is no parameter to set it with. Cap 5
    became a per-symbol cap in C5 (D-7): its input is keyed on
    ``(symbol, market)``, so the book as a whole has no pair to be judged
    against, and one borrowed from any single holding would be applied to all
    of them. ``tests/test_advice_book.py`` pins the field at ``None`` here.

    ``held`` is ``False`` and ``position_ids`` empty for the same reason: this
    context stands for no holding.
    """
    equity, _, _ = _book_equity(summary)
    # Classified once per context and shared by every per-group rule below.
    groups = _sector_groups(summary)
    notes: list[str] = []
    # Attached on the same condition as in :func:`build_book_context`: the
    # sentence qualifies an industry ratio, so it is stated when there is at
    # least one classified valued holding for that ratio to be computed from.
    if _has_classified_holding(summary):
        unclassified_note = _sector_unclassified_note(groups, equity)
        if unclassified_note is not None:
            notes.append(unclassified_note)
    context = PortfolioContext(
        symbol=BOOK_LEVEL_SYMBOL,
        total_equity_twd=equity,
        # Same rule as the per-symbol context: the numerator is only offered
        # when a denominator exists to divide it by (module docstring, rule 3).
        gross_exposure_twd=equity if net_worth is not None else None,
        net_worth=net_worth,
        book_fully_valued=_fully_valued(summary),
        # Classified like any other context, with no symbol of its own and no
        # industry: so no path that is shown to a user ever reaches the
        # "caller did not say" fallback (ADR-0023 R-10), and the overview's
        # direction clause can read the unknown lots off it.
        unvalued=_unvalued_composition(groups, [], None),
        valued_unclassified_lots=_valued_unclassified(groups)[0],
    )
    # The book scope's (B) (risk RK4-R5, second group): the equity and the
    # exposure every cap divides by were converted with these rates. The one
    # judgement point RK4-R5 allows here; ``fx_open`` is never read (R4-24).
    valued_fx_sources: list[tuple[str, str]] = []
    for position in summary.positions:
        info = position.valuation.fx
        if (
            _converted_by_valuator(position)
            and info is not None
            and all(info.source != seen for seen, _ in valued_fx_sources)
        ):
            valued_fx_sources.append((info.source, info.source_note))
    return BookContext(
        context=context,
        held=False,
        summary=summary,
        scope="book",
        symbol_notes=tuple(notes),
        valued_fx_sources=tuple(valued_fx_sources),
    )


def _has_classified_holding(summary: PortfolioSummary) -> bool:
    """Whether any valued holding carries an industry category at all."""
    return any(
        position.valuation.status == "ok" and position.sector is not None
        for position in summary.positions
    )


def build_book_context(
    summary: PortfolioSummary,
    *,
    symbol: str,
    market: Market | None = None,
    close: float | None = None,
    currency: str | None = None,
    atr: float | None = None,
    fx: FxQuote | None = None,
    net_worth: SelfReportedNetWorth | None = None,
    kelly: KellyInputs | None = None,
) -> BookContext:
    """Assemble the risk-budget context for ``symbol`` against the whole book.

    ``close`` is the latest close **in the instrument's own currency** (the unit
    the caps compare); pass ``None`` when no price is available and the
    price-dependent caps will report ``not_evaluable`` instead of guessing.
    A close that is not usable (zero, negative or not finite, per
    :func:`app.data.price_guard.usable_price`) is withheld exactly like
    ``None``, and ``atr`` is withheld with it -- one judgement for both, since
    an ATR computed from the same bad bar is no evidence either. No note is
    added for this; the caps that read the price or the ATR report
    ``not_evaluable`` with their existing reasons. This layer judges what it is
    handed: the callers load bars separately from the valuator, so the guard
    is applied here too rather than trusted from upstream.
    A symbol with no holding yields a *candidate* context
    (``position_market_value_twd=0``, ``quantity=0``) so a card can still be
    produced for something the user does not own yet.

    ``fx`` is the instrument-currency -> TWD quote the caller resolved. It is
    ignored for a TWD instrument (which needs no conversion) and required for
    every other currency; without a usable one the price is withheld rather
    than scaled by an invented rate.

    ``net_worth`` is the figure the user reported on the settings page, built
    by :func:`self_reported_net_worth`. It reaches one cap and one cap only
    (gross exposure); ``total_equity_twd`` keeps its old definition whether it
    is supplied or not, so caps 1 and 4 are unaffected by it.

    ``kelly`` is this symbol's stored Kelly pair, built by
    :func:`kelly_inputs_of`. It likewise reaches one cap and one cap only
    (cap 5). Omitting it is a supported state and means exactly what an empty
    ``kelly_inputs`` table means -- the cap reports (g-1), "nothing entered
    yet". A caller that *has* a row and forgets to pass it therefore produces a
    card stating something untrue about the user's own input, which is why the
    production call sites are pinned by
    ``tests/test_book_context_call_sites.py``.
    """
    # One judgement for both price inputs (task F-1, constraint 4).
    priced = close is not None and usable_price(close)
    fully_valued = _fully_valued(summary)
    # The book-level notes are not assembled here: their direction clause
    # depends on this context's classification and is chosen by
    # :func:`book_notes` once the response is assembled.
    notes: list[str] = []
    equity, _, _ = _book_equity(summary)
    # Classified once per context and shared by every per-group rule below.
    groups = _sector_groups(summary)

    matched = _matching(summary, symbol, market)
    market_value, cost, quantity, skipped = _position_rollup(matched)
    if skipped:
        notes.append(SYMBOL_UNVALUED_NOTE.format(count=skipped))

    sector, sector_gap = _resolve_sector(matched)
    if sector_gap == "mixed":
        notes.append(SECTOR_MIXED_DETAIL)
    sector_market_value: float | None = None
    if sector is not None:
        sector_market_value = _sector_rollup(groups, sector)
        unclassified_note = _sector_unclassified_note(groups, equity)
        if unclassified_note is not None:
            notes.append(unclassified_note)

    currencies = sorted({position.currency for position in matched})
    holding_currency = currencies[0] if len(currencies) == 1 else None
    mixed_currencies = len(currencies) > 1
    # Task X-3c (KX-A4): lots in one currency that is not their market's. The
    # mixed case is judged first and keeps its own sentence (R0-4); the
    # judgement is the write rule itself (KX-A1), never a second table.
    mismatched_currency = not mixed_currencies and any(
        not currency_matches_market(position.market, position.currency) for position in matched
    )
    if mixed_currencies:
        notes.append(MIXED_CURRENCY_NOTE)

    effective_currency = holding_currency if matched else currency
    applied: FxQuote | None
    price_withheld_note: str | None
    if mixed_currencies:
        # Which of the two rates would be the right one is undecidable, so the
        # question is refused rather than answered with one of them.
        rate, fx_note, applied = None, None, None
        price_withheld_note = None
    elif mismatched_currency:
        # Which currency the close is really in cannot be told from the row,
        # so no rate is resolved -- not the 1.0 of a TWD holding, not the
        # quote the caller resolved for the bars (KX-A11): no FX sentence, no
        # methodology, and the close and the ATR are withheld below.
        rate, fx_note, applied = None, None, None
        price_withheld_note = CURRENCY_MARKET_MISMATCH_NOTE
        notes.append(CURRENCY_MARKET_MISMATCH_NOTE)
    else:
        rate, fx_note, applied = _resolve_fx(effective_currency, fx)
        price_withheld_note = fx_note if rate is None else None
    # Methodology sentences if and only if (A′) or (B) (risk RK4-R1), in
    # mutually exclusive branches so the bridge and the scope sentence can
    # never meet (RK4-R2).
    # (A′): the quote reached this context -- a necessary condition only
    # (PR-RK4c, R4c-3): whether a figure the response shows was multiplied by
    # it is that response's call. Reached means: applied -- a non-``None``
    # ``rate`` is not that signal, since a TWD holding gets 1.0 whatever quote
    # the caller resolved for the bars (X3-R1) -- to a usable close (RK4-R11
    # (b): an unusable close withholds the price and the ATR below, so the
    # quote converts nothing), and with a sentence of its own.
    # (B): otherwise, this symbol's own valued lots were converted by the
    # valuator; its sentences are stated, scoped by FX_VALUATION_SCOPE_NOTE.
    # (B) is judged once and shared by both versions (R4c-4); KX-A11 lots do
    # not ask it.
    valuation_disclosures: tuple[str, ...] = (
        _valuation_disclosures(matched, summary)
        if not mismatched_currency and _valuation_converted(matched)
        else ()
    )
    disclosures: tuple[str, ...] = ()
    disclosed_quote: FxQuote | None = None
    if mismatched_currency:
        # KX-A11: nothing was converted for these lots, and (B) is not asked.
        disclosures = ()
    elif applied is not None and priced and applied.source_note != "":
        disclosures = _fx_disclosures(applied, summary)
        disclosed_quote = applied
    elif valuation_disclosures:
        disclosures = valuation_disclosures
    if applied is None and not mixed_currencies and not mismatched_currency:
        _log_unapplied_quote(effective_currency, fx, summary)
    fx_disclosure = " ".join(disclosures) if disclosures else None
    # The version for a response that shows no figure the quote was multiplied
    # into (R4c-4): (B)'s content or nothing -- never the quote's sentence,
    # never the bridge. This layer does not judge which version a response
    # shows (R4c-3): the advice endpoint and the alert engine do.
    without_disclosures = valuation_disclosures
    fx_disclosure_without_quote = " ".join(without_disclosures) if without_disclosures else None
    notes_without_quote = list(notes)
    if fx_note is not None:
        # R4c-5 (b): the applied-rate sentence only where the close it converts
        # was usable -- an unusable close converts nothing (the O-1 cell).
        if applied is None or priced:
            notes.append(fx_note)
        # R4c-5 (a): no applied-rate sentence without the quote's; a failed
        # conversion's sentence stays.
        if applied is None:
            notes_without_quote.append(fx_note)
    notes.extend(disclosures)
    notes_without_quote.extend(without_disclosures)

    context = PortfolioContext(
        symbol=symbol,
        total_equity_twd=equity,
        position_market_value_twd=market_value,
        position_cost_twd=cost,
        # The numerator is the valued book; it is only offered when there is a
        # denominator to divide it by. Without a reported net worth the field
        # stays absent and the cap behaves exactly as it did before FR-9
        # (AC-9.2) -- see the module docstring, rule 3.
        gross_exposure_twd=equity if net_worth is not None else None,
        net_worth=net_worth,
        book_fully_valued=fully_valued,
        quantity=quantity,
        close=close if priced and rate is not None else None,
        # ``close`` is ``None`` whenever ``rate`` is, so this 1.0 is never
        # applied to a foreign-currency amount; it only satisfies the field's
        # "must be a positive float" contract. Since X-3c a holding stored in a
        # currency other than its market's has no rate either, so the TWD
        # branch's 1.0 no longer meets a close quoted in another currency.
        fx_to_twd=rate if rate is not None else 1.0,
        atr=atr if priced and rate is not None else None,
        sector=sector,
        sector_market_value_twd=sector_market_value,
        sector_gap=sector_gap,
        kelly=kelly,
        # ADR-0022 Decision 1: classified once, here, per holding.
        unvalued=_unvalued_composition(groups, matched, sector),
        valued_unclassified_lots=_valued_unclassified(groups)[0],
    )
    return BookContext(
        context=context,
        held=bool(matched),
        summary=summary,
        scope="symbol",
        position_ids=[position.id for position in matched],
        currency=effective_currency,
        symbol_notes=tuple(notes),
        symbol_notes_without_quote=tuple(notes_without_quote),
        fx_rate=rate,
        fx_note=fx_note,
        fx_disclosure=fx_disclosure,
        fx_disclosure_without_quote=fx_disclosure_without_quote,
        price_withheld_note=price_withheld_note,
        disclosed_quote=disclosed_quote,
    )


def limits_fx_disclosures(book_level: BookContext, quotes: Sequence[FxQuote]) -> tuple[str, ...]:
    """The overview's FX source sentences, to follow its notes (task RK-4, R4-25).

    Two groups, each deduplicated by **source id** (risk S-1), the first ahead
    of the second (risk RK4-R5, RK4-C2):

    * G1 -- ``quotes``: the quotes applied under (A′) to the holdings that were
      actually compared on a cap reading the price or the ATR, in book order.
      Picking them is the caller's job (R4-23); this function trusts the list.
    * G2 -- ``book_level.valued_fx_sources``: every rate the valuator multiplied
      into the book's total (R4-24).

    A G2 source with the id of a G1 source is not repeated, whatever its
    sentence (RK4-C2): one id is one source. With ``k1``/``k2`` the number of
    distinct ids in G1/G2 (R4-26):

    * E0 -- ``k1 == 0``, ``k2 == 0``: ``()``, so a TWD book is unchanged (R4-27).
    * E1 -- ``k1 == 0``, ``k2 == 1``: :data:`FX_VALUATION_SCOPE_NOTE`, then
      the G2 sentence.
    * E2 -- ``k1 == 1``, G2 holds no other id: the G1 sentence alone.
    * E3 -- ``k1 == 1``, ``k2 == 1``, different ids: the G1 sentence, the G2
      sentence, then :data:`FX_MIXED_SOURCES_NOTE`.
    * E4 -- ``k1 >= 2`` or ``k2 >= 2``: ``()`` plus one WARNING (below).

    Quotes with no sentence are not counted, as in :func:`_fx_disclosures`; a
    quote applied under (A′) always has one.
    """
    if book_level.scope != "book":
        raise ValueError("the overview's FX sentences are stated about a book-scope context")
    first: list[tuple[str, str]] = []
    for quote in quotes:
        if quote.source_note and all(quote.source != seen for seen, _ in first):
            first.append((quote.source, quote.source_note))
    second: list[tuple[str, str]] = []
    for source, note in book_level.valued_fx_sources:
        if note and all(source != seen for seen, _ in second):
            second.append((source, note))
    if len(first) >= 2 or len(second) >= 2:
        # E4, option (α) (risk RK4-C1): all or nothing -- no G1 or G2 sentence,
        # no scope sentence, no bridge -- and one line so the occurrence is
        # seen (RK4-C1 (b)): pair and sorted source ids only, never a symbol,
        # an amount or a rate. Only here; E0 to E3 log nothing.
        # Re-review trigger (RK4-C1 (d)): back to risk-compliance once this
        # line first shows up in a production log, or once Bank of Taiwan
        # answers again (RK-2 condition (a)). Clause 3: also when ADR-0015 W11
        # (the cross-request FX rate cache) is wired -- a cache hit reports the
        # cached row's original source id, so rows written while Bank of Taiwan
        # answered can make E4 reachable even while it is blocked.
        offending = first if len(first) >= 2 else second
        pairs = sorted({quote.pair.strip().upper() for quote in quotes if quote.source_note})
        logger.warning(
            "fx quote sources differ across compared holdings: pair=%s sources=%s",
            ",".join(pairs) or "-",
            ",".join(sorted(source for source, _ in offending)),
        )
        return ()
    if not first:
        if not second:
            return ()
        return (FX_VALUATION_SCOPE_NOTE, second[0][1])
    if not second or second[0][0] == first[0][0]:
        return (first[0][1],)
    return (first[0][1], second[0][1], FX_MIXED_SOURCES_NOTE)


def _valued_rates(summary: PortfolioSummary, pair: str) -> list[FxInfo]:
    """The valuator's ``fx_now`` provenance on every row it multiplied into a figure.

    Only ``ok`` rows count (risk RK2-R1): an unvalued row may still carry the
    rate it looked up, but that rate reached no total, and a methodology
    sentence for it would describe a number nobody was shown (scenario 9).
    """
    wanted = pair.strip().upper()
    rates: list[FxInfo] = []
    for position in summary.positions:
        info = position.valuation.fx
        if (
            position.valuation.status == "ok"
            and info is not None
            and info.pair.strip().upper() == wanted
            and info.data_status is not DataStatus.UNAVAILABLE
        ):
            rates.append(info)
    return rates


def _fx_disclosures(applied: FxQuote, summary: PortfolioSummary) -> tuple[str, ...]:
    """Every source behind this context's converted figures, quote first (task RK-2).

    The applied quote converts the price and the ATR; the valuator's rate
    converts every holding's market value and so the equity every cap divides
    by. The two are separate lookups and may land on different sources, so
    both are disclosed: ``[quote, valuator]``, deduplicated by **source id**
    rather than by sentence (risk S-1 -- two sources sharing
    ``GENERIC_SOURCE_NOTE`` are still two). Sources with no sentence are not
    shown. :data:`FX_MIXED_SOURCES_NOTE` follows only when exactly two items
    from two different sources remain (RK2-T5): its wording says "兩項" and
    attributes them by position.

    Precondition: ``applied.source_note`` is not empty -- the caller only
    reaches here under (A′) (task RK-4, R4-11). ``shown[0][0] == applied.source``
    below is kept as defence in depth (R4-20): without it, a quote with no
    sentence would leave two valuator items and the bridge would attribute the
    first of them to the price and the ATR.
    """
    sources: list[tuple[str, str, str | None]] = [
        (applied.source, applied.source_note, applied.as_of)
    ]
    seen = {applied.source}
    for info in _valued_rates(summary, applied.pair):
        if info.source_note and info.source not in seen:
            seen.add(info.source)
            sources.append((info.source, info.source_note, info.as_of))
    if len(sources) > 1:
        # Observability only (risk RK2-R4): a mixed-source event, not a "Bank
        # of Taiwan is back" signal. Pair, source ids and rate dates only -- no
        # symbol, position, amount, quantity or rate.
        logger.warning(
            "fx sources differ within one context: pair=%s quote_source=%s quote_as_of=%s "
            "valuation_source=%s valuation_as_of=%s",
            applied.pair,
            sources[0][0],
            sources[0][2],
            sources[1][0],
            sources[1][2],
        )
    shown = [(source, note) for source, note, _ in sources if note]
    disclosures = [note for _, note in shown]
    if len(shown) == 2 and shown[0][0] != shown[1][0] and shown[0][0] == applied.source:
        disclosures.append(FX_MIXED_SOURCES_NOTE)
    return tuple(disclosures)


def _converted_by_valuator(position: SummaryPosition) -> bool:
    """Whether the valuator multiplied a stated rate into this lot's market value.

    Reads ``valuation.status`` and ``valuation.fx`` only -- never ``fx_open``
    and never the lot's currency or market (task RK-4, R4-12): since X-3c a lot
    whose currency is not its market's is ``insufficient_data`` with no
    ``FxInfo`` (KX-A2), so it can never qualify (RK4-R12, (R12-a)).
    """
    return (
        position.valuation.status == "ok"
        and position.valuation.fx is not None
        and position.valuation.fx.data_status is not DataStatus.UNAVAILABLE
        and position.valuation.fx.source_note != ""
    )


def _valuation_converted(matched: list[SummaryPosition]) -> bool:
    """(B) of task RK-4: at least one of this symbol's own lots was converted.

    Empty for a symbol not held, so a candidate never satisfies it.
    """
    return any(_converted_by_valuator(position) for position in matched)


def _valuation_disclosures(
    matched: list[SummaryPosition], summary: PortfolioSummary
) -> tuple[str, ...]:
    """:data:`FX_VALUATION_SCOPE_NOTE`, then the valuator's sentences (task RK-4, (B)).

    Takes no quote, by design (risk RK4-C3): nothing here can appear *because
    of* the quote. A sentence that is also the quote's appears once, as the
    valuator's, when both lookups landed on one source.

    The pairs are those of the lots that satisfied (B), in their first-seen
    order; for each, every ``ok`` row of the book with that pair contributes
    (:func:`_valued_rates`, the RK-2 set: the equity every cap divides by was
    converted with them too), deduplicated by **source id** (risk S-1) in
    summary order, sources with no sentence left out.
    :data:`FX_MIXED_SOURCES_NOTE` is never attached here (R4-13).
    """
    pairs: list[str] = []
    for position in matched:
        info = position.valuation.fx
        if _converted_by_valuator(position) and info is not None:
            pair = info.pair.strip().upper()
            if pair not in pairs:
                pairs.append(pair)
    seen: set[str] = set()
    sentences: list[str] = []
    for pair in pairs:
        for info in _valued_rates(summary, pair):
            if info.source_note and info.source not in seen:
                seen.add(info.source)
                sentences.append(info.source_note)
    return (FX_VALUATION_SCOPE_NOTE, *sentences)


def _log_unapplied_quote(
    currency: str | None, fx: FxQuote | None, summary: PortfolioSummary
) -> None:
    """Log scenario 2a: the quote had no rate while valued rows did use one.

    Nothing is disclosed for it here (R2-3: whether to is task RK-4's
    question); the line exists so how often it happens can be counted (risk
    S-4). Same content limits as the mixed-source line.
    """
    if fx is None or currency is None or currency.strip().upper() == "TWD":
        return
    if fx.pair.strip().upper() != f"{currency.strip().upper()}TWD":
        return
    if fx.rate is not None and fx.rate > 0.0:
        return
    rates = _valued_rates(summary, fx.pair)
    if not rates:
        return
    logger.warning(
        "fx quote unavailable while valued holdings used a rate: pair=%s quote_source=%s "
        "valuation_source=%s valuation_as_of=%s",
        fx.pair,
        fx.source,
        rates[0].source,
        rates[0].as_of,
    )


def _resolve_fx(
    currency: str | None, fx: FxQuote | None
) -> tuple[float | None, str | None, FxQuote | None]:
    """Instrument currency -> ``(rate, note, applied)``; ``rate`` is ``None`` if unusable.

    A TWD instrument (or a candidate with no currency at all) is already in the
    reporting currency and needs no quote. For every other currency the quote
    has to exist, be for the right pair, and carry a positive rate; anything
    else returns ``None`` with a sentence naming *which* input was missing, so
    "no price" and "no FX conversion" never look the same downstream.

    ``applied`` is ``fx`` itself on the one branch that converts with it and
    ``None`` on every other, including the TWD branch's 1.0 (task X-3 KX-10):
    it is what decides whether the quote's standing disclosure may be shown.
    """
    if currency is None or currency.strip().upper() == "TWD":
        return 1.0, None, None
    if fx is None:
        return None, NO_FX_QUOTE_NOTE.format(currency=currency), None

    expected = f"{currency.strip().upper()}TWD"
    if fx.pair.strip().upper() != expected:
        return (
            None,
            FX_PAIR_MISMATCH_NOTE.format(currency=currency, expected=expected, pair=fx.pair),
            None,
        )
    if fx.rate is None or fx.rate <= 0.0:
        return (
            None,
            FX_UNAVAILABLE_NOTE.format(
                currency=currency,
                pair=fx.pair,
                status=fx.status.value,
                source=fx.source,
                as_of=fx.as_of or "未知",
            ),
            None,
        )
    return (
        fx.rate,
        FX_APPLIED_NOTE.format(
            pair=fx.pair,
            rate=f"{fx.rate:g}",
            status=fx.status.value,
            source=fx.source,
            as_of=fx.as_of or "未知",
        ),
        fx,
    )
