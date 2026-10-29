"""N-156 disclosure copy: verbatim, scanned, and chosen by the fallback sections alone.

Source: 「風控 2026-10-29 N-156 字面定稿與表態」 第 1、2、4、6 項 (ADR-0032 accepted,
CEO #74, Decision 2 / K-6 / K-7 / DL-1 / DL-2). Every sentence is **retyped**
here by hand, never imported: a drift of one character in
``app/settings/fallback_wording.py`` has to fail this file rather than quietly
become the new approved text. Every rendered sentence then goes through the
forbidden-term scans (``shared/forbidden-terms.json``, the front end's
``FRONTEND_FORBIDDEN_TERMS``, the rule loader's ``BANNED_PHRASES``, bare 「即時」).

The selection functions are pinned over all sixteen combinations of the four
sections: what appears depends on ``fallback_sections`` and nothing else.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import pytest

from app.advice.loader import BANNED_PHRASES
from app.settings import fallback_wording as wording
from app.settings import store as store_module
from app.settings.migrations import CAP1_SECTION_NAMES
from tests.settings_fallback_helpers import SECTIONS
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

STOCK_DESK_ROOT = Path(__file__).resolve().parents[2]

# --- 第 1 項：設定頁頁首區塊與段標記（逐字重打） ------------------------------------------

TITLE = "部分設定沒有通過驗證，目前使用預設值"
F1 = (
    "發生了什麼",
    "{section_names}原本存的內容沒有通過驗證，系統目前改用這些區段的預設值。本頁這些區段顯示的"
    "也是預設值，不是原本存的內容。",
)
F2 = (
    "原本存的內容",
    "原本存的內容仍留在系統裡，你儲存其他區段時不會改動它；但本頁無法顯示，也無法還原。",
)
F3 = (
    "加碼結論",
    "風險預算使用預設值期間，各條風險上限都依預設值判定，可能比你原本的設定寬，也可能比較嚴。"
    "這段期間個股頁的規則結論為加碼時一律改為觀望，不提供買進股數；減碼與停損參考照常提供，"
    "其中用到風險上限的判定與股數區間同樣依預設值計算。",
)
F4 = (
    "警示與推播",
    "警示排程使用預設值期間，系統照常評估警示，觸發時會推送至已設定的 webhook；若你原本關閉了"
    "評估或推播，目前仍會評估並推送。",
)
F5 = (
    "帳戶總淨值",
    "帳戶總淨值使用預設值期間，系統視為沒有帳戶總淨值，第 3 條總曝險上限無法評估；這不代表你"
    "沒有輸入過，也不代表這條上限已通過。",
)
F6 = (
    "怎麼恢復",
    "在該區段儲存時確認覆寫，系統就改用你這次存的內容。確認覆寫後，原本存的內容會被取代，"
    "系統內不會保留。",
)
F7 = ("檢查時點", "每次讀取設定時都會重新檢查；系統沒有記錄這個狀態從何時開始。")

MARKERS = {
    "risk_budget": (
        "本區段目前顯示與使用的是預設值，不是原本存的內容（原本存的內容沒有通過驗證）。在你確認"
        "覆寫本區段之前，個股頁的規則結論為加碼時一律改為觀望，不提供買進股數。"
    ),
    "cost_model": (
        "本區段目前顯示與使用的是預設值，不是原本存的內容（原本存的內容沒有通過驗證）。回測沒有"
        "另外指定費率時，會用這些預設費率計算。"
    ),
    "alerts": (
        "本區段目前顯示與使用的是預設值，不是原本存的內容（原本存的內容沒有通過驗證）。警示排程"
        "目前照常評估，觸發時會推送至已設定的 webhook。"
    ),
    "net_worth": (
        "本區段原本存的內容沒有通過驗證，本頁無法顯示；系統目前視為沒有帳戶總淨值，第 3 條總曝險"
        "上限無法評估。這不代表你沒有輸入過。"
    ),
}

# --- 第 2 項：短句 ----------------------------------------------------------------------

N1 = (
    "風險預算原本存的內容沒有通過驗證，目前改用預設值，各條風險上限都依預設值判定，可能比你原本"
    "的設定寬，也可能比較嚴。在設定頁確認覆寫風險預算之前，規則結論為加碼時一律改為觀望，不提供"
    "買進股數；減碼與停損參考照常提供，其中用到風險上限的判定與股數區間同樣依預設值計算。"
    "詳見設定頁。"
)
N2 = (
    "帳戶總淨值原本存的內容沒有通過驗證，系統目前視為沒有帳戶總淨值，第 3 條總曝險上限因此無法"
    "評估；這不代表你沒有輸入過，也不代表這條上限已通過。詳見設定頁。"
)
N3 = (
    "風險預算與帳戶總淨值原本存的內容都沒有通過驗證，目前改用預設值：各條風險上限都依預設值判定，"
    "可能比你原本的設定寬，也可能比較嚴；系統也視為沒有帳戶總淨值，第 3 條總曝險上限因此無法"
    "評估，這不代表你沒有輸入過，也不代表這條上限已通過。在設定頁確認覆寫風險預算之前，規則結論"
    "為加碼時一律改為觀望，不提供買進股數；減碼與停損參考照常提供，其中用到風險上限的判定與股數"
    "區間同樣依預設值計算。詳見設定頁。"
)

# --- 第 4 項：Kelly ---------------------------------------------------------------------

KELLY = (
    "此數值依預設的風險預算算出，不是依你的設定：風險預算原本存的內容沒有通過驗證，目前改用"
    "預設值。詳見設定頁頁首的說明。"
)

# --- 第 6 項：S3 覆寫確認面板、409、部分儲存 ----------------------------------------------

PANEL_TITLE = "這些區段目前使用預設值"
P1 = "{section_names}原本存的內容沒有通過驗證，本頁顯示的是預設值，不是原本存的內容。"
P2 = (
    "勾選覆寫的區段，會改存為本頁目前的數值；原本存的內容會被取代，系統內不會保留，也無法從本頁"
    "還原。沒有勾選的區段不會寫入，你在本頁對它們做的修改也不會儲存。"
)
P3 = (
    "風險預算的放寬確認，比較的是本頁顯示的預設值，不是原本存的內容；原本存的值本頁無法得知，"
    "所以你存的值即使比原本寬，系統也可能不會提醒。"
)
P4 = "覆寫風險預算後，各條風險上限改依你這次存的值判定，個股頁的加碼結論恢復依規則判定。"
CHECKBOX = "覆寫「{section_name}」"
SAVE = "儲存"
CANCEL = "取消，不儲存"
P2B = (
    "確認覆寫後，帳戶總淨值會改存為你這次輸入的數值；原本存的內容會被取代，系統內不會保留，"
    "也無法從本頁還原。"
)
NET_WORTH_CONFIRM = "確認覆寫並儲存"
DETAIL_409 = (
    "沒有寫入任何設定：{section_names}原本存的內容沒有通過驗證，要寫入這些區段必須先確認覆寫。"
)
PARTIAL_SAVE = "設定已儲存。{section_names}沒有寫入，仍使用預設值。"

#: Every subset of the four sections, empty included (DL-2: 16 combinations).
COMBOS: list[tuple[str, ...]] = [
    combo for size in range(len(SECTIONS) + 1) for combo in itertools.combinations(SECTIONS, size)
]


def _names(sections: tuple[str, ...]) -> str:
    return "、".join(CAP1_SECTION_NAMES[name] for name in sections)


def _combo_id(combo: tuple[str, ...]) -> str:
    return "+".join(combo) or "none"


# --- 逐字 --------------------------------------------------------------------------


def test_every_sentence_in_the_module_is_the_finalised_one() -> None:
    assert wording.NOTICE_TITLE == TITLE
    assert [(item.label, item.body) for item in wording.NOTICE_ITEMS] == [
        F1,
        F2,
        F3,
        F4,
        F5,
        F6,
        F7,
    ]
    assert [item.shown for item in wording.NOTICE_ITEMS] == [
        "always",
        "always",
        "risk_budget",
        "alerts",
        "net_worth",
        "always",
        "always",
    ]
    assert wording.SECTION_MARKERS == MARKERS
    assert wording.RISK_NOTICE_BUDGET == N1
    assert wording.RISK_NOTICE_NET_WORTH == N2
    assert wording.RISK_NOTICE_BOTH == N3
    assert wording.KELLY_EFFECTIVE_CAP_NOTICE == KELLY
    assert wording.OVERWRITE_PANEL_TITLE == PANEL_TITLE
    assert wording.OVERWRITE_PANEL_WHAT == P1
    assert wording.OVERWRITE_PANEL_FORM_EFFECT == P2
    assert wording.OVERWRITE_PANEL_LOOSENING_CHECK == P3
    assert wording.OVERWRITE_PANEL_BUDGET_EFFECT == P4
    assert wording.OVERWRITE_CHECKBOX_LABEL == CHECKBOX
    assert wording.OVERWRITE_FORM_CONFIRM_LABEL == SAVE
    assert wording.OVERWRITE_CANCEL_LABEL == CANCEL
    assert wording.OVERWRITE_PANEL_NET_WORTH_EFFECT == P2B
    assert wording.OVERWRITE_NET_WORTH_CONFIRM_LABEL == NET_WORTH_CONFIRM
    assert wording.OVERWRITE_REQUIRED_DETAIL == DETAIL_409
    assert wording.PARTIAL_SAVE_NOTICE == PARTIAL_SAVE


def test_n3_is_its_own_sentence_not_n1_and_n2_joined() -> None:
    assert N3 != N1 + N2
    assert N1 not in N3 and N2 not in N3


def test_the_short_sentences_do_not_count_the_caps_or_use_a_held_verb() -> None:
    """第 2 項 用字說明: 「各條」 not 「五條」; no held-mode verb (候選模式 also renders it)."""
    for sentence in (N1, N2, N3):
        assert "五條" not in sentence
        for verb in ("續抱", "加碼參考", "減碼參考", "停損型減碼參考"):
            assert verb not in sentence
    assert "各條" in N1 and "各條" in N3


def _every_rendered_text() -> list[str]:
    texts: list[str] = []
    for combo in COMBOS:
        view = wording.settings_fallback(combo)
        if view is not None:
            texts.append(view.notice.title)
            texts.extend(f"{item.label}｜{item.body}" for item in view.notice.items)
            texts.extend(view.section_markers.values())
            for panel in (view.form_overwrite_panel, view.net_worth_overwrite_panel):
                if panel is not None:
                    texts += [panel.title, *panel.paragraphs, panel.confirm_label]
                    texts += [panel.cancel_label, *(box.label for box in panel.checkboxes)]
        for text in (
            wording.risk_notice(combo),
            wording.kelly_effective_cap_notice(combo),
            wording.partial_save_notice(combo),
        ):
            if text is not None:
                texts.append(text)
        if combo:
            texts.append(wording.overwrite_required_detail(combo))
    return sorted(set(texts))


@pytest.mark.parametrize("text", _every_rendered_text())
def test_every_rendered_sentence_passes_the_forbidden_term_scans(text: str) -> None:
    """DL-1: both lists, the loader's phrases, and no bare 「即時」 (「即使」 is not it)."""
    shared = json.loads(
        (STOCK_DESK_ROOT / "shared" / "forbidden-terms.json").read_text(encoding="utf-8")
    )
    terms = (
        set(FRONTEND_FORBIDDEN_TERMS)
        | set(shared["guarantee"])
        | set(shared["price_target"])
        | set(BANNED_PHRASES)
    )
    assert [term for term in sorted(terms) if term in text] == []
    assert find_bare_realtime_claims(text) == []
    assert "{" not in text and "}" not in text  # every slot filled
    assert "risk_budget" not in text and "net_worth" not in text  # never the internal key


