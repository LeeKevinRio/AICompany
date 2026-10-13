"""F-11 copy: verbatim pins, placeholder guards and the F-11-scoped scans.

Sources (risk-compliance-officer, verbatim): the revised ruling F11-W-1..W-21
(§2 逐字定稿清單), the L-06p ruling F11-W-22..W-27, reproduced in PRD v0.3 C.2.
The literals below are the pins: a one-character drift in
``app/api/backtest_wording.py`` turns this file red, and the fix is to go back
to that review, never to edit a pin to match.

Every scan here is **F-11 scoped** -- it reads the F-11 constants and the
labels the response carries, or (for the rejected-draft scan of F11-W-16 /
W-27) the shipped source tree. None of it is merged into the global banned-term
lists (F11-R-2, PRD C.4).
"""

from __future__ import annotations

import ast
import re
import string
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.api import backtest_wording as wording
from app.api.backtest_wording import (
    F11_APPROVED_WORDING,
    RoundTripDetailLabels,
    build_round_trip_labels,
)
from app.api.kelly_wording import KELLY_BOUNDARY_TRIP_EXCLUSION
from app.backtest.display_params import N_MIN_DISPLAY
from app.backtest.engine import BacktestResult, Trade
from app.backtest.report import walk_forward_round_trip_detail
from app.backtest.splits import walk_forward_splits
from tests.import_graph import reachable_app_modules
from tests.test_rules_invalidation_wording import (
    FRONTEND_FORBIDDEN_TERMS,
    find_bare_realtime_claims,
)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_APP_ROOT = _BACKEND_ROOT / "app"
_STOCK_DESK_ROOT = _BACKEND_ROOT.parent
_FRONTEND_APP_ROOT = _STOCK_DESK_ROOT / "frontend" / "app"
_WORDING_SOURCE = _APP_ROOT / "api" / "backtest_wording.py"

