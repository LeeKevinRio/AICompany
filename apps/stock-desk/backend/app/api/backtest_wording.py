"""F-11 copy of the backtest report's round-trip detail block: one definition site.

Every user-facing sentence and label F-11 adds is defined here, once, and
reaches the page only through ``BacktestResponse.round_trip_detail.labels``
(tech-architect F11-A-30, A-38; PRD C 節). The front end renders these strings
verbatim and holds no copy of its own.

Approval source -- risk-compliance-officer, verbatim, any one-character change
goes back to that review:

* L-01 .. L-18 except L-06p: ``work/reviews/2026-10-13-F-11-新字面逐字審-風控裁示-
  修訂版-F11-W1至W21.md`` §2 逐字定稿清單 (F11-W-1 .. W-21);
* L-06p: ``work/reviews/2026-10-13-F-11-L-06p逐字審-風控裁示-F11-W22至W27.md`` §1
  (F11-W-22 .. W-27);
* both reproduced in ``work/stock-desk-F-11-回測報告補欄位-PRD.md`` v0.3, C.2.

Rules this module keeps (pinned in ``tests/test_backtest_wording.py``):

* A ``{...}`` placeholder never ships. Every template is filled here by
  ``str.format``; :func:`build_round_trip_labels` is the only producer of what
  the response carries.
* The threshold number in L-09 is formatted from
  :data:`app.backtest.display_params.N_MIN_DISPLAY`, never typed into a string.
* L-06p names the detail title (L-01a / L-01b) and the exclusion heading
  (L-11h) by passing **those constant objects** to ``format`` (F11-W-24), so
  the pointer cannot name a heading the page does not carry.
* The segment names used by L-16c are cut from the L-01 constants themselves,
  so they share one source with the titles.
* The boundary-exclusion copy here is new copy written for both segments; it
  neither imports nor paraphrases any sentence of another surface.
* Numbers the existing metric table formats with the front end's locale
  formatters (the two mean returns, as percentages) stay numbers on the wire.
  For those cells the front end renders ``formatPercent(value)`` followed by
  the text this module produced from the same template with the value left
  out -- so a missing value renders as ``—`` plus that text, which is exactly
  the template filled with ``—`` (F11-W-20). Every other placeholder (counts,
  dates, titles) is filled here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.backtest.display_params import N_MIN_DISPLAY
from app.backtest.report import SegmentRoundTripDetail, WalkForwardRoundTripDetail

# --- L-01: detail sub-block titles -------------------------------------------
ROUND_TRIP_DETAIL_TITLE_IN_SAMPLE = "樣本內：完整回合明細"
ROUND_TRIP_DETAIL_TITLE_OUT_OF_SAMPLE = "樣本外：完整回合明細"

#: ``{segment}`` of L-16c: the segment name as the L-01 title states it.
SEGMENT_NAME_IN_SAMPLE = ROUND_TRIP_DETAIL_TITLE_IN_SAMPLE.partition("：")[0]
SEGMENT_NAME_OUT_OF_SAMPLE = ROUND_TRIP_DETAIL_TITLE_OUT_OF_SAMPLE.partition("：")[0]

# --- L-02: list column headers and their note --------------------------------
ROUND_TRIP_ENTRY_DATE_HEADER = "進場日"
ROUND_TRIP_EXIT_DATE_HEADER = "出場日"
ROUND_TRIP_HOLDING_BARS_HEADER = "持有日數（日線根數）"
ROUND_TRIP_RETURN_HEADER = "回合報酬率（相對進場前權益）"
#: The cell carries the currency prefix (F11-W-15), not this header.
ROUND_TRIP_REALIZED_PNL_HEADER = "已實現損益"
ROUND_TRIP_COLUMNS_NOTE = (
    "回合報酬率＝該回合已實現損益 ÷ 進場前的權益，不等同於標的價格的漲跌幅。"
    "持有日數的單位是日線根數；資料若有缺漏，日線根數可能少於實際的交易日。"
)

# --- L-03: lowest-return sub-section -----------------------------------------
LOWEST_RETURNS_HEADING = "回合報酬率最低的幾筆（由低到高排列）：列出 {k} 筆／共 {n} 筆"

# --- L-04: longest losing streak row -----------------------------------------
LOSING_STREAK_LABEL = "最長連續虧損回合數"
LOSING_STREAK_VALUE = "{length}（{start_date} 至 {end_date}）"
#: Round trips exist, none of them lost.
LOSING_STREAK_VALUE_NONE_LOST = "0"
#: No round trip at all: no streak is defined.
LOSING_STREAK_VALUE_UNDEFINED = "—"
LOSING_STREAK_DEFINITION = (
    "最長連續虧損回合數是報酬率低於零的完整回合接連出現的最大回合數，"
    "報酬率為零或高於零的回合會中斷。起日為該段第一筆回合的進場日，"
    "迄日為最後一筆回合的出場日。有數段同長度時，列出的是最早的一段。"
    "連續虧損只在本區段內的完整回合之間計算，被排除的回合不算在內；"
    "因此一段連續虧損若與被排除的回合相鄰，顯示的長度可能短於把該回合一併計入時的長度。"
)

# --- L-05: mean winning / losing return rows ---------------------------------
MEAN_WINNING_RETURN_LABEL = "平均獲利回合報酬率"
MEAN_LOSING_RETURN_LABEL = "平均虧損回合報酬率"
MEAN_WINNING_RETURN_CELL = "{value}（{n_win} 筆獲利回合）"
MEAN_LOSING_RETURN_CELL = "{value}（{n_loss} 筆虧損回合）"

# --- L-06: payoff ratio row --------------------------------------------------
BACKTEST_PAYOFF_RATIO_LABEL = "盈虧比"
BACKTEST_PAYOFF_RATIO_DEFINITION = (
    "盈虧比＝本區段獲利回合報酬率的平均 ÷ 虧損回合報酬率平均的絕對值，"
    "是報酬率的比值，不是金額的比值。獲利因子以金額加總計算，兩者基準不同，"
    "數值可能不同，不可互換。"
)
#: L-06p: an independent constant rendered in the same cell after L-06d
#: (F11-W-23); never concatenated into L-06d.
BACKTEST_PAYOFF_RATIO_POINTER = (
    "盈虧比、獲利因子與其他以完整回合為單位算出的列，"
    "所用的是進場與出場都落在本區段內的完整回合；"
    "被排除的回合數與說明，載於本區段「{detail_title}」中的「{excluded_heading}」。"
)

# --- L-07: profit factor definition ------------------------------------------
BACKTEST_PROFIT_FACTOR_DEFINITION = (
    "獲利因子＝本區段獲利回合已實現損益的加總 ÷ 虧損回合已實現損益絕對值的加總，"
    "是金額基準，且已實現損益含成本。金額加總會隨獲利與虧損的筆數多寡、"
    "各回合進場前權益的大小而變，所以與盈虧比的數值可能不同，兩者不可互換。"
)

# --- L-08: in-market share row -----------------------------------------------
IN_MARKET_RATIO_LABEL = "在場時間比例"
IN_MARKET_RATIO_DEFINITION = (
    "在場時間比例＝本區段中、起點收盤後持有股票的日線區間數 ÷ 本區段的日線區間數"
    "（相鄰兩根日線之間算一個區間，與總報酬率涵蓋同一組區間）；無法計算時顯示「—」。"
    "暖身期沒有扣除：本區段有 {warmup_flat_intervals} 個區間落在策略的暖身期"
    "（策略需先累積一段資料才能產生訊號），暖身期間策略不持有股票。"
    "Buy & Hold 的在場時間依定義是 100%（自本區段第一根收盤起全程持有），不是量測值；"
    "沒有 Buy & Hold 序列時顯示「—」。"
)

# --- L-09 / L-10: sample-size sentences --------------------------------------
#: Shown only when the segment's flag is set; true for every n, zero included.
SAMPLE_BELOW_MINIMUM = (
    "本區段的完整回合數少於 {n_min_display} 筆。"
    "以完整回合為單位算出的各項是否適用於其他期間，難以判斷；已算出的數字都照常列出。"
)
#: Shown on every segment, whatever its count (F11-R-10).
SAMPLE_COUNT_REMINDER = (
    "本區段的完整回合數是名目筆數，也就是直接數出來的回合數。"
    "同一檔標的的回合常集中在相近的行情，彼此可能不完全獨立；"
    "回合之間不獨立時，同樣的筆數所含的資訊，可能比同樣多筆各自獨立的觀察少。"
    "筆數多寡也不代表這些結果會延續到未來。"
)

# --- L-11: excluded round trips ----------------------------------------------
EXCLUDED_ROUND_TRIPS_HEADING = "本區段排除的回合"
EXCLUDED_CLOSED_ROUND_TRIPS_LABEL = "被排除的已平倉回合數（與本區段重疊，但進場或出場不在本區段內）"
EXCLUDED_OPEN_ROUND_TRIPS_LABEL = (
    "被排除的未平倉回合數（本區段結束前已進場，到回測資料最後一根 {last_bar_date} 仍未平倉）"
)
EXCLUDED_ROUND_TRIPS_NOTE = (
    "明細，以及以完整回合為單位算出的各項，所用的是進場與出場都落在本區段內的完整回合；"
    "這兩類被排除的回合不在其中。持有越久的回合，越容易跨過區段邊界或拖到最後一根，"
    "所以被排除的回合傾向持有較久，明細與這些統計因此較不容易包含持有期間長的回合。"
    "這對統計結果是偏高、偏低或沒有影響，目前沒有證據可以判斷。"
    "同一個回合可能在樣本內與樣本外各被排除一次，所以兩個區段的這兩個數字不可相加。"
)

# --- L-12 / L-13: cost and opening sentences ---------------------------------
COST_AND_SETTINGS_NOTE = (
    "本區段的回合報酬率與已實現損益，以及由它們算出的各項，依本次回測的成本設定計入成本；"
    "實際使用的費率與滑價設定，見本報告所列的費率與滑價。"
    "這些數字取決於本次回測的設定，包括期間、成本設定，以及樣本內與樣本外的長度；"
    "設定不同，結果也可能不同。"
)
DETAIL_OPENING = (
    "本子區塊呈現的是以歷史價格資料模擬的結果，不是對未來報酬或損失幅度的預測。"
    "所列欄位皆由本次回測的價格資料與設定算出，不含當時的新聞或事件說明。"
)

# --- L-14: empty states, keyed by ``SegmentRoundTripDetail.empty_state`` -----
EMPTY_STATE_NO_POSITION = "本區段內沒有進場過，也沒有被排除的回合，所以沒有完整回合可列。"
EMPTY_STATE_EXCLUDED_ONLY = (
    "本區段沒有完整回合可列：與本區段相關的回合都已被排除"
    "（進場或出場不在本區段內，或到回測資料最後一根仍未平倉）。"
)

# --- L-16: full-list toggle --------------------------------------------------
EXPAND_ALL_ROUND_TRIPS = "展開全部 {n} 筆完整回合明細"
COLLAPSE_ALL_ROUND_TRIPS = "收合全部 {n} 筆完整回合明細"
ROUND_TRIP_TOGGLE_ARIA = "{segment}：{label}"

# --- L-18: the unattributed tail, one render point per page -----------------
UNATTRIBUTED_TAIL_PRESENT = (
    "回測資料的最後 {tail_bars} 根日線（{tail_start_date} 至 {tail_end_date}）"
    "不屬於樣本內，也不屬於樣本外。這段期間的模擬損益沒有計入任何指標、權益曲線或回合明細；"
    "在這段期間內才進場的回合，也沒有計入被排除的回合數。"
    "這段期間的長度，取決於資料總根數、訓練窗與測試窗的長度。"
)
UNATTRIBUTED_TAIL_ABSENT = "本次回測資料的每一根日線，都屬於樣本內或樣本外。"

#: Every approved string, by its id in the review and PRD C.2. The verbatim pins
#: and the scoped scans iterate over this inventory.
F11_APPROVED_WORDING: dict[str, str] = {
    "L-01a": ROUND_TRIP_DETAIL_TITLE_IN_SAMPLE,
    "L-01b": ROUND_TRIP_DETAIL_TITLE_OUT_OF_SAMPLE,
    "L-02a": ROUND_TRIP_ENTRY_DATE_HEADER,
    "L-02b": ROUND_TRIP_EXIT_DATE_HEADER,
    "L-02c": ROUND_TRIP_HOLDING_BARS_HEADER,
    "L-02d": ROUND_TRIP_RETURN_HEADER,
    "L-02e": ROUND_TRIP_REALIZED_PNL_HEADER,
    "L-02n": ROUND_TRIP_COLUMNS_NOTE,
    "L-03": LOWEST_RETURNS_HEADING,
    "L-04a": LOSING_STREAK_LABEL,
    "L-04b": LOSING_STREAK_VALUE,
    "L-04c": LOSING_STREAK_VALUE_NONE_LOST,
    "L-04d": LOSING_STREAK_VALUE_UNDEFINED,
    "L-04n": LOSING_STREAK_DEFINITION,
    "L-05a": MEAN_WINNING_RETURN_LABEL,
    "L-05b": MEAN_LOSING_RETURN_LABEL,
    "L-05c": MEAN_WINNING_RETURN_CELL,
    "L-05d": MEAN_LOSING_RETURN_CELL,
    "L-06a": BACKTEST_PAYOFF_RATIO_LABEL,
    "L-06d": BACKTEST_PAYOFF_RATIO_DEFINITION,
    "L-06p": BACKTEST_PAYOFF_RATIO_POINTER,
    "L-07": BACKTEST_PROFIT_FACTOR_DEFINITION,
    "L-08a": IN_MARKET_RATIO_LABEL,
    "L-08n": IN_MARKET_RATIO_DEFINITION,
    "L-09": SAMPLE_BELOW_MINIMUM,
    "L-10": SAMPLE_COUNT_REMINDER,
    "L-11h": EXCLUDED_ROUND_TRIPS_HEADING,
    "L-11a": EXCLUDED_CLOSED_ROUND_TRIPS_LABEL,
    "L-11b": EXCLUDED_OPEN_ROUND_TRIPS_LABEL,
    "L-11n": EXCLUDED_ROUND_TRIPS_NOTE,
    "L-12": COST_AND_SETTINGS_NOTE,
    "L-13": DETAIL_OPENING,
    "L-14 no_position": EMPTY_STATE_NO_POSITION,
    "L-14 excluded_only": EMPTY_STATE_EXCLUDED_ONLY,
    "L-16a": EXPAND_ALL_ROUND_TRIPS,
    "L-16b": COLLAPSE_ALL_ROUND_TRIPS,
    "L-16c": ROUND_TRIP_TOGGLE_ARIA,
    "L-18a": UNATTRIBUTED_TAIL_PRESENT,
    "L-18b": UNATTRIBUTED_TAIL_ABSENT,
}

_VALUE_PLACEHOLDER = "{value}"
#: What a date slot shows when the run has no bar to name (never on a report).
_NO_DATE = "—"


def _text_after_value(template: str) -> str:
    """The part of a ``{value}…`` cell template that follows the value."""
    if not template.startswith(_VALUE_PLACEHOLDER):
        raise ValueError(f"cell template must open with {_VALUE_PLACEHOLDER}: {template!r}")
    return template[len(_VALUE_PLACEHOLDER) :]


#: L-05c / L-05d with the value left out, cut once at import: a template that
#: stops opening with ``{value}`` fails the module load, not a request.
_MEAN_WINNING_RETURN_TAIL = _text_after_value(MEAN_WINNING_RETURN_CELL)
_MEAN_LOSING_RETURN_TAIL = _text_after_value(MEAN_LOSING_RETURN_CELL)


def _count(value: int) -> str:
    """An integer count, grouped the way the front end's locale formatter groups it."""
    return f"{value:,}"


