"""Every sentence that discloses a settings fallback (N-156), in one file.

A stored settings section that fails validation is served with its defaults
(:meth:`app.settings.store.SettingsStore.load_with_status`). This module holds
what the user is told about that -- the settings-page block (F-1 ~ F-7), the
marker under each section heading, the short sentence of the risk-cap lists
(N-1 / N-2 / N-3), the line beside cap 5's effective value on the Kelly
screen, the overwrite confirmation panels, the 409 refusal and the
partial-save sentence -- exactly as 「風控 2026-10-29 N-156 字面定稿與表態」 fixed
them, and the functions that pick and fill them. ADR-0032 (CEO #74) is the
architecture (Decision 2, K-6/K-7).

House rules, all of them non-negotiable:

* **逐字**. Each string was approved character by character, punctuation
  included. ``tests/test_settings_fallback_wording.py`` retypes every one and
  runs the forbidden-term scans over them.
* **One copy.** Routers pass what these functions return through unchanged;
  the front end renders it and derives nothing about the fallback state from
  the settings values (K-6).
* **The backend chooses every branch and fills every slot.** ``{section_names}``
  is always built from :data:`app.settings.migrations.CAP1_SECTION_NAMES`
  joined by :data:`app.settings.migrations.SECTION_NAME_SEPARATOR` (I-4), in
  ``_SECTIONS`` order; never the internal key.
* **Nothing to say is ``None``**, never an empty string (K-7).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

from app.settings.migrations import CAP1_SECTION_NAMES, SECTION_NAME_SEPARATOR

#: The order every list of sections is written in (``_SECTIONS`` order). Kept
#: here so the copy needs nothing from the store; a test pins the two together.
SECTION_ORDER: Final[tuple[str, ...]] = ("risk_budget", "cost_model", "alerts", "net_worth")

#: The sections ``SettingsForm`` saves; ``net_worth`` has its own form and panel.
FORM_SECTIONS: Final[tuple[str, ...]] = ("risk_budget", "cost_model", "alerts")

# --- 1. 設定頁頁首區塊 -------------------------------------------------------------

NOTICE_TITLE: Final = "部分設定沒有通過驗證，目前使用預設值"

#: When an item of the settings-page block is part of it: ``always``, or only
#: while the named section is a fallback section.
ItemShown = Literal["always", "risk_budget", "alerts", "net_worth"]


@dataclass(frozen=True)
class NoticeItemCopy:
    """One「標籤｜正文」item of the settings-page block."""

    label: str
    #: A ``str.format`` template; ``{section_names}`` is the only slot.
    body: str
    shown: ItemShown


NOTICE_ITEMS: Final[tuple[NoticeItemCopy, ...]] = (
    # F-1
    NoticeItemCopy(
        "發生了什麼",
        "{section_names}原本存的內容沒有通過驗證，系統目前改用這些區段的預設值。"
        "本頁這些區段顯示的也是預設值，不是原本存的內容。",
        "always",
    ),
    # F-2
    NoticeItemCopy(
        "原本存的內容",
        "原本存的內容仍留在系統裡，你儲存其他區段時不會改動它；但本頁無法顯示，也無法還原。",
        "always",
    ),
    # F-3. Rests on CEO #72 (E2) and on the reduce range and cap 4 being
    # computed from the budget (風控 第 1 項 F-3 的理由). Reviewed again once
    # 5-K lands (第 9 項 (d)).
    NoticeItemCopy(
        "加碼結論",
        "風險預算使用預設值期間，各條風險上限都依預設值判定，可能比你原本的設定寬，"
        "也可能比較嚴。這段期間個股頁的規則結論為加碼時一律改為觀望，不提供買進股數；"
        "減碼與停損參考照常提供，其中用到風險上限的判定與股數區間同樣依預設值計算。",
        "risk_budget",
    ),
    # F-4. Rests on CEO #73 (A-1 照常) and on AlertSettings defaulting to
    # enabled=True, notify_webhooks=True; if either default changes, this item
    # and the alerts marker go back to risk-compliance (DL-8).
    NoticeItemCopy(
        "警示與推播",
        "警示排程使用預設值期間，系統照常評估警示，觸發時會推送至已設定的 webhook；"
        "若你原本關閉了評估或推播，目前仍會評估並推送。",
        "alerts",
    ),
    # F-5
    NoticeItemCopy(
        "帳戶總淨值",
        "帳戶總淨值使用預設值期間，系統視為沒有帳戶總淨值，第 3 條總曝險上限無法評估；"
        "這不代表你沒有輸入過，也不代表這條上限已通過。",
        "net_worth",
    ),
    # F-6
    NoticeItemCopy(
        "怎麼恢復",
        "在該區段儲存時確認覆寫，系統就改用你這次存的內容。確認覆寫後，原本存的內容會被取代，"
        "系統內不會保留。",
        "always",
    ),
    # F-7
    NoticeItemCopy(
        "檢查時點",
        "每次讀取設定時都會重新檢查；系統沒有記錄這個狀態從何時開始。",
        "always",
    ),
)

#: The line directly under each fallback section's h2 (``section_markers``).
#: The ``cost_model`` one rests on the stored rates being read by the backtest
#: alone (DL-9: ``app/api/backtest.py``); another reader sends it back to
#: risk-compliance. The ``alerts`` one rests on the same defaults as F-4.
SECTION_MARKERS: Final[dict[str, str]] = {
    "risk_budget": (
        "本區段目前顯示與使用的是預設值，不是原本存的內容（原本存的內容沒有通過驗證）。"
        "在你確認覆寫本區段之前，個股頁的規則結論為加碼時一律改為觀望，不提供買進股數。"
    ),
    "cost_model": (
        "本區段目前顯示與使用的是預設值，不是原本存的內容（原本存的內容沒有通過驗證）。"
        "回測沒有另外指定費率時，會用這些預設費率計算。"
    ),
    "alerts": (
        "本區段目前顯示與使用的是預設值，不是原本存的內容（原本存的內容沒有通過驗證）。"
        "警示排程目前照常評估，觸發時會推送至已設定的 webhook。"
    ),
    "net_worth": (
        "本區段原本存的內容沒有通過驗證，本頁無法顯示；系統目前視為沒有帳戶總淨值，"
        "第 3 條總曝險上限無法評估。這不代表你沒有輸入過。"
    ),
}

# --- 2. 建議端與儀表的短句 settings_fallback_notice ------------------------------------

#: N-1: only ``risk_budget`` fell back.
RISK_NOTICE_BUDGET: Final = (
    "風險預算原本存的內容沒有通過驗證，目前改用預設值，各條風險上限都依預設值判定，"
    "可能比你原本的設定寬，也可能比較嚴。在設定頁確認覆寫風險預算之前，規則結論為加碼時"
    "一律改為觀望，不提供買進股數；減碼與停損參考照常提供，其中用到風險上限的判定與股數區間"
    "同樣依預設值計算。詳見設定頁。"
)
#: N-2: only ``net_worth`` fell back.
RISK_NOTICE_NET_WORTH: Final = (
    "帳戶總淨值原本存的內容沒有通過驗證，系統目前視為沒有帳戶總淨值，第 3 條總曝險上限因此"
    "無法評估；這不代表你沒有輸入過，也不代表這條上限已通過。詳見設定頁。"
)
#: N-3: both fell back. A sentence of its own -- never N-1 followed by N-2.
RISK_NOTICE_BOTH: Final = (
    "風險預算與帳戶總淨值原本存的內容都沒有通過驗證，目前改用預設值：各條風險上限都依預設值"
    "判定，可能比你原本的設定寬，也可能比較嚴；系統也視為沒有帳戶總淨值，第 3 條總曝險上限"
    "因此無法評估，這不代表你沒有輸入過，也不代表這條上限已通過。在設定頁確認覆寫風險預算"
    "之前，規則結論為加碼時一律改為觀望，不提供買進股數；減碼與停損參考照常提供，其中用到"
    "風險上限的判定與股數區間同樣依預設值計算。詳見設定頁。"
)

# --- 4. Kelly 第 5 條數值旁 ------------------------------------------------------------

KELLY_EFFECTIVE_CAP_NOTICE: Final = (
    "此數值依預設的風險預算算出，不是依你的設定：風險預算原本存的內容沒有通過驗證，"
    "目前改用預設值。詳見設定頁頁首的說明。"
)

# --- 6. S3 覆寫確認面板、409、部分儲存 ---------------------------------------------------

OVERWRITE_PANEL_TITLE: Final = "這些區段目前使用預設值"
#: P-1, both versions.
OVERWRITE_PANEL_WHAT: Final = (
    "{section_names}原本存的內容沒有通過驗證，本頁顯示的是預設值，不是原本存的內容。"
)
#: P-2, ``SettingsForm`` version.
OVERWRITE_PANEL_FORM_EFFECT: Final = (
    "勾選覆寫的區段，會改存為本頁目前的數值；原本存的內容會被取代，系統內不會保留，"
    "也無法從本頁還原。沒有勾選的區段不會寫入，你在本頁對它們做的修改也不會儲存。"
)
#: P-3, only when the panel covers ``risk_budget``.
OVERWRITE_PANEL_LOOSENING_CHECK: Final = (
    "風險預算的放寬確認，比較的是本頁顯示的預設值，不是原本存的內容；原本存的值本頁無法得知，"
    "所以你存的值即使比原本寬，系統也可能不會提醒。"
)
#: P-4, only when the panel covers ``risk_budget``.
OVERWRITE_PANEL_BUDGET_EFFECT: Final = (
    "覆寫風險預算後，各條風險上限改依你這次存的值判定，個股頁的加碼結論恢復依規則判定。"
)
#: The per-section checkbox, unchecked by default.
OVERWRITE_CHECKBOX_LABEL: Final = "覆寫「{section_name}」"
OVERWRITE_FORM_CONFIRM_LABEL: Final = "儲存"
OVERWRITE_CANCEL_LABEL: Final = "取消，不儲存"
#: P-2b, ``NetWorthSection`` version.
OVERWRITE_PANEL_NET_WORTH_EFFECT: Final = (
    "確認覆寫後，帳戶總淨值會改存為你這次輸入的數值；原本存的內容會被取代，系統內不會保留，"
    "也無法從本頁還原。"
)
OVERWRITE_NET_WORTH_CONFIRM_LABEL: Final = "確認覆寫並儲存"

#: The 409 ``detail``: true only because a refused write writes no section.
OVERWRITE_REQUIRED_DETAIL: Final = (
    "沒有寫入任何設定：{section_names}原本存的內容沒有通過驗證，要寫入這些區段必須先確認覆寫。"
)

#: Replaces「設定已儲存。」when fallback sections were left unwritten.
PARTIAL_SAVE_NOTICE: Final = "設定已儲存。{section_names}沒有寫入，仍使用預設值。"

#: The「全未寫入」variant (「風控 2026-10-29 N-156 K-15 正式核對與裁示」 二-4 (b)): the
#: request carried no section at all, so nothing the user sent was stored and
#: 「設定已儲存。」 would be a false success.
NOTHING_SAVED_NOTICE: Final = "沒有儲存任何變更：{section_names}沒有寫入，仍使用預設值。"


# --- Response shapes ---------------------------------------------------------------


class FallbackNoticeItemView(BaseModel):
    """One「標籤｜正文」item, already filled."""

    model_config = ConfigDict(frozen=True)

    label: str
    body: str


class FallbackNoticeView(BaseModel):
    """The settings-page header block: never inside a ``<details>``, never closable."""

    model_config = ConfigDict(frozen=True)

    title: str
    items: list[FallbackNoticeItemView]


class OverwriteCheckboxView(BaseModel):
    """One per-section checkbox of the form panel; unchecked by default."""

    model_config = ConfigDict(frozen=True)

    section: str
    label: str


class OverwritePanelView(BaseModel):
    """A confirmation panel shown before saving over fallback sections (W-2).

    ``paragraphs`` are in display order. ``checkboxes`` is empty on the
    net-worth panel, whose confirm button is itself the confirmation.
    """

    model_config = ConfigDict(frozen=True)

    #: The fallback sections this panel covers, in ``_SECTIONS`` order.
    sections: list[str]
    title: str
    paragraphs: list[str]
    checkboxes: list[OverwriteCheckboxView]
    confirm_label: str
    cancel_label: str


class SettingsFallbackView(BaseModel):
    """``settings_fallback`` of ``GET``/``PUT /api/settings`` (ADR-0032 Decision 2).

    ``None`` on the response when no section fell back; never an empty block.
    """

    model_config = ConfigDict(frozen=True)

    #: The fallback sections, in ``_SECTIONS`` order. The only input the page
    #: may branch on for anything fallback-related (K-6).
    sections: list[str]
    notice: FallbackNoticeView
    #: section id -> the line under that section's h2; fallback sections only.
    section_markers: dict[str, str]
    #: The ``SettingsForm`` panel, when any of its three sections fell back.
    form_overwrite_panel: OverwritePanelView | None
    #: The ``NetWorthSection`` panel, when ``net_worth`` fell back.
    net_worth_overwrite_panel: OverwritePanelView | None


# --- Selection ---------------------------------------------------------------------


def _ordered(sections: Iterable[str]) -> tuple[str, ...]:
    wanted = set(sections)
    unknown = wanted - set(SECTION_ORDER)
    if unknown:
        raise KeyError(f"unknown settings sections: {sorted(unknown)}")
    return tuple(name for name in SECTION_ORDER if name in wanted)


def section_names(sections: Iterable[str]) -> str:
    """``{section_names}``: the h2 names, ``_SECTIONS`` order, joined by「、」(I-4)."""
    return SECTION_NAME_SEPARATOR.join(CAP1_SECTION_NAMES[name] for name in _ordered(sections))


def _form_panel(fallback: tuple[str, ...]) -> OverwritePanelView | None:
    covered = tuple(name for name in fallback if name in FORM_SECTIONS)
    if not covered:
        return None
    paragraphs = [
        OVERWRITE_PANEL_WHAT.format(section_names=section_names(covered)),
        OVERWRITE_PANEL_FORM_EFFECT,
    ]
    if "risk_budget" in covered:
        paragraphs += [OVERWRITE_PANEL_LOOSENING_CHECK, OVERWRITE_PANEL_BUDGET_EFFECT]
    return OverwritePanelView(
        sections=list(covered),
        title=OVERWRITE_PANEL_TITLE,
        paragraphs=paragraphs,
        checkboxes=[
            OverwriteCheckboxView(
                section=name,
                label=OVERWRITE_CHECKBOX_LABEL.format(section_name=CAP1_SECTION_NAMES[name]),
            )
            for name in covered
        ],
        confirm_label=OVERWRITE_FORM_CONFIRM_LABEL,
        cancel_label=OVERWRITE_CANCEL_LABEL,
    )


def _net_worth_panel(fallback: tuple[str, ...]) -> OverwritePanelView | None:
    if "net_worth" not in fallback:
        return None
    return OverwritePanelView(
        sections=["net_worth"],
        title=OVERWRITE_PANEL_TITLE,
        paragraphs=[
            OVERWRITE_PANEL_WHAT.format(section_names=section_names(("net_worth",))),
            OVERWRITE_PANEL_NET_WORTH_EFFECT,
        ],
        checkboxes=[],
        confirm_label=OVERWRITE_NET_WORTH_CONFIRM_LABEL,
        cancel_label=OVERWRITE_CANCEL_LABEL,
    )


def settings_fallback(fallback_sections: Iterable[str]) -> SettingsFallbackView | None:
    """The settings-page disclosure for these fallback sections, or ``None``."""
    fallback = _ordered(fallback_sections)
    if not fallback:
        return None
    names = section_names(fallback)
    return SettingsFallbackView(
        sections=list(fallback),
        notice=FallbackNoticeView(
            title=NOTICE_TITLE,
            items=[
                FallbackNoticeItemView(label=item.label, body=item.body.format(section_names=names))
                for item in NOTICE_ITEMS
                if item.shown == "always" or item.shown in fallback
            ],
        ),
        section_markers={name: SECTION_MARKERS[name] for name in fallback},
        form_overwrite_panel=_form_panel(fallback),
        net_worth_overwrite_panel=_net_worth_panel(fallback),
    )


def risk_notice(fallback_sections: Iterable[str]) -> str | None:
    """N-1 / N-2 / N-3 for the risk-cap lists, or ``None``.

    Triggered by ``risk_budget`` and ``net_worth`` only: the other two sections
    feed no cap. The advice endpoint passes nothing on ``insufficient_data``.
    """
    fallback = set(fallback_sections)
    budget, net_worth = "risk_budget" in fallback, "net_worth" in fallback
    if budget and net_worth:
        return RISK_NOTICE_BOTH
    if budget:
        return RISK_NOTICE_BUDGET
    if net_worth:
        return RISK_NOTICE_NET_WORTH
    return None


def kelly_effective_cap_notice(fallback_sections: Iterable[str]) -> str | None:
    """The line beside cap 5's effective value, or ``None``.

    ``risk_budget`` only: ``net_worth`` plays no part in cap 5 (風控 第 4 項).
    """
    return KELLY_EFFECTIVE_CAP_NOTICE if "risk_budget" in set(fallback_sections) else None


def overwrite_required_detail(sections: Iterable[str]) -> str:
    """The 409 ``detail`` naming the sections that needed a confirmed overwrite."""
    return OVERWRITE_REQUIRED_DETAIL.format(section_names=section_names(sections))


def partial_save_notice(
    unwritten_fallback_sections: Iterable[str], *, carried_nothing: bool
) -> str | None:
    """The save confirmation when fallback sections were left unwritten, or ``None``.

    ``carried_nothing`` -- the request carried no section at all -- picks the
    「全未寫入」 variant (K-15 裁示 二-4 (b)); otherwise the original sentence.
    Keyword-only with no default, so the caller has to say which case it is.
    """
    unwritten = _ordered(unwritten_fallback_sections)
    if not unwritten:
        return None
    template = NOTHING_SAVED_NOTICE if carried_nothing else PARTIAL_SAVE_NOTICE
    return template.format(section_names=section_names(unwritten))