def test_the_scan_covers_every_template() -> None:
    """Not vacuous: the scanned set holds each approved sentence at least once."""
    texts = "\n".join(_every_rendered_text())
    for sentence in (F2[1], F3[1], F4[1], F5[1], F6[1], F7[1], *MARKERS.values()):
        assert sentence in texts
    for sentence in (N1, N2, N3, KELLY, P2, P3, P4, P2B):
        assert sentence in texts


# --- {section_names} --------------------------------------------------------------------


def test_section_order_is_the_stores() -> None:
    assert wording.SECTION_ORDER == tuple(store_module._SECTIONS) == SECTIONS
    assert set(CAP1_SECTION_NAMES) == set(SECTIONS)


def test_section_names_use_the_h2_names_in_order_joined_by_the_ideographic_comma() -> None:
    assert wording.section_names(("net_worth", "risk_budget")) == "風險預算、帳戶總淨值"
    assert wording.section_names(SECTIONS) == "風險預算、費率、警示排程、帳戶總淨值"
    with pytest.raises(KeyError):
        wording.section_names(("kelly",))


# --- 16 種組合：設定頁 -----------------------------------------------------------------


@pytest.mark.parametrize("combo", COMBOS, ids=[_combo_id(c) for c in COMBOS])
def test_the_settings_block_follows_the_fallback_sections(combo: tuple[str, ...]) -> None:
    """DL-2: F-3 / F-4 / F-5 on their section, F-1/2/6/7 always, one marker per section."""
    view = wording.settings_fallback(combo)
    if not combo:
        assert view is None  # K-7: no block, never an empty one
        return
    assert view is not None
    assert view.sections == list(combo)
    assert view.notice.title == TITLE
    expected = [(F1[0], F1[1].format(section_names=_names(combo))), F2]
    if "risk_budget" in combo:
        expected.append(F3)
    if "alerts" in combo:
        expected.append(F4)
    if "net_worth" in combo:
        expected.append(F5)
    expected += [F6, F7]
    assert [(item.label, item.body) for item in view.notice.items] == expected
    assert view.section_markers == {name: MARKERS[name] for name in combo}
    assert list(view.section_markers) == list(combo)