class SegmentRoundTripLabels(BaseModel):
    """The copy of one segment, every placeholder already filled."""

    model_config = ConfigDict(frozen=True)

    #: L-01a / L-01b.
    detail_title: str
    #: L-03 with ``k`` (rows listed) and ``n`` (complete round trips).
    lowest_returns_heading: str
    #: L-04b, L-04c or L-04d, whichever the segment's streak calls for.
    longest_losing_streak_value: str
    #: L-05c / L-05d with the value left out, the side count filled in. The
    #: front end renders ``formatPercent(mean) + this`` -- ``—`` + this when the
    #: mean is null.
    mean_winning_return_suffix: str
    mean_losing_return_suffix: str
    #: L-06p, naming this segment's L-01 title and L-11h.
    payoff_ratio_pointer: str
    #: L-08n with this segment's warm-up interval count.
    in_market_ratio_definition: str
    #: L-16a / L-16b with the segment's ``n``.
    expand_control: str
    collapse_control: str
    #: L-16c around L-16a / L-16b.
    expand_control_aria: str
    collapse_control_aria: str


class RoundTripDetailLabels(BaseModel):
    """All F-11 copy a response carries; nothing here is a template any more."""

    model_config = ConfigDict(frozen=True)

    # L-02
    entry_date: str
    exit_date: str
    holding_bars: str
    return_on_entry_equity: str
    realized_pnl: str
    columns_note: str
    # L-04
    longest_losing_streak: str
    longest_losing_streak_definition: str
    # L-05
    mean_winning_return: str
    mean_losing_return: str
    # L-06 / L-07
    payoff_ratio: str
    payoff_ratio_definition: str
    profit_factor_definition: str
    # L-08
    in_market_ratio: str
    # L-09 (render only where the segment's ``below_display_minimum`` is true)
    # and L-10 (render on every segment)
    sample_below_minimum: str
    sample_count_reminder: str
    # L-11
    excluded_heading: str
    excluded_closed_trips: str
    excluded_open_trips: str
    excluded_note: str
    # L-12 / L-13
    cost_and_settings_note: str
    detail_opening: str
    # L-14, keyed by the segment's ``empty_state`` code
    empty_state_no_position: str
    empty_state_excluded_only: str
    # L-18a or L-18b: the run's single tail disclosure
    unattributed_tail: str
    in_sample: SegmentRoundTripLabels
    out_of_sample: SegmentRoundTripLabels