#: PRD v0.3 C.2, character for character (L-05e is derived, see below).
APPROVED: dict[str, str] = {
    "L-01a": "樣本內：完整回合明細",
    "L-01b": "樣本外：完整回合明細",
    "L-02a": "進場日",
    "L-02b": "出場日",
    "L-02c": "持有日數（日線根數）",
    "L-02d": "回合報酬率（相對進場前權益）",
    "L-02e": "已實現損益",
    "L-02n": (
        "回合報酬率＝該回合已實現損益 ÷ 進場前的權益，不等同於標的價格的漲跌幅。"
        "持有日數的單位是日線根數；資料若有缺漏，日線根數可能少於實際的交易日。"
    ),
    "L-03": "回合報酬率最低的幾筆（由低到高排列）：列出 {k} 筆／共 {n} 筆",
    "L-04a": "最長連續虧損回合數",
    "L-04b": "{length}（{start_date} 至 {end_date}）",
    "L-04c": "0",
    "L-04d": "—",
    "L-04n": (
        "最長連續虧損回合數是報酬率低於零的完整回合接連出現的最大回合數，"
        "報酬率為零或高於零的回合會中斷。起日為該段第一筆回合的進場日，"
        "迄日為最後一筆回合的出場日。有數段同長度時，列出的是最早的一段。"
        "連續虧損只在本區段內的完整回合之間計算，被排除的回合不算在內；"
        "因此一段連續虧損若與被排除的回合相鄰，顯示的長度可能短於把該回合一併計入時的長度。"
    ),
    "L-05a": "平均獲利回合報酬率",
    "L-05b": "平均虧損回合報酬率",
    "L-05c": "{value}（{n_win} 筆獲利回合）",
    "L-05d": "{value}（{n_loss} 筆虧損回合）",
    "L-06a": "盈虧比",
    "L-06d": (
        "盈虧比＝本區段獲利回合報酬率的平均 ÷ 虧損回合報酬率平均的絕對值，"
        "是報酬率的比值，不是金額的比值。獲利因子以金額加總計算，兩者基準不同，"
        "數值可能不同，不可互換。"
    ),
    "L-06p": (
        "盈虧比、獲利因子與其他以完整回合為單位算出的列，"
        "所用的是進場與出場都落在本區段內的完整回合；"
        "被排除的回合數與說明，載於本區段「{detail_title}」中的「{excluded_heading}」。"
    ),
    "L-07": (
        "獲利因子＝本區段獲利回合已實現損益的加總 ÷ 虧損回合已實現損益絕對值的加總，"
        "是金額基準，且已實現損益含成本。金額加總會隨獲利與虧損的筆數多寡、"
        "各回合進場前權益的大小而變，所以與盈虧比的數值可能不同，兩者不可互換。"
    ),
    "L-08a": "在場時間比例",
    "L-08n": (
        "在場時間比例＝本區段中、起點收盤後持有股票的日線區間數 ÷ 本區段的日線區間數"
        "（相鄰兩根日線之間算一個區間，與總報酬率涵蓋同一組區間）；無法計算時顯示「—」。"
        "暖身期沒有扣除：本區段有 {warmup_flat_intervals} 個區間落在策略的暖身期"
        "（策略需先累積一段資料才能產生訊號），暖身期間策略不持有股票。"
        "Buy & Hold 的在場時間依定義是 100%（自本區段第一根收盤起全程持有），不是量測值；"
        "沒有 Buy & Hold 序列時顯示「—」。"
    ),
    "L-09": (
        "本區段的完整回合數少於 {n_min_display} 筆。"
        "以完整回合為單位算出的各項是否適用於其他期間，難以判斷；已算出的數字都照常列出。"
    ),
    "L-10": (
        "本區段的完整回合數是名目筆數，也就是直接數出來的回合數。"
        "同一檔標的的回合常集中在相近的行情，彼此可能不完全獨立；"
        "回合之間不獨立時，同樣的筆數所含的資訊，可能比同樣多筆各自獨立的觀察少。"
        "筆數多寡也不代表這些結果會延續到未來。"
    ),
    "L-11h": "本區段排除的回合",
    "L-11a": "被排除的已平倉回合數（與本區段重疊，但進場或出場不在本區段內）",
    "L-11b": (
        "被排除的未平倉回合數（本區段結束前已進場，到回測資料最後一根 {last_bar_date} 仍未平倉）"
    ),
    "L-11n": (
        "明細，以及以完整回合為單位算出的各項，所用的是進場與出場都落在本區段內的完整回合；"
        "這兩類被排除的回合不在其中。持有越久的回合，越容易跨過區段邊界或拖到最後一根，"
        "所以被排除的回合傾向持有較久，明細與這些統計因此較不容易包含持有期間長的回合。"
        "這對統計結果是偏高、偏低或沒有影響，目前沒有證據可以判斷。"
        "同一個回合可能在樣本內與樣本外各被排除一次，所以兩個區段的這兩個數字不可相加。"
    ),
    "L-12": (
        "本區段的回合報酬率與已實現損益，以及由它們算出的各項，依本次回測的成本設定計入成本；"
        "實際使用的費率與滑價設定，見本報告所列的費率與滑價。"
        "這些數字取決於本次回測的設定，包括期間、成本設定，以及樣本內與樣本外的長度；"
        "設定不同，結果也可能不同。"
    ),
    "L-13": (
        "本子區塊呈現的是以歷史價格資料模擬的結果，不是對未來報酬或損失幅度的預測。"
        "所列欄位皆由本次回測的價格資料與設定算出，不含當時的新聞或事件說明。"
    ),
    "L-14 no_position": "本區段內沒有進場過，也沒有被排除的回合，所以沒有完整回合可列。",
    "L-14 excluded_only": (
        "本區段沒有完整回合可列：與本區段相關的回合都已被排除"
        "（進場或出場不在本區段內，或到回測資料最後一根仍未平倉）。"
    ),
    "L-16a": "展開全部 {n} 筆完整回合明細",
    "L-16b": "收合全部 {n} 筆完整回合明細",
    "L-16c": "{segment}：{label}",
    "L-18a": (
        "回測資料的最後 {tail_bars} 根日線（{tail_start_date} 至 {tail_end_date}）"
        "不屬於樣本內，也不屬於樣本外。這段期間的模擬損益沒有計入任何指標、權益曲線或回合明細；"
        "在這段期間內才進場的回合，也沒有計入被排除的回合數。"
        "這段期間的長度，取決於資料總根數、訓練窗與測試窗的長度。"
    ),
    "L-18b": "本次回測資料的每一根日線，都屬於樣本內或樣本外。",
}

#: The exact placeholders each template may carry; a text with none carries none.
PLACEHOLDERS: dict[str, set[str]] = {
    "L-03": {"k", "n"},
    "L-04b": {"length", "start_date", "end_date"},
    "L-05c": {"value", "n_win"},
    "L-05d": {"value", "n_loss"},
    "L-06p": {"detail_title", "excluded_heading"},
    "L-08n": {"warmup_flat_intervals"},
    "L-09": {"n_min_display"},
    "L-11b": {"last_bar_date"},
    "L-16a": {"n"},
    "L-16b": {"n"},
    "L-16c": {"segment", "label"},
    "L-18a": {"tail_bars", "tail_start_date", "tail_end_date"},
}