@pytest.mark.parametrize("combo", COMBOS, ids=[_combo_id(c) for c in COMBOS])
def test_the_overwrite_panels_follow_the_fallback_sections(combo: tuple[str, ...]) -> None:
    """第 6 項: the form panel covers its three sections, the net-worth panel its own."""
    view = wording.settings_fallback(combo)
    if view is None:
        assert combo == ()
        return
    form = tuple(name for name in combo if name != "net_worth")
    panel = view.form_overwrite_panel
    if not form:
        assert panel is None
    else:
        assert panel is not None
        assert panel.sections == list(form)
        assert panel.title == PANEL_TITLE
        paragraphs = [P1.format(section_names=_names(form)), P2]
        if "risk_budget" in form:
            paragraphs += [P3, P4]
        assert panel.paragraphs == paragraphs
        assert [(box.section, box.label) for box in panel.checkboxes] == [
            (name, CHECKBOX.format(section_name=CAP1_SECTION_NAMES[name])) for name in form
        ]
        assert (panel.confirm_label, panel.cancel_label) == (SAVE, CANCEL)
    net_worth = view.net_worth_overwrite_panel
    if "net_worth" not in combo:
        assert net_worth is None
    else:
        assert net_worth is not None
        assert net_worth.sections == ["net_worth"]
        assert net_worth.title == PANEL_TITLE
        assert net_worth.paragraphs == [P1.format(section_names="帳戶總淨值"), P2B]
        assert net_worth.checkboxes == []
        assert (net_worth.confirm_label, net_worth.cancel_label) == (NET_WORTH_CONFIRM, CANCEL)


