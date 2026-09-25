"""Risk-approved wording the sector card's backend emits (ADR-0012 C-30; 派工單 §5-§13).

Every sentence below is copied **verbatim** from ``work/stock-desk-族群動能-派工單.md``
(risk's final text, punctuation included) and pinned by
``tests/test_api_sectors_wording.py``, which also checks each constant still
appears word for word in that file. Nothing here may be reworded; a change
goes back to risk-compliance-officer first.

Placeholders are kept exactly as risk wrote them (``{x}``, ``{門檻}``, ``{e}``
...). Two substitutions are made at run time, both sanctioned by risk:

* "5" in 「近 5 日」／「近 5 個交易日」 is the version's lookback L (派工單 §6
  preamble: 「5」「近 5 日」由 API ``lookback_days`` 代入). It is **not** applied
  to the turnover decode sentence, whose 5 / 20 are the fixed windows of
  ``turnover_value_ratio_5_20``;
* numbers come from the response's own fields (C-44: each sentence binds its
  own ratio and threshold; {x} is already floored to one decimal, C-37).

Where the backend puts them:

* ``reason`` -- the main-view sentence of the whole-card ``insufficient_reason``
  (IP-1, IP-2: the ``InsufficientPanel`` reason); ``None`` when the card is ok;
* ``disclosures`` -- the 「詳細」 sentences. In ``insufficient_data`` only that
  reason's detail sentence (IP-5: 詳細只可放定稿句與三類排除檔數); otherwise
  the standing, state-independent detail sentences listed in
  :func:`standing_disclosures`. Sentences chosen by ``gate_status`` /
  ``not_evaluated_reason`` / ``pit_gaps`` / ``reason_code`` are the front end's
  (ADR-0012 D-8: 前端依碼選句), and are not duplicated here.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Final

from app.sectors.models import InsufficientReason

# ---------------------------------------------------------------------------
# Whole-card insufficiency (派工單 §9 ④, §10 ①②③⑤)
# ---------------------------------------------------------------------------

#: ① as_of_unknown -- main view (§10); this card's own sentence, never the stock page's (C-45).
AS_OF_UNKNOWN_MAIN: Final = (
    "本卡未取得全市場收盤資料的日期，無法標示資料時間；因此也無法判斷這份資料距今多久。"
    "本次不呈現族群動能排行。"
)
#: ① as_of_unknown -- detail (§10).
AS_OF_UNKNOWN_DETAIL: Final = (
    "資料日期無法確認時，無法判斷排行反映的是哪一天的市場，"
    "因此本卡不呈現族群報酬、上漲家數與歷史統計。"
)
#: ② ex_dividend_feed_gap -- main view (§10).
EX_DIVIDEND_FEED_GAP_MAIN: Final = (
    "系統保存的除權息公告未涵蓋近 5 個交易日，無法確認哪些個股需排除，本次不呈現族群動能排行。"
)
#: ② ex_dividend_feed_gap -- detail (§10).
EX_DIVIDEND_FEED_GAP_DETAIL: Final = (
    "族群報酬計算前，須先依除權息公告排除近 5 個交易日內除權息的個股；"
    "本次系統保存的公告未涵蓋這段期間，若照常計算，除權息造成的價格落差會被誤算為下跌，"
    "因此本卡不呈現族群動能排行。"
)
#: ③ overall_completeness_low -- main view (§10). {x}/{門檻}: completeness (C-44).
OVERALL_COMPLETENESS_LOW_MAIN: Final = (
    "全市場資料完整率 {x}%，低於 {門檻}%（{e} 檔中缺漏 {a} 檔），本次不呈現族群動能排行。"
)
#: ③ overall_completeness_low -- detail (§13 R-6; replaces the §10 text, which is void).
OVERALL_COMPLETENESS_LOW_DETAIL: Final = (
    "全市場應有資料 {e} 檔，其中 {a} 檔在計算近 5 日漲跌幅所需的交易日中，"
    "至少一天沒有日線資料（原因未能判定；未取得暫停交易名單時，暫停交易的個股也計入缺漏），"
    "資料完整率 {x}%，低於 {門檻}%。缺漏過多時，無法確認缺漏是否集中在特定族群，"
    "因此本卡不呈現族群動能排行。"
)
#: ④ computable_ratio_low -- main view (§9). {x}/{門檻}: computable ratio (C-44).
COMPUTABLE_RATIO_LOW_MAIN: Final = (
    "近 5 日遇除權息或減資等事件而暫不計入的個股較多，全市場可計算比例 {x}%，"
    "低於 {門檻}%，本次不呈現族群動能排行。"
)
#: ④ computable_ratio_low -- detail (§9).
COMPUTABLE_RATIO_LOW_DETAIL: Final = (
    "可計算比例＝全市場應納入計算的上市普通股中，近 5 日未因資料缺漏、"
    "除權息或減資等公司行動而排除的比例。本次應納入 {e} 檔，排除資料缺漏 {a} 檔、"
    "除權息 {b} 檔、公司行動 {c} 檔，可計算比例 {x}%，低於 {門檻}%。"
    "排除過多時，等權全市場已不足以代表全市場，因此本次不呈現族群動能排行。"
)
#: ⑤ no_sector_computable -- main view (§10).
NO_SECTOR_COMPUTABLE_MAIN: Final = (
    "本次所有官方產業分類的族群皆未達列入排行的標準，不呈現族群動能排行。"
)
#: ⑤ no_sector_computable -- detail (§10). {族群門檻}: sector coverage (C-44).
NO_SECTOR_COMPUTABLE_DETAIL: Final = (
    "族群須有至少 {最小數} 檔可計算成分股，且覆蓋率達 {族群門檻}%，才列入排行；"
    "本次所有族群皆未達標準（成分股不足 {n1} 個、資料覆蓋率不足 {n2} 個、"
    "除權息或減資等事件排除 {n3} 個），因此不呈現族群動能排行。"
)

#: (main view, detail) per reason, in the fixed order of C-42.
INSUFFICIENT_SENTENCES: Final[dict[InsufficientReason, tuple[str, str]]] = {
    "as_of_unknown": (AS_OF_UNKNOWN_MAIN, AS_OF_UNKNOWN_DETAIL),
    "ex_dividend_feed_gap": (EX_DIVIDEND_FEED_GAP_MAIN, EX_DIVIDEND_FEED_GAP_DETAIL),
    "overall_completeness_low": (OVERALL_COMPLETENESS_LOW_MAIN, OVERALL_COMPLETENESS_LOW_DETAIL),
    "computable_ratio_low": (COMPUTABLE_RATIO_LOW_MAIN, COMPUTABLE_RATIO_LOW_DETAIL),
    "no_sector_computable": (NO_SECTOR_COMPUTABLE_MAIN, NO_SECTOR_COMPUTABLE_DETAIL),
}

# ---------------------------------------------------------------------------
# Standing 「詳細」 disclosures
# ---------------------------------------------------------------------------

#: 派工單 §4.5-5 (not ``NON_REALTIME_NOTICE``).
END_OF_DAY_DATA: Final = (
    "本排行以全市場盤後日線計算，非即時資料；資料截至日之後的市場變動未反映在排行中。"
)
#: 派工單 §6.2 (b-ii): structurally TWSE only.
TWSE_ONLY: Final = (
    "本階段尚無上櫃產業分類的資料來源，族群排行、等權全市場與成分股皆僅含上市普通股；"
    "持有的上櫃個股不會出現在本卡。"
)
#: 派工單 §5-2, fourth 「詳細」 sentence: what the benchmark is.
EQUAL_WEIGHT_BENCHMARK: Final = (
    "等權全市場：本卡合格母體內每檔上市普通股權重相同的平均報酬，不是加權指數。"
)
#: 派工單 §5-3: decode of ``turnover_value_ratio_5_20`` (5 / 20 are fixed windows).
TURNOVER_RATIO_DECODE: Final = (
    "成交金額倍數＝族群成分股近 5 個交易日平均成交金額 ÷ 近 20 個交易日平均成交金額"
    "（近 20 日含近 5 日）；僅描述過去，不列入排名，不代表資金流向。"
)
#: 派工單 §4.1e / §6.3 H-2: listing order (the front end also lifts it to the main
#: view when ``held`` is unknown).
LISTING_ORDER: Final = "列示順序僅依近 5 日漲跌幅，不代表任何優先順序。"
#: 派工單 §4.3 「詳細」.
HISTORICAL_DESCRIPTION_ONLY: Final = "本排行與歷史比例僅為歷史統計描述，不代表未來會重演。"
#: 派工單 §13 R-2: the three market exclusion counts, always when the card is ok
#: (0 printed as 0). {e}/{a}/{b}/{c} = ``market_expected_count`` /
#: ``market_missing_count`` / ``market_ex_date_excluded_count`` /
#: ``market_corporate_action_excluded_count``.
MARKET_EXCLUSION_COUNTS: Final = (
    "本次全市場應納入計算的上市普通股共 {e} 檔；其中近 5 日因資料缺漏排除 {a} 檔、"
    "因除權息排除 {b} 檔、因單日價格變動超過漲跌幅限制（例如減資後恢復交易）排除 {c} 檔，"
    "這些個股皆未納入族群報酬與等權全市場的計算。"
)
#: 派工單 §6.2 (a): only when names were excluded for an ex-date in the window.
EX_DATE_EXCLUSION: Final = (
    "近 5 日內遇到除權息的成分股，不納入本次族群報酬計算（本次共 {m} 檔）；"
    "因此本排行的數字可能與個股頁以未還原收盤價呈現的走勢不同。"
)
#: 派工單 §6.2 (d): only when a TAIEX reference return is output.
TAIEX_REFERENCE: Final = (
    "加權指數報酬僅供參考，不用於排名或歷史比例的判定；兩者一律以等權全市場為基準。"
    "加權指數以市值加權且不含股利，與等權全市場不可直接比較。"
)

#: Every constant here, for the verbatim tests.
ALL_SENTENCES: Final[tuple[str, ...]] = (
    AS_OF_UNKNOWN_MAIN,
    AS_OF_UNKNOWN_DETAIL,
    EX_DIVIDEND_FEED_GAP_MAIN,
    EX_DIVIDEND_FEED_GAP_DETAIL,
    OVERALL_COMPLETENESS_LOW_MAIN,
    OVERALL_COMPLETENESS_LOW_DETAIL,
    COMPUTABLE_RATIO_LOW_MAIN,
    COMPUTABLE_RATIO_LOW_DETAIL,
    NO_SECTOR_COMPUTABLE_MAIN,
    NO_SECTOR_COMPUTABLE_DETAIL,
    END_OF_DAY_DATA,
    TWSE_ONLY,
    EQUAL_WEIGHT_BENCHMARK,
    TURNOVER_RATIO_DECODE,
    LISTING_ORDER,
    HISTORICAL_DESCRIPTION_ONLY,
    MARKET_EXCLUSION_COUNTS,
    EX_DATE_EXCLUSION,
    TAIEX_REFERENCE,
)


# ---------------------------------------------------------------------------
# Filling
# ---------------------------------------------------------------------------


def with_lookback(text: str, lookback_days: int) -> str:
    """Put the version's L into 「近 5 日」／「近 5 個交易日」 (risk: the only substitution)."""
    return text.replace("近 5 日", f"近 {lookback_days} 日").replace(
        "近 5 個交易日", f"近 {lookback_days} 個交易日"
    )


