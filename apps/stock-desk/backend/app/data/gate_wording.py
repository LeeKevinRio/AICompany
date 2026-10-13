"""Reader-facing sentences of the daily-bar currency gate (ADR-0024 D-2, D-7).

Every sentence here was fixed verbatim by risk-compliance-officer and is the
*whole* ``reason`` of the answer that carries it (W-d, 風控 F9W-6): ``load_bars``
passes it through without ``NO_BARS_REASON`` and without
``PROVIDER_REASON_PREFIX``. Changing a character, the split between them, or
the order they are stated in goes back to review (F9W-16, F9W-29).

Only the equity path speaks: the index path refuses with no sentence of its
own (ADR-0024 D-4, 風控 F9W-9), so nothing under ``app/services/index.py`` or
the index construction point refers to this module.

``{provider}`` is filled with the refusing adapter's ``source_id`` and nothing
else (F9W-3, C-14).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from app.data.interface import Market

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


@dataclass(frozen=True)
class GateWording:
    """The sentences one service states when its gate refuses an answer.

    Keyed by the market of the call (the sentence names the market's unit).
    """

    #: W-c, by market; ``{provider}`` is the refusing rung's ``source_id``.
    unit_mismatch: Mapping[Market, str]
    #: W-c', by market; ``{provider}`` likewise.
    unit_missing: Mapping[Market, str]


#: The equity ladders' wording (TW and US).
EQUITY_GATE_WORDING: Final = GateWording(
    unit_mismatch=MappingProxyType({"US": UNIT_MISMATCH_REASON_US, "TW": UNIT_MISMATCH_REASON_TW}),
    unit_missing=MappingProxyType({"US": UNIT_MISSING_REASON_US, "TW": UNIT_MISSING_REASON_TW}),
)