#: L-06p as rendered, per the L-06p ruling §1 (qa assertion strings).
L06P_RENDERED = {
    "in_sample": (
        "盈虧比、獲利因子與其他以完整回合為單位算出的列，所用的是進場與出場都落在本區段內的完整回合；"
        "被排除的回合數與說明，載於本區段「樣本內：完整回合明細」中的「本區段排除的回合」。"
    ),
    "out_of_sample": (
        "盈虧比、獲利因子與其他以完整回合為單位算出的列，所用的是進場與出場都落在本區段內的完整回合；"
        "被排除的回合數與說明，載於本區段「樣本外：完整回合明細」中的「本區段排除的回合」。"
    ),
}

#: PRD C.3 (F11-W-16, F11-W-27): drafts and pre-correction sentences that may not
#: ship anywhere in the shipped source, comments included. 16 entries.
REJECTED_F11_LITERALS: tuple[tuple[str, str], ...] = (
    ("L-13 修正前原句（F11-W-5）", "已經發生的歷史觀測"),
    ("L-09 修正前條件子句（F11-W-2）", "筆數在這個範圍內時"),
    ("L-10 主案（F11-W-3）", "所以筆數不一定等於同樣多筆各自獨立的觀察"),
    ("L-10 備案（F11-W-3）", "實際可參考的資訊量可能比筆數所示更少"),
    ("L-12 修正前原句（F11-W-4）", "設定不同，結果也不同"),
    ("L-04n 修正前子句（F11-W-1）", "那部分不會計入長度"),
    ("L-06r VETO（F11-W-6）", "最後一位小數可能與盈虧比差一"),
    ("L-06 備案", "盈虧比（報酬率基準）"),
    ("L-14 備案（F11-W-13）", "有持有股票的日子"),
    ("L-16 備案（F11-W-21）", "隱藏全部"),
    ("L-18 備案", "樣本外內進場"),
    ("L-15 替代句候選（O-1）", "本子區塊不含與其他標的或指數的比較"),
    ("L-06p 備案（F11-W-27）", "被排除的回合數與說明，見本區段"),
    ("L-06p 修正前原句（F11-W-22、W-27）", "其他以完整回合算出的列"),
    ("L-06p 前一版（F11-W-27）", "含盈虧比與獲利因子"),
    ("L-06p 未採用的替代寫法（F11-W-27）", "被排除的回合數及其說明"),
)

#: PRD C.3 note: L-15 is removed whole, its "not loaded" kind of sentence too.
L15_REMOVED = ("未載入基準指數", "同期指數")

#: AC-8 / F11-W-18: the enumerated exemption list is empty. A future entry needs
#: a risk ruling, recorded as (approved id, word, count).
AC8_EXEMPTIONS: tuple[tuple[str, str, int], ...] = ()
AC8_BANNED = (
    "具統計意義",
    "統計意義",
    "顯著",
    "足夠",
    "充足",
    "可靠",
    "可信",
    "有優勢",
    "沒有優勢",
    "無優勢",
    "曲線擬合",
    "過度擬合",
    "擬合",
    "已達",
    "通過",
)

#: PRD C.4.2: PX-2's external-source phrases, never product copy.
PX2_PHRASES = (
    "真正有優勢",
    "挖出交易機會",
    "不會糊弄你",
    "一則清晰的交易",
    "在燒你錢",
    "別客氣",
    "別說軟話",
    "能照做的清單",
)

#: F11-R-4, R-16.3, R-17: the page may not point at the sizing surface at all.
CROSS_SCREEN_TERMS = ("Kelly", "kelly", "凱利", "閘門", "匯入", "下注", "加碼", "部位大小")

#: F11-W-17: the statistic labels and definitions the「依…計」scan covers. L-12
#: is out of it on purpose (its 依 hangs on the returns, O-8) and is pinned
#: verbatim above instead.
YI_JI_SCOPE = (
    "L-04a",
    "L-04n",
    "L-05a",
    "L-05b",
    "L-05c",
    "L-05d",
    "L-06a",
    "L-06d",
    "L-06p",
    "L-07",
    "L-08a",
    "L-08n",
    "L-02a",
    "L-02b",
    "L-02c",
    "L-02d",
    "L-02e",
)
YI_JI = re.compile(r"依[^，。；：、（）「」]*計")