def _losing_streak_value(segment: SegmentRoundTripDetail) -> str:
    streak = segment.longest_losing_streak
    if streak is None:
        return LOSING_STREAK_VALUE_UNDEFINED
    if streak.length == 0:
        return LOSING_STREAK_VALUE_NONE_LOST
    return LOSING_STREAK_VALUE.format(
        length=_count(streak.length), start_date=streak.start_date, end_date=streak.end_date
    )


def _segment_labels(
    segment: SegmentRoundTripDetail, *, detail_title: str, segment_name: str
) -> SegmentRoundTripLabels:
    n = _count(segment.num_round_trips)
    expand = EXPAND_ALL_ROUND_TRIPS.format(n=n)
    collapse = COLLAPSE_ALL_ROUND_TRIPS.format(n=n)
    return SegmentRoundTripLabels(
        detail_title=detail_title,
        lowest_returns_heading=LOWEST_RETURNS_HEADING.format(
            k=_count(len(segment.lowest_return_round_trips)), n=n
        ),
        longest_losing_streak_value=_losing_streak_value(segment),
        mean_winning_return_suffix=_MEAN_WINNING_RETURN_TAIL.format(
            n_win=_count(segment.num_winning_round_trips)
        ),
        mean_losing_return_suffix=_MEAN_LOSING_RETURN_TAIL.format(
            n_loss=_count(segment.num_losing_round_trips)
        ),
        payoff_ratio_pointer=BACKTEST_PAYOFF_RATIO_POINTER.format(
            detail_title=detail_title, excluded_heading=EXCLUDED_ROUND_TRIPS_HEADING
        ),
        in_market_ratio_definition=IN_MARKET_RATIO_DEFINITION.format(
            warmup_flat_intervals=_count(segment.warmup_flat_intervals)
        ),
        expand_control=expand,
        collapse_control=collapse,
        expand_control_aria=ROUND_TRIP_TOGGLE_ARIA.format(segment=segment_name, label=expand),
        collapse_control_aria=ROUND_TRIP_TOGGLE_ARIA.format(segment=segment_name, label=collapse),
    )