def test_the_checkbox_label_quotes_the_section_name() -> None:
    view = wording.settings_fallback(("risk_budget", "alerts"))
    assert view is not None and view.form_overwrite_panel is not None
    assert [box.label for box in view.form_overwrite_panel.checkboxes] == [
        "覆寫「風險預算」",
        "覆寫「警示排程」",
    ]


# --- 16 種組合：短句、Kelly ---------------------------------------------------------


@pytest.mark.parametrize("combo", COMBOS, ids=[_combo_id(c) for c in COMBOS])
def test_the_short_sentence_is_chosen_by_risk_budget_and_net_worth_only(
    combo: tuple[str, ...],
) -> None:
    """第 2 項: the union of the two; cost_model or alerts alone is ``None``."""
    budget, net_worth = "risk_budget" in combo, "net_worth" in combo
    expected = N3 if budget and net_worth else N1 if budget else N2 if net_worth else None
    assert wording.risk_notice(combo) == expected


@pytest.mark.parametrize("combo", COMBOS, ids=[_combo_id(c) for c in COMBOS])
def test_the_kelly_line_is_for_risk_budget_only(combo: tuple[str, ...]) -> None:
    """第 4 項 / DL 第 7 項: ``net_worth`` plays no part in cap 5."""
    expected = KELLY if "risk_budget" in combo else None
    assert wording.kelly_effective_cap_notice(combo) == expected


# --- 409 與部分儲存 ------------------------------------------------------------------


def test_the_409_detail_names_the_sections_in_order() -> None:
    assert wording.overwrite_required_detail(("alerts", "risk_budget")) == (
        "沒有寫入任何設定：風險預算、警示排程原本存的內容沒有通過驗證，要寫入這些區段必須先確認覆寫。"
    )


def test_the_partial_save_sentence() -> None:
    assert wording.partial_save_notice(()) is None
    assert wording.partial_save_notice(("net_worth", "cost_model")) == (
        "設定已儲存。費率、帳戶總淨值沒有寫入，仍使用預設值。"
    )