#: KT-R-10: three phrases no exclusion or tail sentence may carry.
KT_R_10_PHRASES = ("跨越樣本內、外邊界", "本區段結束時仍未平倉", "在本區段內進場")


def _placeholders(text: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(text) if field is not None}


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


# --------------------------------------------------------------------------
# Labels of real shapes: n = 0 (both codes), n > 0, n >= 1000, r = 0 / r > 0
# --------------------------------------------------------------------------


def _run(
    bars: int, spans: list[tuple[int, int, float]], open_entry: int | None = None
) -> BacktestResult:
    dates = [(date(2020, 1, 1) + timedelta(days=t)).isoformat() for t in range(bars)]
    trades: list[Trade] = []
    for entry, exit_, ret in spans:
        trades.append(Trade(dates[entry], entry, "buy", 10.0, 100.0, 1000.0, 0.0, None))
        trades.append(Trade(dates[exit_], exit_, "sell", -10.0, 100.0, -1000.0, 0.0, ret * 1e6))
    if open_entry is not None:
        trades.append(Trade(dates[open_entry], open_entry, "buy", 10.0, 100.0, 1000.0, 0.0, None))
    return BacktestResult(
        dates=dates,
        equity_curve=[1e6] * bars,
        close=[100.0] * bars,
        weights=[0.0] * bars,
        trades=trades,
        initial_cash=1e6,
    )


def _labels_for(
    bars: int,
    spans: list[tuple[int, int, float]],
    open_entry: int | None = None,
    *,
    train: int = 252,
    test: int = 63,
    warmup: int = 60,
) -> RoundTripDetailLabels:
    folds = walk_forward_splits(bars, train_size=train, test_size=test)
    detail = walk_forward_round_trip_detail(
        _run(bars, spans, open_entry), folds, warmup_bars=warmup
    )
    return build_round_trip_labels(detail)


_MANY = [(253 + 2 * i, 254 + 2 * i, -0.01 if i % 3 else 0.01) for i in range(1200)]

LABEL_SHAPES = {
    "n=0 no_position r>0": (360, [], None, 252, 63),
    "n=0 excluded_only r=0": (315, [(240, 260, 0.01)], None, 252, 63),
    "open at the end r>0": (360, [(10, 20, -0.01), (30, 40, -0.02)], 300, 252, 63),
    "streak and wins r=0": (
        315,
        [(10, 20, -0.01), (30, 40, 0.02), (260, 270, -0.03)],
        None,
        252,
        63,
    ),
    "thousands of round trips": (3000, _MANY, None, 252, 2700),
    "one-bar tail": (316, [(10, 20, 0.01)], None, 252, 63),
}


@pytest.fixture(params=sorted(LABEL_SHAPES), name="labels")
def _labels(request: pytest.FixtureRequest) -> dict[str, object]:
    bars, spans, open_entry, train, test = LABEL_SHAPES[request.param]
    dumped: dict[str, object] = _labels_for(
        bars, spans, open_entry, train=train, test=test
    ).model_dump()
    return dumped


# --------------------------------------------------------------------------
# Verbatim
# --------------------------------------------------------------------------


def test_the_inventory_is_exactly_the_approved_list() -> None:
    assert set(F11_APPROVED_WORDING) == set(APPROVED)


@pytest.mark.parametrize("item", sorted(APPROVED))
def test_each_approved_string_ships_character_for_character(item: str) -> None:
    assert F11_APPROVED_WORDING[item] == APPROVED[item]


@pytest.mark.parametrize("item", sorted(APPROVED))
def test_each_template_carries_exactly_its_approved_placeholders(item: str) -> None:
    assert _placeholders(F11_APPROVED_WORDING[item]) == PLACEHOLDERS.get(item, set())


def test_l05e_is_the_l05c_and_l05d_template_filled_with_a_dash_and_zero() -> None:
    """F11-W-20: no separate string; the same template, ``—`` and 0 put in."""
    detail = walk_forward_round_trip_detail(
        _run(360, []), walk_forward_splits(360, train_size=252, test_size=63), warmup_bars=0
    )
    segment = build_round_trip_labels(detail).in_sample
    win_cell = "—" + segment.mean_winning_return_suffix
    loss_cell = "—" + segment.mean_losing_return_suffix
    assert win_cell == wording.MEAN_WINNING_RETURN_CELL.format(value="—", n_win=0)
    assert loss_cell == wording.MEAN_LOSING_RETURN_CELL.format(value="—", n_loss=0)
    assert f"{win_cell}／{loss_cell}" == "—（0 筆獲利回合）／—（0 筆虧損回合）"


