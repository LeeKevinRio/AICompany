"""Standing, user-facing disclosures for each FX source.

Kept in a module with no dependency on the advice package so the valuation
layer (``app/portfolio/valuation.py``) can attach the note to every converted
figure without pulling ``app.advice`` into its import graph -- the playbook
reads the valuator, and 風控 R4 forbids the playbook from reaching the advice
engine (``tests/test_playbook_boundary.py``). ``app/services/fx.py`` re-exports
these names for its existing callers.
"""

from __future__ import annotations

from typing import Final

#: Emitted when no provider was wired in, or no rung of the ladder answered.
NO_PROVIDER_SOURCE: Final = "none"

#: Per-source standing disclosure, surfaced wherever the rate is used. Bank of
#: Taiwan publishes no single official daily close, so the adapter reports the
#: mid-point of the spot buy/sell pair -- a model value, not an official rate --
#: and its endpoint could not be verified against a live response in this
#: environment (see the ``app/data/providers/fx.py`` header and
#: ``tests/fixtures/README.md``). This text is user-facing on purpose (F-4).
SOURCE_NOTES: Final[dict[str, str]] = {
    "bank_of_taiwan": (
        "匯率為台灣銀行即期買賣中點的模型值，不是官方收盤匯率；"
        "該端點與 CSV 欄位格式未經本環境線上查證（verified=false）。"
    ),
    # ADR-0011: the FX ladder's backup rung. Yahoo Finance data, not Bank of
    # Taiwan's official mid-rate -- only reached when the primary source
    # declines (see ``app/data/providers/fx.py`` ``FxRateLadder``), and the
    # ladder always labels it ``DataStatus.BACKUP``, never ``FRESH``.
    # Fixed verbatim by risk-compliance-officer 2026-09-19 (VETO on the first
    # draft: the rate's own basis -- a Yahoo daily close, a different measure
    # from the Bank of Taiwan spot mid-point -- and the unverified ticker
    # convention were missing). Any change goes back to them.
    "yfinance_fx": (
        "匯率取自 Yahoo Finance 的每日收盤價（非台灣銀行官方牌告），"
        "為本次台灣銀行來源不可用時的備援；其口徑與台銀即期中價不同，"
        "換算結果可能與官方牌告有落差。該端點未公開文件化，"
        "幣別代號（如 TWD=X）與欄位格式均未經本環境線上查證（verified=false）。"
    ),
}

#: Used for any source without an entry above: says what is unknown, and does
#: not claim anything about the source's methodology.
GENERIC_SOURCE_NOTE: Final = (
    "此匯率來源的端點與欄位格式未經本環境線上查證（verified=false），"
    "其數值口徑（即期／收盤／中點）以來源文件為準。"
)


def source_note(source: str) -> str:
    """The standing disclosure for ``source``.

    ``none`` (no rung answered, or no provider wired) gets no note: a
    methodology statement about a source that did not supply the number
    would be a false disclosure (風控 2026-09-19 suggested 4).
    """
    if source == NO_PROVIDER_SOURCE:
        return ""
    return SOURCE_NOTES.get(source, GENERIC_SOURCE_NOTE)
