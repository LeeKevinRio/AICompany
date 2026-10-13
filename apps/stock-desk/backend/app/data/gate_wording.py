"""Reader-facing sentences of the daily-bar admission and currency gate (ADR-0024 D-2, D-4, D-7).

Every sentence here was fixed verbatim by risk-compliance-officer and is the
*whole* ``reason`` of the answer that carries it (W-d, 風控 F9W-6): ``load_bars``
passes it through without ``NO_BARS_REASON`` and without
``PROVIDER_REASON_PREFIX``. Changing a character, the split between them, or
the order they are stated in goes back to review (F9W-16, F9W-29).

Only the equity path speaks: the index path refuses with no sentence of its
own (ADR-0024 D-4, 風控 F9W-9): nothing under ``app/services/index.py`` refers to
this module, and the index construction point passes ``wording=None``.

``{provider}`` is filled with the refusing adapter's ``source_id`` and nothing
else (F9W-3, C-14).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from app.data.interface import Market

#: W-a (US, alt-1): the symbol's shape is outside what the system asks about.
#: Only the service's admission, before layer 0, states it (F9W-7).
#: 風控核可文案,修改須重新送審(2026-10-12)
#: ``work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md``
#: (W-a alt-1; F9W-1, F9W-6, F9W-7, F9W-16)
SYMBOL_NOT_ADMITTED_REASON_US: Final = (
    "本系統只查詢這種形式的美股代號：1 至 5 個英文字母，可接單一字母的類別字尾（如 BRK.B）；"
    "此代號不在其內，未向任何來源查詢。帶其他字尾的代號可能是外國交易所的掛牌（價格單位未必是美元），"
    "也可能是特別股等美國商品，系統無法逐一分辨。"
)
#: W-b (TW, second sentence alt-2): digits followed by K.
#: Only the service's admission, before layer 0, states it (F9W-7).
#: 風控核可文案,修改須重新送審(2026-10-12)
#: ``work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md``
#: (W-b 第二句 alt-2; F9W-2, F9W-6, F9W-7, F9W-8, F9W-16)
SYMBOL_NOT_ADMITTED_REASON_TW: Final = (
    "此台股代號是「數字後接英文字母 K」的形式，本系統不處理這種形式，未向任何來源查詢。"
    "這類代號可能是以外幣計價的掛牌商品，價格單位未必是新台幣。"
)
#: W-c (US): a live rung's bars declare a unit that is not the US dollar.
#: 風控核可文案,修改須重新送審(2026-10-12)
#: ``work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md``
#: (W-c 美股; F9W-3, F9W-6, F9W-16)
UNIT_MISMATCH_REASON_US: Final = (
    "{provider} 這次回傳的日線，標示的價格單位不是美元（美股日線以美元為準），整段都不採用。"
)
#: W-c (TW): a live rung's bars declare a unit that is not the New Taiwan dollar.
#: 風控核可文案,修改須重新送審(2026-10-12)
#: ``work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md``
#: (W-c 台股; F9W-3, F9W-6, F9W-16)
UNIT_MISMATCH_REASON_TW: Final = (
    "{provider} 這次回傳的日線，標示的價格單位不是新台幣（台股日線以新台幣為準），整段都不採用。"
)
#: W-c' (US): a live rung's bars declare no unit at all.
#: 風控核可文案,修改須重新送審(2026-10-12)
#: ``work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md``
#: (W-c′ 美股; F9W-3, F9W-5, F9W-16)
UNIT_MISSING_REASON_US: Final = (
    "{provider} 這次回傳的日線沒有標示價格單位，無法確認是否為美元，整段都不採用。"
)
#: W-c' (TW): a live rung's bars declare no unit at all.
#: 風控核可文案,修改須重新送審(2026-10-12)
#: ``work/reviews/2026-10-12-F-9-原因句逐字審-F9W-1至F9W-16-風控.md``
#: (W-c′ 台股; F9W-3, F9W-5, F9W-16)
UNIT_MISSING_REASON_TW: Final = (
    "{provider} 這次回傳的日線沒有標示價格單位，無法確認是否為新台幣，整段都不採用。"
)
#: T-15: the cached rows of the series declare a unit that is not the market's,
#: or none at all; the whole cached series is not used. One constant for all
#: four cache paths -- layer 0, the degrade-to-cache rung, the cache-only read
#: and the incremental read-back (F9W-22) -- and at most once in a reason (C-30).
#: 風控核可文案,修改須重新送審(2026-10-12)
#: ``work/reviews/2026-10-12-F-9-第二批字面逐字審-F9W-17至F9W-29-風控.md``
#: (T-15 主案; F9W-22, F9W-27, F9W-29)
CACHE_UNIT_REJECTED_REASON: Final = (
    "本機快取中此標的的日線資料，標示的價格單位與市場所用的單位不同，或沒有標示價格單位，"
    "整段都不採用。"
)


@dataclass(frozen=True)
class GateWording:
    """The sentences one service states when its gate refuses an answer.

    Keyed by the market of the call (the sentence names the market's unit).
    """

    #: W-a (US) / W-b (TW): the admission refused the symbol.
    symbol_not_admitted: Mapping[Market, str]
    #: W-c, by market; ``{provider}`` is the refusing rung's ``source_id``.
    unit_mismatch: Mapping[Market, str]
    #: W-c', by market; ``{provider}`` likewise.
    unit_missing: Mapping[Market, str]
    #: T-15, the same for every market.
    cache_unit_rejected: str


#: The equity ladders' wording (TW and US).
EQUITY_GATE_WORDING: Final = GateWording(
    symbol_not_admitted=MappingProxyType(
        {"US": SYMBOL_NOT_ADMITTED_REASON_US, "TW": SYMBOL_NOT_ADMITTED_REASON_TW}
    ),
    unit_mismatch=MappingProxyType({"US": UNIT_MISMATCH_REASON_US, "TW": UNIT_MISMATCH_REASON_TW}),
    unit_missing=MappingProxyType({"US": UNIT_MISSING_REASON_US, "TW": UNIT_MISSING_REASON_TW}),
    cache_unit_rejected=CACHE_UNIT_REJECTED_REASON,
)