def test_a_filled_mean_cell_is_the_value_followed_by_the_suffix() -> None:
    detail = walk_forward_round_trip_detail(
        _run(360, [(10, 20, 0.02), (30, 40, -0.01), (50, 60, 0.03)]),
        walk_forward_splits(360, train_size=252, test_size=63),
        warmup_bars=0,
    )
    segment = build_round_trip_labels(detail).in_sample
    assert "+2.50%" + segment.mean_winning_return_suffix == wording.MEAN_WINNING_RETURN_CELL.format(
        value="+2.50%", n_win=2
    )
    assert segment.mean_losing_return_suffix == "（1 筆虧損回合）"


def test_the_segment_names_are_cut_from_the_l01_titles() -> None:
    assert wording.SEGMENT_NAME_IN_SAMPLE == "樣本內"
    assert wording.SEGMENT_NAME_OUT_OF_SAMPLE == "樣本外"


# --------------------------------------------------------------------------
# L-06p (F11-W-22 .. W-26)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("segment", ["in_sample", "out_of_sample"])
def test_l06p_renders_the_approved_sentence_for_each_segment(segment: str) -> None:
    """F11-W-24(b): full text, own title present, the other one absent, no brace."""
    detail = walk_forward_round_trip_detail(
        _run(360, [(10, 20, 0.01)]),
        walk_forward_splits(360, train_size=252, test_size=63),
        warmup_bars=0,
    )
    labels = build_round_trip_labels(detail)
    rendered = getattr(labels, segment).payoff_ratio_pointer
    assert rendered == L06P_RENDERED[segment]
    own, other = (
        (wording.ROUND_TRIP_DETAIL_TITLE_IN_SAMPLE, wording.ROUND_TRIP_DETAIL_TITLE_OUT_OF_SAMPLE)
        if segment == "in_sample"
        else (
            wording.ROUND_TRIP_DETAIL_TITLE_OUT_OF_SAMPLE,
            wording.ROUND_TRIP_DETAIL_TITLE_IN_SAMPLE,
        )
    )
    assert own in rendered and other not in rendered
    assert "{" not in rendered and "}" not in rendered
    # Independent of L-06d: never concatenated into it (F11-W-23(a)).
    assert labels.payoff_ratio_definition == APPROVED["L-06d"]
    assert APPROVED["L-06d"] not in rendered