def threshold_pct(threshold: float) -> str:
    """A threshold ratio as the percent risk prints: 0.98 -> "98", 0.825 -> "82.5"."""
    percent = Fraction(repr(threshold)) * 100
    if percent.denominator == 1:
        return str(percent.numerator)
    text = f"{float(percent):.6f}".rstrip("0")
    return text.rstrip(".")


def display_pct(value: float) -> str:
    """An already-floored display percent (C-37) with its one decimal: 79.9 -> "79.9"."""
    return f"{value:.1f}"


def fill(template: str, values: dict[str, object], *, lookback_days: int) -> str:
    """``template`` with its placeholders and the lookback substituted."""
    return with_lookback(template, lookback_days).format_map(
        {key: str(value) for key, value in values.items()}
    )


def standing_disclosures(
    *,
    lookback_days: int,
    market_expected_count: int,
    market_missing_count: int,
    market_ex_date_excluded_count: int,
    market_corporate_action_excluded_count: int,
    has_taiex_reference: bool,
) -> list[str]:
    """The 「詳細」 sentences shown whatever the gate state, when the card is ok.

    Always, in this order: "historical description only" first (risk
    suggestion, 派工單 §13), end-of-day data, TWSE only, what the benchmark is,
    the turnover decode, the listing order, and the market exclusion counts
    (R-2; printed even when every count is 0). Conditional: the ex-date
    exclusion sentence when names were excluded for an ex-date ({m} =
    ``market_ex_date_excluded_count``, the same field as R-2's {b}), and the
    TAIEX reference sentence when a reference return is output.
    """
    counts: dict[str, object] = {
        "e": market_expected_count,
        "a": market_missing_count,
        "b": market_ex_date_excluded_count,
        "c": market_corporate_action_excluded_count,
    }
    sentences = [
        HISTORICAL_DESCRIPTION_ONLY,
        END_OF_DAY_DATA,
        TWSE_ONLY,
        EQUAL_WEIGHT_BENCHMARK,
        TURNOVER_RATIO_DECODE,
        with_lookback(LISTING_ORDER, lookback_days),
        fill(MARKET_EXCLUSION_COUNTS, counts, lookback_days=lookback_days),
    ]
    if market_ex_date_excluded_count:
        sentences.append(
            fill(
                EX_DATE_EXCLUSION,
                {"m": market_ex_date_excluded_count},
                lookback_days=lookback_days,
            )
        )
    if has_taiex_reference:
        sentences.append(TAIEX_REFERENCE)
    return sentences
