"""The closed list of TWSE industry categories a TW position may declare.

FR-12 needs a *classification*, not free text: the sector cap divides one
industry's market value by the book's, so two spellings of the same industry
would split a bucket and understate concentration. The values below are
therefore an enumeration the API validates against, offered to the UI by
``GET /api/positions/sectors`` so the dropdown and the validator can never
drift apart.

Which taxonomy, and why only TW: the PRD fixes TWSE's own industry categories
for the TW market (they are what TW data sources emit natively, and they are
what the user already reads on every TW quote page). US holdings have no place
in this list -- GICS and TWSE are different systems, and pasting a TWSE category
onto a US ticker would be a fabricated classification -- so a US position must
leave ``sector`` empty until the US taxonomy is decided (AC-12.6).

PROVENANCE NOTICE: this list was compiled from public knowledge of the TWSE
listed-company industry classification, and on 2026-08-12 was audited against
the official ``t187ap03_L`` dataset run locally by the CEO (see
``app.directory.sector_audit``): 32 of the names below matched the official
codes in use that day; 文化創意業/綜合企業/農業科技業/電子商務業 exist in the
official code table but currently have no listed company, and are kept by CEO
ruling; 存託憑證 (code 91) was added by the same ruling. The audit resolves
codes to names via ``app.directory.twse_sector_codes`` -- that mapping table,
not this file, owns the name-to-code relation. The two umbrella categories
(電子工業, 化學生技醫療) remain deliberately excluded: they contain the leaf
categories listed here, and allowing both levels would let one holding be
filed above another and make the sector totals incomparable (the official
data confirmed only leaf codes are ever emitted).
"""

from __future__ import annotations

from typing import Final

#: Every value ``Position.sector`` accepts for a TW holding, in TWSE's own
#: order (cement first, then food, ... , with the newer categories last).
TWSE_SECTORS: Final[tuple[str, ...]] = (
    "水泥工業",
    "食品工業",
    "塑膠工業",
    "紡織纖維",
    "電機機械",
    "電器電纜",
    "玻璃陶瓷",
    "造紙工業",
    "鋼鐵工業",
    "橡膠工業",
    "汽車工業",
    "建材營造業",
    "航運業",
    "觀光餐旅業",
    "金融保險業",
    "貿易百貨業",
    "綜合企業",
    "化學工業",
    "生技醫療業",
    "油電燃氣業",
    "半導體業",
    "電腦及週邊設備業",
    "光電業",
    "通信網路業",
    "電子零組件業",
    "電子通路業",
    "資訊服務業",
    "其他電子業",
    "文化創意業",
    "農業科技業",
    "電子商務業",
    "綠能環保業",
    "數位雲端業",
    "運動休閒業",
    "居家生活業",
    "其他業",
    # CEO ruling 2026-08-12 (work/dispatch/2026-08-12-產業清單覆核-CEO裁決.md):
    # code 91 is not a traditional industry, but TDR holdings do carry it as
    # their 產業別, so excluding it would leave such a position unclassifiable
    # in the sector-cap check. Kept last, mirroring TWSE's own ordering.
    "存託憑證",
)

_SECTOR_SET: Final[frozenset[str]] = frozenset(TWSE_SECTORS)

#: Rejection message shared by the API model and the CSV importer, so both
#: doors turn the same input down with the same sentence (the pattern
#: ``INDEX_SYMBOL_REJECTED_MESSAGE`` already set).
SECTOR_REJECTED_MESSAGE: Final = (
    "產業別必須是台灣證交所產業別清單中的其中一項（可由 "
    "GET /api/positions/sectors 取得完整清單），不接受自訂文字。"
)

#: Rejection message for a US holding carrying a TWSE category (AC-12.6).
SECTOR_US_REJECTED_MESSAGE: Final = (
    "美股持倉目前不可填產業別：台灣證交所產業別分類不適用於美股，"
    "美股的分類標準尚未定案；請留空，該部位的單一產業佔比上限會如實顯示無法評估。"
)


def is_valid_sector(value: str) -> bool:
    """Whether ``value`` is one of the enumerated TWSE categories."""
    return value in _SECTOR_SET
