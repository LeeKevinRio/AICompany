"""TWSE listed-company (上市) industry-category code -> Chinese name mapping.

## Provenance -- inferred-from-public-docs, NOT verified against TWSE's live
## API documentation or schema publication

CEO's first real ``python -m app.directory.sync --verify-sectors`` run
against production TWSE data (2026-08-12) confirmed the ``t187ap03_L``
endpoint and its ``公司代號``/``公司名稱``/``產業別`` field names (1095 rows
fetched successfully -- see ``app/directory/providers.py``'s "Sector-profile
endpoint" section for the updated confirmation note). That same run also
surfaced a schema assumption that turned out wrong: the ``產業別`` column
returns a **two-digit code** (33 distinct values observed: 01, 02, 03, 04,
05, 06, 08, 09, 10, 11, 12, 14, 15, 16, 17, 18, 20, 21, 22, 23, 24, 25, 26,
27, 28, 29, 30, 31, 35, 36, 37, 38, 91), not the Chinese industry name
``app.positions.sectors.TWSE_SECTORS`` originally assumed when the audit
tool's comparison logic was first written -- that earlier code-vs-name
mismatch is what made the previous run report "33 items all-miss vs 36
items all-miss" instead of a real diff.

The code -> name mapping below is compiled from public knowledge of TWSE's
standard listed-company industry classification code table (the same table
used to build every 上市 stock's quote-page industry label and TWSE's
official published sector indices). It is **not verified against a live
TWSE code-table document fetched from this environment** -- egress to
``openapi.twse.com.tw`` and TWSE's documentation domains is blocked here,
same limitation as the rest of this module's siblings (see
``app/directory/providers.py``'s module docstring) -- so treat this table as
*inferred*, version-dated below, and re-check it against TWSE's own
published code table once network access allows.

Version: compiled 2026-08-12, against TWSE's industry-category code table as
of that date. Codes are long-term stable but TWSE has added new categories
over time (e.g. 35/36/37/38 are newer additions), so this table should be
re-checked periodically rather than assumed permanent, and MUST be extended
(never guessed) whenever a real fetch surfaces a code not listed here.

## Naming convention

Where a code's official industry meaning has an unambiguous,
character-for-character match in ``app.positions.sectors.TWSE_SECTORS``,
the local spelling is used here verbatim, so ``app.directory.sector_audit``
treats it as a match instead of a spurious diff caused by two
different-but-equivalent strings for the same industry. Where no local
category matches (e.g. code ``91``, depository receipts, which is not an
industry at all), the official generic term is kept as-is -- that
intentionally surfaces as an "official has it, local list does not" finding
for a human to decide on, not something this module silently resolves.

Codes NOT in this table are deliberately NOT guessed at: they must surface
as ``UNKNOWN_CODE`` findings from ``app.directory.sector_audit.compare_sectors``
for a human to confirm and add here, per the "no silent invention of
unverified data" rule in ``.claude/skills/data-source-integration/SKILL.md``.
"""

from __future__ import annotations

from typing import Final

#: TWSE listed-company (上市) 產業別 code -> Chinese industry name.
#: See module docstring for provenance/version. Keys are the exact
#: two-digit strings TWSE's ``t187ap03_L`` dataset uses (zero-padded,
#: e.g. ``"01"`` not ``"1"``).
TWSE_SECTOR_CODE_TO_NAME: Final[dict[str, str]] = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "14": "建材營造業",
    "15": "航運業",
    "16": "觀光餐旅業",
    "17": "金融保險業",
    "18": "貿易百貨業",
    "20": "其他業",
    "21": "化學工業",
    "22": "生技醫療業",
    "23": "油電燃氣業",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    # 32-34 were not among the 33 codes CEO's 2026-08-12 run observed, but
    # they are the same publicly documented code table's leaf categories
    # that correspond 1:1 to three TWSE_SECTORS entries -- kept here (rather
    # than left out) so a future run that *does* see them resolves instead
    # of surfacing a spurious UNKNOWN_CODE for a category this table already
    # knows about.
    "32": "文化創意業",
    "33": "農業科技業",
    "34": "電子商務業",
    "35": "綠能環保業",
    "36": "數位雲端業",
    "37": "運動休閒業",
    "38": "居家生活業",
    "91": "存託憑證",
}

#: The 33 codes CEO's first real ``--verify-sectors`` run against production
#: TWSE data observed (2026-08-12). Kept here (rather than only in the test
#: file) so ``tests/test_twse_sector_codes.py`` can assert "every code CEO
#: actually saw resolves" without hand-retyping the list, and so this
#: module documents exactly what has been *observed* versus what is merely
#: *believed* from public docs (the 32/33/34 entries above are the latter).
CEO_OBSERVED_CODES: Final[frozenset[str]] = frozenset(
    {
        "01",
        "02",
        "03",
        "04",
        "05",
        "06",
        "08",
        "09",
        "10",
        "11",
        "12",
        "14",
        "15",
        "16",
        "17",
        "18",
        "20",
        "21",
        "22",
        "23",
        "24",
        "25",
        "26",
        "27",
        "28",
        "29",
        "30",
        "31",
        "35",
        "36",
        "37",
        "38",
        "91",
    }
)


def resolve_sector_name(code: str) -> str | None:
    """Map a TWSE 產業別 code to its Chinese name, or ``None`` if unknown.

    Returning ``None`` instead of falling back to the raw code lets callers
    (``app.directory.sector_audit.compare_sectors``) surface an explicit
    "code not in table" finding rather than silently comparing a raw code
    string against Chinese industry names, which would always miss and look
    like a real taxonomy gap instead of an incomplete mapping table.
    """
    return TWSE_SECTOR_CODE_TO_NAME.get(code)
