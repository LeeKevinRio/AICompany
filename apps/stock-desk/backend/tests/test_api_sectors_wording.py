"""The sector card's backend wording is risk's final text, verbatim (ADR-0012 C-30; T-14).

Two independent pins per sentence:

* the constant equals the literal below, copied from
  ``work/stock-desk-族群動能-派工單.md`` (§4.3, §4.5-5, §5-2, §5-3, §6.2, §6.3,
  §9, §10, §13) -- including every punctuation mark and the spaces around numbers;
* the constant still appears word for word in that file, so a later edit of
  either side fails here instead of drifting. The sentences risk ruled on in
  §13 (R-2, R-6) must appear in §13 itself, and the §10 ③ detail text that
  R-6 voided may no longer be used by any constant.

Plus the only two run-time substitutions risk sanctioned (the lookback L, and
the numbers from the response's own fields).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api import sectors_wording as wording

DISPATCH = Path(__file__).resolve().parents[4] / "work" / "stock-desk-族群動能-派工單.md"

#: Copied from the dispatch sheet (risk final text).
VERBATIM: dict[str, str] = {
    "AS_OF_UNKNOWN_MAIN": (
        "本卡未取得全市場收盤資料的日期，無法標示資料時間；因此也無法判斷這份資料距今多久"
        "。本次不呈現族群動能排行。"
    ),
    "AS_OF_UNKNOWN_DETAIL": (
        "資料日期無法確認時，無法判斷排行反映的是哪一天的市場，因此本卡不呈現族群報酬、上"
        "漲家數與歷史統計。"
    ),
    "EX_DIVIDEND_FEED_GAP_MAIN": (
        "系統保存的除權息公告未涵蓋近 5 個交易日，無法確認哪些個股需排除，本次不呈現族群動能排行。"
    ),
    "EX_DIVIDEND_FEED_GAP_DETAIL": (
        "族群報酬計算前，須先依除權息公告排除近 5 個交易日內除權息的個股；本次系統保存的"
        "公告未涵蓋這段期間，若照常計算，除權息造成的價格落差會被誤算為下跌，因此本卡不呈"
        "現族群動能排行。"
    ),
    "OVERALL_COMPLETENESS_LOW_MAIN": (
        "全市場資料完整率 {x}%，低於 {門檻}%（{e} 檔中缺漏 {a} 檔），本次不呈現族群動能排行。"
    ),
    "OVERALL_COMPLETENESS_LOW_DETAIL": (
        "全市場應有資料 {e} 檔，其中 {a} 檔在計算近 5 日漲跌幅所需的交易日中，至少一天沒有"
        "日線資料（原因未能判定；未取得暫停交易名單時，暫停交易的個股也計入缺漏），資料完整"
        "率 {x}%，低於 {門檻}%。缺漏過多時，無法確認缺漏是否集中在特定族群，因此本卡不呈現"
        "族群動能排行。"
    ),
    "NO_SECTOR_COMPUTABLE_MAIN": (
        "本次所有官方產業分類的族群皆未達列入排行的標準，不呈現族群動能排行。"
    ),
    "NO_SECTOR_COMPUTABLE_DETAIL": (
        "族群須有至少 {最小數} 檔可計算成分股，且覆蓋率達 {族群門檻}%，才列入排行；本次所"
        "有族群皆未達標準（成分股不足 {n1} 個、資料覆蓋率不足 {n2} 個、除權息或減資等事件"
        "排除 {n3} 個），因此不呈現族群動能排行。"
    ),
    "COMPUTABLE_RATIO_LOW_MAIN": (
        "近 5 日遇除權息或減資等事件而暫不計入的個股較多，全市場可計算比例 {x}%，低於 {門"
        "檻}%，本次不呈現族群動能排行。"
    ),
    "COMPUTABLE_RATIO_LOW_DETAIL": (
        "可計算比例＝全市場應納入計算的上市普通股中，近 5 日未因資料缺漏、除權息或減資等"
        "公司行動而排除的比例。本次應納入 {e} 檔，排除資料缺漏 {a} 檔、除權息 {b} 檔、公"
        "司行動 {c} 檔，可計算比例 {x}%，低於 {門檻}%。排除過多時，等權全市場已不足以代表"
        "全市場，因此本次不呈現族群動能排行。"
    ),
    "TWSE_ONLY": (
        "本階段尚無上櫃產業分類的資料來源，族群排行、等權全市場與成分股皆僅含上市普通股；"
        "持有的上櫃個股不會出現在本卡。"
    ),
    "TAIEX_REFERENCE": (
        "加權指數報酬僅供參考，不用於排名或歷史比例的判定；兩者一律以等權全市場為基準。加"
        "權指數以市值加權且不含股利，與等權全市場不可直接比較。"
    ),
    "MARKET_EXCLUSION_COUNTS": (
        "本次全市場應納入計算的上市普通股共 {e} 檔；其中近 5 日因資料缺漏排除 {a} 檔、因除"
        "權息排除 {b} 檔、因單日價格變動超過漲跌幅限制（例如減資後恢復交易）排除 {c} 檔，這"
        "些個股皆未納入族群報酬與等權全市場的計算。"
    ),
    "EX_DATE_EXCLUSION": (
        "近 5 日內遇到除權息的成分股，不納入本次族群報酬計算（本次共 {m} 檔）；因此本排行"
        "的數字可能與個股頁以未還原收盤價呈現的走勢不同。"
    ),
    "END_OF_DAY_DATA": (
        "本排行以全市場盤後日線計算，非即時資料；資料截至日之後的市場變動未反映在排行中。"
    ),
    "EQUAL_WEIGHT_BENCHMARK": (
        "等權全市場：本卡合格母體內每檔上市普通股權重相同的平均報酬，不是加權指數。"
    ),
    "TURNOVER_RATIO_DECODE": (
        "成交金額倍數＝族群成分股近 5 個交易日平均成交金額 ÷ 近 20 個交易日平均成交金額（"
        "近 20 日含近 5 日）；僅描述過去，不列入排名，不代表資金流向。"
    ),
    "LISTING_ORDER": ("列示順序僅依近 5 日漲跌幅，不代表任何優先順序。"),
    "HISTORICAL_DESCRIPTION_ONLY": ("本排行與歷史比例僅為歷史統計描述，不代表未來會重演。"),
}


#: Constants whose final text is risk's 2026-09-25 ruling (派工單 §13).
RULED_IN_SECTION_13 = ("MARKET_EXCLUSION_COUNTS", "OVERALL_COMPLETENESS_LOW_DETAIL")

#: The §10 ③ detail text R-6 voided (kept here only to prove nothing uses it).
VOID_OVERALL_COMPLETENESS_LOW_DETAIL = (
    "全市場應有資料 {e} 檔，其中 {a} 檔在資料截至日沒有日線資料（原因未能判定；未取得"
    "暫停交易名單時，暫停交易的個股也計入缺漏），資料完整率 {x}%，低於 {門檻}%。缺漏"
    "過多時，無法確認缺漏是否集中在特定族群，因此本卡不呈現族群動能排行。"
)


def _section_13() -> str:
    text = DISPATCH.read_text(encoding="utf-8")
    heading = "## 13. 第三波風控裁定（2026-09-25）"
    assert text.count(heading) == 1
    return text.split(heading, 1)[1]


def test_every_constant_is_pinned() -> None:
    names = {
        name for name in dir(wording) if name.isupper() and isinstance(getattr(wording, name), str)
    }
    assert names == set(VERBATIM)
    assert set(wording.ALL_SENTENCES) == {getattr(wording, name) for name in VERBATIM}


@pytest.mark.parametrize("name", sorted(VERBATIM))
def test_the_constant_is_the_final_text(name: str) -> None:
    assert getattr(wording, name) == VERBATIM[name]


@pytest.mark.parametrize("name", sorted(VERBATIM))
def test_the_final_text_is_still_in_the_dispatch_sheet(name: str) -> None:
    assert VERBATIM[name] in DISPATCH.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", RULED_IN_SECTION_13)
def test_section_13_rulings_are_quoted_from_section_13(name: str) -> None:
    assert VERBATIM[name] in _section_13()


def test_the_voided_completeness_detail_is_used_by_no_constant() -> None:
    constants = [getattr(wording, name) for name in VERBATIM]
    assert VOID_OVERALL_COMPLETENESS_LOW_DETAIL not in constants
    assert all("在資料截至日沒有日線資料" not in text for text in constants)
    # §13 records it as void, quoting it once.
    assert VOID_OVERALL_COMPLETENESS_LOW_DETAIL in _section_13()


def test_the_market_exclusion_counts_print_zero() -> None:
    standing = wording.standing_disclosures(
        lookback_days=5,
        market_expected_count=900,
        market_missing_count=0,
        market_ex_date_excluded_count=0,
        market_corporate_action_excluded_count=0,
        has_taiex_reference=False,
    )
    assert standing[0] == wording.HISTORICAL_DESCRIPTION_ONLY
    assert (
        "本次全市場應納入計算的上市普通股共 900 檔；其中近 5 日因資料缺漏排除 0 檔、"
        "因除權息排除 0 檔、因單日價格變動超過漲跌幅限制（例如減資後恢復交易）排除 0 檔，"
        "這些個股皆未納入族群報酬與等權全市場的計算。"
    ) in standing
    assert not any("本次共" in sentence for sentence in standing)  # §6.2 (a) only when m > 0


def test_each_insufficient_reason_has_its_own_pair() -> None:
    pairs = wording.INSUFFICIENT_SENTENCES
    assert list(pairs) == [
        "as_of_unknown",
        "ex_dividend_feed_gap",
        "overall_completeness_low",
        "computable_ratio_low",
        "no_sector_computable",
    ]
    sentences = [sentence for pair in pairs.values() for sentence in pair]
    assert len(set(sentences)) == len(sentences)  # IP-4: never shared


def test_the_lookback_is_the_only_rewrite() -> None:
    assert wording.with_lookback(wording.LISTING_ORDER, 20) == (
        "列示順序僅依近 20 日漲跌幅，不代表任何優先順序。"
    )
    assert "近 20 個交易日" in wording.with_lookback(wording.EX_DIVIDEND_FEED_GAP_MAIN, 20)
    assert wording.with_lookback(wording.LISTING_ORDER, 5) == wording.LISTING_ORDER
    # The turnover decode's 5 / 20 are the ratio's own windows, never L.
    standing = wording.standing_disclosures(
        lookback_days=20,
        market_expected_count=1000,
        market_missing_count=1,
        market_ex_date_excluded_count=0,
        market_corporate_action_excluded_count=0,
        has_taiex_reference=False,
    )
    assert wording.TURNOVER_RATIO_DECODE in standing
    assert any("其中近 20 日因資料缺漏排除 1 檔" in sentence for sentence in standing)
    detail = wording.with_lookback(wording.OVERALL_COMPLETENESS_LOW_DETAIL, 20)
    assert "計算近 20 日漲跌幅所需的交易日中" in detail


def test_numbers_are_formatted_as_risk_prints_them() -> None:
    assert wording.threshold_pct(0.98) == "98"
    assert wording.threshold_pct(0.8) == "80"
    assert wording.threshold_pct(0.825) == "82.5"
    assert wording.display_pct(79.9) == "79.9"
    assert wording.display_pct(80.0) == "80.0"
    filled = wording.fill(
        wording.OVERALL_COMPLETENESS_LOW_MAIN,
        {"x": "97.9", "門檻": "98", "e": 1000, "a": 21},
        lookback_days=5,
    )
    assert (
        filled
        == "全市場資料完整率 97.9%，低於 98%（1000 檔中缺漏 21 檔），本次不呈現族群動能排行。"
    )
