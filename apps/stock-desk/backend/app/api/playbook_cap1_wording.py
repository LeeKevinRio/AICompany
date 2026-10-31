"""The 排程台 × 第 1 條 disclosure (N-155): every approved sentence, in one file.

CEO #68 (2026-10-28) ruled that cap 1 (單一標的佔比上限) does not constrain the
排程台: its share counts come from the user's rule set alone, and the conflict is
disclosed instead of reconciled. This module holds that disclosure -- the title,
sentences ① to ④ and the five 讀取失敗／無法算出 replacements (①-缺, ①-缺b,
①-缺nb, ②-缺, ③-缺) -- exactly as 「風控 2026-10-28 #68 裁決（D-2 修訂／N-155
揭露規格）」, its follow-up (``2026-10-28-#68裁決補充-R4解讀與出貨方式-風控.md``
第 4 節) and 「風控 2026-10-28 #68 裁決補充二（N-155 交件已知限制 2～5）」 fixed them,
plus ②-預設 from 「風控 2026-10-29 N-156 字面定稿與表態」 第 5 項 (P2), and the one
function that fills them in. ADR-0031 (CEO #69) is the architecture; ADR-0032
(CEO #74) replaces C-4's signature with :class:`Cap1Reading`.

**Why this module sits in ``app/api`` and imports nothing from ``app``**
(ADR-0031 C-1, PD-1): the disclosure states a cap-1 value, and the settings
package that holds it imports ``app.advice`` itself. A copy under
``app/playbook`` would put the 排程台 one import away from the advice engine,
which 風控 R4 forbids outright (``tests/test_playbook_boundary.py``). The value
therefore arrives as an argument, assembled by ``app/api/playbook.py`` -- the
same arrangement ``app/api/kelly_wording.py`` uses (ADR-0006 D-8).

House rules, all of them non-negotiable:

* **逐字**. Each string below was approved character by character, punctuation
  included. Re-wording, splitting, merging, truncating or re-ordering any of
  them makes the approval lapse; ``tests/test_api_playbook_cap1_disclosure.py``
  retypes every one, so a drift fails the build instead of reaching a user.
* **Every number is filled in here**, already formatted, so a client renders
  whole sentences and never multiplies, divides or appends a ``%`` (AV-13).
  The slots never carry 「約」: the sentences already say it.
* **Nothing is compared.** Whether the per-target share is above, at or below
  cap 1 is not computed and not returned: the two percentages have different
  denominators, so a comparison would be false precision, and the disclosure
  is shown unconditionally (補充裁定 第 2 節).
* **A missing value is described, never replaced.** No default (10% or any
  other) stands in for a cap-1 value that could not be read, no raw
  ``n_targets`` or ``batches_per_target`` of zero or below is written into a
  sentence, and every pct field is ``None`` rather than ``0`` when it cannot be
  computed or is not stated (AV-16).
* **Rendered on demand, stored nowhere** (AV-11, H2): no table, no directive
  log, no ``RuleParams`` field.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

#: 區塊標題 (補充裁定 第 3 節, required). Sent by the backend so a client cannot
#: hard-code a heading carrying a number of its own.
TITLE: Final = "排程台每檔規模與第 1 條上限"

#: ① 每檔規模算式.
LINE_PER_TARGET: Final = (
    "依此規則集的參數（部署比例 {deploy_ratio_pct}、{n_targets} 檔均分、每檔分 "
    "{batches_per_target} 批），每檔標的的預定投入金額為 TOTAL_DEPLOY ÷ {n_targets}，"
    "約為計算 TOTAL_DEPLOY 當時排程台總資產（含現金）的 {per_target_pct}；實際股數依各批"
    "進場時的收盤價換算，實際成本與日後市值的佔比可能與此數不同。"
)

#: ①-缺: ``n_targets`` is not a positive integer, so no share can be computed.
LINE_PER_TARGET_UNAVAILABLE: Final = (
    "此規則集的每檔規模無法由目前參數算出（標的檔數 n_targets 不是正整數），本區塊不陳述每檔佔比。"
)

#: ①-缺b: only ``batches_per_target`` is not a positive integer. No batch would
#: be created (``PlaybookStore.ensure_batches``), so neither the per-target
#: amount nor its share is stated (補充裁定二 第 1 項).
LINE_PER_TARGET_NO_BATCHES: Final = (
    "此規則集的每檔批數 batches_per_target 不是正整數，本區塊不陳述每檔規模與每檔佔比。"
)

#: ①-缺nb: neither ``n_targets`` nor ``batches_per_target`` is a positive integer.
LINE_PER_TARGET_UNAVAILABLE_NO_BATCHES: Final = (
    "此規則集的每檔規模無法由目前參數算出（標的檔數 n_targets 與每檔批數 batches_per_target "
    "都不是正整數），本區塊不陳述每檔佔比。"
)

#: ② 第 1 條目前設定值與其分母.
LINE_CAP1: Final = (
    "第 1 條・單一標的佔比上限目前設定為 {cap1_pct}，分母是庫存的已估值部位市值（不含現金，"
    "即設定頁所稱的「總資產」）。排程台與庫存是兩套獨立帳冊，上述兩個百分比的分母不同，"
    "不能直接比較大小。"
)

#: ②-預設: the cap-1 value read is the default, because the stored risk budget
#: failed validation (P2, 「風控 2026-10-29 N-156 字面定稿與表態」 第 5 項). Like
#: ②-缺 it carries no remedy; unlike it, the value is stated -- the one that was
#: actually loaded, never a constant.
LINE_CAP1_DEFAULT: Final = (
    "第 1 條・單一標的佔比上限目前使用預設值 {cap1_pct}：設定頁的風險預算原本存的內容沒有通過驗證，"
    "這個值不是原本存的內容；其分母是庫存的已估值部位市值（不含現金，即設定頁所稱的「總資產」）。"
    "排程台與庫存是兩套獨立帳冊，上述兩個百分比的分母不同，不能直接比較大小。"
)

#: ②-缺: the cap-1 setting could not be read (R4-4).
LINE_CAP1_UNREADABLE: Final = (
    "第 1 條・單一標的佔比上限的目前設定值讀取失敗；其分母是庫存的已估值部位市值（不含現金，"
    "即設定頁所稱的「總資產」）。排程台與庫存是兩套獨立帳冊，兩者的分母不同，"
    "不能直接比較大小。"
)

#: ③ 以庫存分母計的條件例示 (1 ÷ n_targets), kept by the follow-up ruling.
LINE_BOOK_EXAMPLE: Final = (
    "如果你也把排程台的持股記入庫存，第 1 條會以庫存的分母計算這些持股的佔比：例如庫存只有"
    "排程台的 {n_targets} 檔且各檔市值相同時，每檔約佔 {per_target_book_pct}；達到或超過"
    "第 1 條設定值時，個股頁會顯示該檔已達或超過上限。"
)

#: ③-缺: same sentence without the example, which needs a positive ``n_targets``.
LINE_BOOK_EXAMPLE_UNAVAILABLE: Final = (
    "如果你也把排程台的持股記入庫存，第 1 條會以庫存的分母計算這些持股的佔比；達到或超過"
    "第 1 條設定值時，個股頁會顯示該檔已達或超過上限。"
)

#: ④ 互不干涉. Never replaced, whatever is missing.
LINE_INDEPENDENCE: Final = (
    "排程台計算股數時不讀取第 1 條或其他任何一條風險上限的設定，也不會因這些上限調整任何一批的"
    "股數；兩邊各自計算，本系統不會自動調和兩者的結果。"
)

_ONE_PLACE: Final = Decimal("0.1")


@dataclass(frozen=True)
class Cap1Reading:
    """What :func:`app.api.deps.get_cap1_reading` read for cap 1 (ADR-0032 K-9).

    ``weight`` is the cap-1 value in force, or ``None`` when it could not be
    read. ``from_default`` is whether that value is the default because the
    stored risk budget failed validation -- taken from the settings layer's one
    read, never judged here or in the router. A failed read is never a
    fallback (ADR-0032 延伸 7): ``weight is None`` forces ``from_default`` to be
    ``False``, and constructing anything else is refused.

    The router hands this to :func:`compose` unchanged and may not branch on,
    compare, compute with or log it (R4-1, extended to ``from_default`` by K-9).
    """

    weight: Decimal | None
    from_default: bool

    def __post_init__(self) -> None:
        if self.weight is None and self.from_default:
            raise ValueError("an unreadable cap-1 value is not a fallback to the default")


class PlaybookCap1Disclosure(BaseModel):
    """The rendered disclosure carried by ``/today``, ``/rule-set`` and ``/confirm-rules``.

    Holds facts and sentences only -- no comparison result, flag or status
    (ADR-0031 C-2, PD-6): whether it is shown never depends on the numbers.
    """

    model_config = ConfigDict(frozen=True)

    #: :data:`TITLE`, verbatim.
    title: str
    #: Sentences ① to ④ in their fixed order, numbers already filled in; each
    #: missing value swaps in its own 讀取失敗 sentence. Never empty.
    lines: list[str] = Field(min_length=1)
    #: ``RuleParams.version`` of the parameter set the numbers came from, for
    #: reconciliation against the same response only (B-3). Not for display.
    #: On 待確認規則集 this is the version in force (the set a confirmation
    #: would adopt), while ``/today``'s top-level ``rules_version`` is ``0``
    #: ("no user rule was evaluated today"): the two mean different things and
    #: must never be reconciled against each other (補充裁定二 第 4 項).
    rules_version: int
    #: deploy_ratio ÷ n_targets as a percentage (``"14%"``); ``None`` whenever
    #: sentence ① is any of its 缺 variants (n_targets or batches_per_target not
    #: positive), so the field never states what the sentence does not.
    per_target_pct: str | None
    #: The cap-1 setting as a percentage (``"10%"``); ``None`` when unreadable.
    cap1_pct: str | None
    #: 1 ÷ n_targets as a percentage (``"20%"``), the figure sentence ③ uses;
    #: ``None`` when ``n_targets`` is not positive.
    per_target_book_pct: str | None


def format_pct(ratio: Decimal) -> str:
    """``ratio`` as the percentage the disclosure prints (``0.14`` -> ``"14%"``).

    The follow-up ruling's rule (ADR-0031 C-3): ``Decimal`` arithmetic,
    ROUND_HALF_UP to one decimal place, a trailing ``.0`` dropped, then ``%``.
    """
    text = format((ratio * 100).quantize(_ONE_PLACE, rounding=ROUND_HALF_UP), "f")
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text}%"


def compose(
    *,
    rules_version: int,
    deploy_ratio: Decimal,
    n_targets: int,
    batches_per_target: int,
    deploy_ratio_pct: str,
    cap1_reading: Cap1Reading,
) -> PlaybookCap1Disclosure:
    """Fill the approved sentences with one parameter version and the cap-1 setting.

    Every argument but the cap-1 value is read off the ``RuleParams`` the same
    response actually used; ``deploy_ratio_pct`` is that version's ratio as the
    response already writes it (``"70%"``). ``cap1_reading`` is the cap-1 value
    in force and whether it is the default (:class:`Cap1Reading`).

    The cap-1 value is only formatted into sentence ②. Nothing here compares it
    with anything, and the missing-value branches are independent: sentence ①
    depends on both ``n_targets`` and ``batches_per_target`` (補充裁定二 第 1 項:
    four cases, one sentence each), sentence ③ on ``n_targets`` alone, ② on the
    cap-1 reading alone, and ④ is never replaced.

    Sentence ② is one of three, in this order of precedence (ADR-0032 延伸 2):
    ②-缺 when the value could not be read, ②-預設 when it is the default
    standing in for a stored budget that failed validation, ② otherwise.
    """
    targets_ok = n_targets > 0
    batches_ok = batches_per_target > 0

    per_target_pct: str | None = None
    if targets_ok and batches_ok:
        per_target_pct = format_pct(deploy_ratio / n_targets)
        line_per_target = LINE_PER_TARGET.format(
            deploy_ratio_pct=deploy_ratio_pct,
            n_targets=n_targets,
            batches_per_target=batches_per_target,
            per_target_pct=per_target_pct,
        )
    elif batches_ok:
        line_per_target = LINE_PER_TARGET_UNAVAILABLE
    elif targets_ok:
        line_per_target = LINE_PER_TARGET_NO_BATCHES
    else:
        line_per_target = LINE_PER_TARGET_UNAVAILABLE_NO_BATCHES

    per_target_book_pct: str | None = None
    if targets_ok:
        per_target_book_pct = format_pct(Decimal(1) / n_targets)
        line_book = LINE_BOOK_EXAMPLE.format(
            n_targets=n_targets, per_target_book_pct=per_target_book_pct
        )
    else:
        line_book = LINE_BOOK_EXAMPLE_UNAVAILABLE

    weight = cap1_reading.weight
    if weight is None:
        cap1_pct: str | None = None
        line_cap1 = LINE_CAP1_UNREADABLE
    elif cap1_reading.from_default:
        cap1_pct = format_pct(weight)
        line_cap1 = LINE_CAP1_DEFAULT.format(cap1_pct=cap1_pct)
    else:
        cap1_pct = format_pct(weight)
        line_cap1 = LINE_CAP1.format(cap1_pct=cap1_pct)

    return PlaybookCap1Disclosure(
        title=TITLE,
        lines=[line_per_target, line_cap1, line_book, LINE_INDEPENDENCE],
        rules_version=rules_version,
        per_target_pct=per_target_pct,
        cap1_pct=cap1_pct,
        per_target_book_pct=per_target_book_pct,
    )