def build_round_trip_labels(detail: WalkForwardRoundTripDetail) -> RoundTripDetailLabels:
    """Fill every F-11 template for one run; the only producer of shipped F-11 copy."""
    coverage = detail.coverage
    # ``None`` only for a run with no bar, which never reaches a report; the
    # dash keeps this total rather than inventing a date.
    last_bar_date = coverage.last_bar_date or _NO_DATE
    if coverage.unattributed_tail_bars > 0:
        tail = UNATTRIBUTED_TAIL_PRESENT.format(
            tail_bars=_count(coverage.unattributed_tail_bars),
            tail_start_date=coverage.unattributed_tail_start_date,
            tail_end_date=last_bar_date,
        )
    else:
        tail = UNATTRIBUTED_TAIL_ABSENT
    return RoundTripDetailLabels(
        entry_date=ROUND_TRIP_ENTRY_DATE_HEADER,
        exit_date=ROUND_TRIP_EXIT_DATE_HEADER,
        holding_bars=ROUND_TRIP_HOLDING_BARS_HEADER,
        return_on_entry_equity=ROUND_TRIP_RETURN_HEADER,
        realized_pnl=ROUND_TRIP_REALIZED_PNL_HEADER,
        columns_note=ROUND_TRIP_COLUMNS_NOTE,
        longest_losing_streak=LOSING_STREAK_LABEL,
        longest_losing_streak_definition=LOSING_STREAK_DEFINITION,
        mean_winning_return=MEAN_WINNING_RETURN_LABEL,
        mean_losing_return=MEAN_LOSING_RETURN_LABEL,
        payoff_ratio=BACKTEST_PAYOFF_RATIO_LABEL,
        payoff_ratio_definition=BACKTEST_PAYOFF_RATIO_DEFINITION,
        profit_factor_definition=BACKTEST_PROFIT_FACTOR_DEFINITION,
        in_market_ratio=IN_MARKET_RATIO_LABEL,
        sample_below_minimum=SAMPLE_BELOW_MINIMUM.format(n_min_display=_count(N_MIN_DISPLAY)),
        sample_count_reminder=SAMPLE_COUNT_REMINDER,
        excluded_heading=EXCLUDED_ROUND_TRIPS_HEADING,
        excluded_closed_trips=EXCLUDED_CLOSED_ROUND_TRIPS_LABEL,
        excluded_open_trips=EXCLUDED_OPEN_ROUND_TRIPS_LABEL.format(last_bar_date=last_bar_date),
        excluded_note=EXCLUDED_ROUND_TRIPS_NOTE,
        cost_and_settings_note=COST_AND_SETTINGS_NOTE,
        detail_opening=DETAIL_OPENING,
        empty_state_no_position=EMPTY_STATE_NO_POSITION,
        empty_state_excluded_only=EMPTY_STATE_EXCLUDED_ONLY,
        unattributed_tail=tail,
        in_sample=_segment_labels(
            detail.in_sample,
            detail_title=ROUND_TRIP_DETAIL_TITLE_IN_SAMPLE,
            segment_name=SEGMENT_NAME_IN_SAMPLE,
        ),
        out_of_sample=_segment_labels(
            detail.out_of_sample,
            detail_title=ROUND_TRIP_DETAIL_TITLE_OUT_OF_SAMPLE,
            segment_name=SEGMENT_NAME_OUT_OF_SAMPLE,
        ),
    )