def test_l06p_is_filled_from_the_title_and_heading_constants_themselves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F11-W-24(a): swap the constants and the pointer follows -- no retyped copy."""
    monkeypatch.setattr(wording, "ROUND_TRIP_DETAIL_TITLE_IN_SAMPLE", "TITLE-IS")
    monkeypatch.setattr(wording, "ROUND_TRIP_DETAIL_TITLE_OUT_OF_SAMPLE", "TITLE-OOS")
    monkeypatch.setattr(wording, "EXCLUDED_ROUND_TRIPS_HEADING", "HEADING")
    detail = walk_forward_round_trip_detail(
        _run(360, []), walk_forward_splits(360, train_size=252, test_size=63), warmup_bars=0
    )
    labels = build_round_trip_labels(detail)
    assert labels.in_sample.payoff_ratio_pointer.endswith("「TITLE-IS」中的「HEADING」。")
    assert labels.out_of_sample.payoff_ratio_pointer.endswith("「TITLE-OOS」中的「HEADING」。")
    assert labels.in_sample.detail_title == "TITLE-IS"
    assert labels.excluded_heading == "HEADING"


@pytest.mark.parametrize(
    ("literal", "constant"),
    [
        ("樣本內：完整回合明細", "ROUND_TRIP_DETAIL_TITLE_IN_SAMPLE"),
        ("樣本外：完整回合明細", "ROUND_TRIP_DETAIL_TITLE_OUT_OF_SAMPLE"),
        ("本區段排除的回合", "EXCLUDED_ROUND_TRIPS_HEADING"),
    ],
)
def test_the_three_named_literals_are_written_once_at_their_definition(
    literal: str, constant: str
) -> None:
    """F11-W-24(c): one occurrence in the wording module, on its own definition line."""
    source = _WORDING_SOURCE.read_text(encoding="utf-8")
    assert source.count(literal) == 1
    (line,) = [line for line in source.splitlines() if literal in line]
    assert line.startswith(f"{constant} = ")


def test_the_pointer_and_the_exclusion_block_ship_together(labels: dict[str, object]) -> None:
    """F11-W-25(a): one decision ships both; neither is ever present alone."""
    for segment in ("in_sample", "out_of_sample"):
        block = labels[segment]
        assert isinstance(block, dict)
        assert block["payoff_ratio_pointer"]
    for key in (
        "excluded_heading",
        "excluded_closed_trips",
        "excluded_open_trips",
        "excluded_note",
    ):
        assert labels[key]


# --------------------------------------------------------------------------
# Placeholders never ship (PRD C, F11-A-30)
# --------------------------------------------------------------------------


def test_no_shipped_label_carries_a_placeholder(labels: dict[str, object]) -> None:
    for text in _strings(labels):
        assert "{" not in text and "}" not in text, text


def test_the_threshold_in_l09_comes_from_the_display_constant(labels: dict[str, object]) -> None:
    assert labels["sample_below_minimum"] == APPROVED["L-09"].format(n_min_display=N_MIN_DISPLAY)
    assert f"少於 {N_MIN_DISPLAY} 筆" in str(labels["sample_below_minimum"])


def test_the_tail_sentence_is_l18a_or_l18b_and_nothing_else(labels: dict[str, object]) -> None:
    tail = str(labels["unattributed_tail"])
    absent = tail == APPROVED["L-18b"]
    present = re.fullmatch(
        re.escape(APPROVED["L-18a"])
        .replace(re.escape("{tail_bars}"), r"[\d,]+")
        .replace(re.escape("{tail_start_date}"), r"\d{4}-\d{2}-\d{2}")
        .replace(re.escape("{tail_end_date}"), r"\d{4}-\d{2}-\d{2}"),
        tail,
    )
    assert absent != bool(present)


def test_counts_are_grouped_like_the_front_end_groups_them() -> None:
    labels = _labels_for(3000, _MANY, train=252, test=2700)
    assert labels.out_of_sample.expand_control == "展開全部 1,200 筆完整回合明細"
    assert labels.out_of_sample.expand_control_aria == "樣本外：展開全部 1,200 筆完整回合明細"


# --------------------------------------------------------------------------
# F11-W-16 / W-27: rejected drafts survive nowhere in the shipped source
# --------------------------------------------------------------------------


def _shipped_sources() -> list[Path]:
    """``backend/app/**`` plus ``frontend/app/**`` outside its test folders."""
    backend = sorted(_APP_ROOT.rglob("*.py"))
    frontend = sorted(
        path
        for pattern in ("*.ts", "*.tsx")
        for path in _FRONTEND_APP_ROOT.rglob(pattern)
        if "node_modules" not in path.parts and "__tests__" not in path.parts
    )
    return [*backend, *frontend]


def test_the_rejected_list_is_the_sixteen_of_prd_c3() -> None:
    assert len(REJECTED_F11_LITERALS) == 16
    assert len({literal for _, literal in REJECTED_F11_LITERALS}) == 16


@pytest.mark.parametrize(("ruling", "literal"), REJECTED_F11_LITERALS)
def test_a_rejected_f11_draft_survives_nowhere_in_the_shipped_source(
    ruling: str, literal: str
) -> None:
    offenders = [
        str(path.relative_to(_STOCK_DESK_ROOT))
        for path in _shipped_sources()
        if literal in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"{ruling}：「{literal}」不得存在於出貨原始碼，出現於 {offenders}"


@pytest.mark.parametrize(("ruling", "literal"), REJECTED_F11_LITERALS)
def test_no_approved_string_contains_a_rejected_draft(ruling: str, literal: str) -> None:
    """The risk ruling's own check: none of the 16 is part of an approved string."""
    for text in APPROVED.values():
        assert literal not in text, ruling


@pytest.mark.parametrize("literal", L15_REMOVED)
def test_l15_is_removed_without_a_replacement(literal: str) -> None:
    offenders = [
        str(path.relative_to(_STOCK_DESK_ROOT))
        for path in _shipped_sources()
        if literal in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_the_rejected_scan_reads_the_files_it_claims_to() -> None:
    sources = {str(path.relative_to(_STOCK_DESK_ROOT)) for path in _shipped_sources()}
    assert "backend/app/api/backtest_wording.py" in sources
    assert "backend/app/backtest/report.py" in sources
    assert "frontend/app/backtest/BacktestReportView.tsx" in sources
    assert len(sources) > 100


# --------------------------------------------------------------------------
# F-11 scoped scans (PRD C.4.3; F11-W-17, W-18, W-22)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("item", YI_JI_SCOPE)
def test_no_statistic_label_or_definition_hangs_yi_ji_on_it(item: str) -> None:
    """F11-W-17 / 條件 86: the「依…計」shape, over the statistic copy only."""
    assert YI_JI.search(F11_APPROVED_WORDING[item]) is None


def test_the_yi_ji_scan_has_teeth_and_l12_is_deliberately_outside_it() -> None:
    assert YI_JI.search("盈虧比（依完整回合計）") is not None
    # L-12 matches the shape -- which is exactly why F11-W-17 / O-8 leave it to
    # its verbatim pin rather than to this scan.
    assert YI_JI.search(F11_APPROVED_WORDING["L-12"]) is not None
    assert "L-12" not in YI_JI_SCOPE


def test_the_ac8_exemption_list_is_empty() -> None:
    """F11-W-18: zero entries. Adding one is a risk ruling, never a dev edit."""
    assert AC8_EXEMPTIONS == ()


def test_no_f11_string_claims_sufficiency_or_a_verdict(labels: dict[str, object]) -> None:
    texts = [*F11_APPROVED_WORDING.values(), *_strings(labels)]
    exempt = {(item, word) for item, word, _ in AC8_EXEMPTIONS}
    for text in texts:
        for word in AC8_BANNED:
            if word in text:
                assert any(word == w for _, w in exempt), (word, text)


def test_no_f11_string_points_at_the_sizing_surface(labels: dict[str, object]) -> None:
    """F11-R-4 / R-16.3 / R-17: no Kelly, gate, import, bet, add-on or size wording."""
    for text in [*F11_APPROVED_WORDING.values(), *_strings(labels)]:
        for term in (*CROSS_SCREEN_TERMS, "損益比", "賠率", "其餘", "勝率"):
            assert term not in text, (term, text)


def test_l09_uses_no_contrast_word_and_no_standard_claim() -> None:
    text = F11_APPROVED_WORDING["L-09"]
    for word in ("僅", "只有", "其餘", "統計意義", "最低要求", "標準"):
        assert word not in text


def test_l10_uses_none_of_its_banned_words() -> None:
    text = F11_APPROVED_WORDING["L-10"]
    for word in (
        "足夠",
        "充足",
        "可靠",
        "可信",
        "顯著",
        "具統計意義",
        "優勢",
        "擬合",
        "已達",
        "通過",
    ):
        assert word not in text


def test_l06p_avoids_layout_words_restriction_words_and_direction_claims() -> None:
    """F11-W-7 / W-22: no layout self-reference or restriction words, 其他 in one phrase only."""
    text = F11_APPROVED_WORDING["L-06p"]
    for word in (
        "上方",
        "下方",
        "以下",
        "前面",
        "後面",
        "本表",
        "本頁",
        "這裡",
        "僅",
        "只有",
        "其餘",
        "保守",
    ):
        assert word not in text
    assert YI_JI.search(text) is None
    assert text.count("其他") == text.count("其他以完整回合為單位算出的列") == 1


@pytest.mark.parametrize("item", ["L-11h", "L-11a", "L-11b", "L-11n", "L-18a", "L-18b", "L-04n"])
def test_exclusion_and_tail_copy_avoids_the_kt_r_10_phrases(item: str) -> None:
    text = F11_APPROVED_WORDING[item]
    for phrase in KT_R_10_PHRASES:
        assert phrase not in text
    assert "1.73" not in text


@pytest.mark.parametrize("item", ["L-18a", "L-18b"])
def test_the_tail_copy_carries_no_justification(item: str) -> None:
    for phrase in ("保留作驗證", "確保公平", "更嚴謹", "驗證"):
        assert phrase not in F11_APPROVED_WORDING[item]


def test_l11_is_new_copy_for_both_segments() -> None:
    """F11-R-5.6 (b): not the Kelly sentence, not limited to one segment."""
    for item in ("L-11h", "L-11a", "L-11b", "L-11n"):
        text = F11_APPROVED_WORDING[item]
        assert text != KELLY_BOUNDARY_TRIP_EXCLUSION
        assert text not in KELLY_BOUNDARY_TRIP_EXCLUSION
        assert KELLY_BOUNDARY_TRIP_EXCLUSION not in text
        assert "樣本外（OOS）" not in text
    assert "不可相加" in F11_APPROVED_WORDING["L-11n"]
    assert "回測資料最後一根" in F11_APPROVED_WORDING["L-11b"]


def test_the_wording_module_never_reaches_kelly_copy() -> None:
    """F11-A-30, KT-R-4: neither imported nor named."""
    reachable = reachable_app_modules(("app.api.backtest_wording",))
    assert "app.api.kelly_wording" not in reachable
    assert not any(module.startswith("app.kelly") for module in reachable)
    source = _WORDING_SOURCE.read_text(encoding="utf-8")
    for name in ("KELLY_BOUNDARY_TRIP_EXCLUSION", "kelly_wording", "fr5-6", "fr5-7"):
        assert name not in source


def test_f11_strings_pass_the_global_banned_term_lists(labels: dict[str, object]) -> None:
    """PRD C.4.1 / C.4.2 / AC-13, read from the shared sources rather than retyped."""
    import json

    shared = json.loads((_STOCK_DESK_ROOT / "shared" / "forbidden-terms.json").read_text("utf-8"))
    terms = {*FRONTEND_FORBIDDEN_TERMS, *shared["guarantee"], *shared["price_target"], *PX2_PHRASES}
    for text in [*F11_APPROVED_WORDING.values(), *_strings(labels)]:
        assert [term for term in sorted(terms) if term in text] == [], text
        assert find_bare_realtime_claims(text) == []


# --------------------------------------------------------------------------
# AC-19: numbers only at approved placeholders
# --------------------------------------------------------------------------


def test_numbers_appear_only_at_placeholders_except_the_one_definition_value() -> None:
    """Sentences carry no digit of their own; L-08n's definitional 100% is the one exception.

    L-04c is a value cell ("0"), not a sentence, and is pinned verbatim above.
    """
    for item, text in F11_APPROVED_WORDING.items():
        if item == "L-04c":
            continue
        literal_parts = "".join(part for part, *_ in string.Formatter().parse(text))
        digits = re.findall(r"\d+%?", literal_parts)
        if item == "L-08n":
            assert digits == ["100%"], digits
        else:
            assert digits == [], (item, digits)


# --------------------------------------------------------------------------
# Single definition site (F11-A-22, A-35) and the module's own boundary
# --------------------------------------------------------------------------

#: F-11-specific names only; generic words (in_sample, labels) are left out so
#: the scan cannot trip on unrelated code (F11-A-35).
F11_NAMES = (
    "N_MIN_DISPLAY",
    "N_WORST",
    "display_params",
    "backtest_wording",
    "round_trip_detail",
    "below_display_minimum",
    "RoundTripDetail",
    "SegmentRoundTripDetail",
    "WalkForwardRoundTripDetail",
    "RoundTripCoverage",
    "RoundTripRow",
    "LosingStreak",
    "RoundTripDetailLabels",
    "SegmentRoundTripLabels",
    "walk_forward_round_trip_detail",
    "round_trip_empty_state",
)

KELLY_SIDE = (
    _APP_ROOT / "kelly",
    _APP_ROOT / "advice",
    _APP_ROOT / "api" / "kelly.py",
    _APP_ROOT / "api" / "kelly_wording.py",
)


def _kelly_side_sources() -> list[Path]:
    paths: list[Path] = []
    for entry in KELLY_SIDE:
        paths.extend(sorted(entry.rglob("*.py")) if entry.is_dir() else [entry])
    return paths


@pytest.mark.parametrize("name", ["N_MIN_DISPLAY", "N_WORST"])
def test_each_threshold_is_assigned_exactly_once_under_app(name: str) -> None:
    assignments: list[str] = []
    for path in sorted(_APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign | ast.AugAssign):
                targets = [node.target]
            assignments.extend(
                str(path.relative_to(_BACKEND_ROOT))
                for target in targets
                if isinstance(target, ast.Name) and target.id == name
            )
    assert assignments == ["app/backtest/display_params.py"]


@pytest.mark.parametrize("name", F11_NAMES)
def test_no_f11_name_appears_on_the_kelly_or_advice_side(name: str) -> None:
    sources = _kelly_side_sources()
    assert len(sources) > 10
    offenders = [
        str(path.relative_to(_BACKEND_ROOT))
        for path in sources
        if name in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
