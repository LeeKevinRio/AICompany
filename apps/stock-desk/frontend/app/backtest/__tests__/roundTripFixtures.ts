/**
 * Hand-built `BacktestResponse` fixtures for the F-11 render tests.
 *
 * The numbers are constructed (they describe no real instrument); the **copy**
 * is the risk-approved final text of PRD v0.3 C.2, typed out here a second
 * time on purpose: the tests assert the page renders what the backend sends,
 * verbatim, so they must not share a constant with anything under test. The
 * per-segment strings are filled the way `app/api/backtest_wording.py` fills
 * them (counts grouped, dash for a missing mean).
 */

import type {
  BacktestResponse,
  PerformanceMetricsWithPayoff,
  RoundTripCoverage,
  RoundTripDetailLabels,
  RoundTripEmptyState,
  RoundTripRow,
  SegmentRoundTripDetail,
  SegmentRoundTripLabels,
} from "../../lib/types";

export const IN_SAMPLE_TITLE = "樣本內：完整回合明細";
export const OUT_OF_SAMPLE_TITLE = "樣本外：完整回合明細";
export const EXCLUDED_HEADING = "本區段排除的回合";

export const LAST_BAR_DATE = "2026-07-20";

/** L-06p, rendered, per segment (qa-automation's assertion text in PRD C.2). */
export const POINTER_IN_SAMPLE =
  "盈虧比、獲利因子與其他以完整回合為單位算出的列，所用的是進場與出場都落在本區段內的完整回合；被排除的回合數與說明，載於本區段「樣本內：完整回合明細」中的「本區段排除的回合」。";
export const POINTER_OUT_OF_SAMPLE =
  "盈虧比、獲利因子與其他以完整回合為單位算出的列，所用的是進場與出場都落在本區段內的完整回合；被排除的回合數與說明，載於本區段「樣本外：完整回合明細」中的「本區段排除的回合」。";

export const L06D =
  "盈虧比＝本區段獲利回合報酬率的平均 ÷ 虧損回合報酬率平均的絕對值，是報酬率的比值，不是金額的比值。獲利因子以金額加總計算，兩者基準不同，數值可能不同，不可互換。";
export const L07 =
  "獲利因子＝本區段獲利回合已實現損益的加總 ÷ 虧損回合已實現損益絕對值的加總，是金額基準，且已實現損益含成本。金額加總會隨獲利與虧損的筆數多寡、各回合進場前權益的大小而變，所以與盈虧比的數值可能不同，兩者不可互換。";
export const L04N =
  "最長連續虧損回合數是報酬率低於零的完整回合接連出現的最大回合數，報酬率為零或高於零的回合會中斷。起日為該段第一筆回合的進場日，迄日為最後一筆回合的出場日。有數段同長度時，列出的是最早的一段。連續虧損只在本區段內的完整回合之間計算，被排除的回合不算在內；因此一段連續虧損若與被排除的回合相鄰，顯示的長度可能短於把該回合一併計入時的長度。";
export const L08N_TEMPLATE =
  "在場時間比例＝本區段中、起點收盤後持有股票的日線區間數 ÷ 本區段的日線區間數（相鄰兩根日線之間算一個區間，與總報酬率涵蓋同一組區間）；無法計算時顯示「—」。暖身期沒有扣除：本區段有 {warmup} 個區間落在策略的暖身期（策略需先累積一段資料才能產生訊號），暖身期間策略不持有股票。Buy & Hold 的在場時間依定義是 100%（自本區段第一根收盤起全程持有），不是量測值；沒有 Buy & Hold 序列時顯示「—」。";
export const L09 =
  "本區段的完整回合數少於 30 筆。以完整回合為單位算出的各項是否適用於其他期間，難以判斷；已算出的數字都照常列出。";
export const L10 =
  "本區段的完整回合數是名目筆數，也就是直接數出來的回合數。同一檔標的的回合常集中在相近的行情，彼此可能不完全獨立；回合之間不獨立時，同樣的筆數所含的資訊，可能比同樣多筆各自獨立的觀察少。筆數多寡也不代表這些結果會延續到未來。";
export const L11A = "被排除的已平倉回合數（與本區段重疊，但進場或出場不在本區段內）";
export const L11B_TEMPLATE =
  "被排除的未平倉回合數（本區段結束前已進場，到回測資料最後一根 {date} 仍未平倉）";
export const L11N =
  "明細，以及以完整回合為單位算出的各項，所用的是進場與出場都落在本區段內的完整回合；這兩類被排除的回合不在其中。持有越久的回合，越容易跨過區段邊界或拖到最後一根，所以被排除的回合傾向持有較久，明細與這些統計因此較不容易包含持有期間長的回合。這對統計結果是偏高、偏低或沒有影響，目前沒有證據可以判斷。同一個回合可能在樣本內與樣本外各被排除一次，所以兩個區段的這兩個數字不可相加。";
export const L12 =
  "本區段的回合報酬率與已實現損益，以及由它們算出的各項，依本次回測的成本設定計入成本；實際使用的費率與滑價設定，見本報告所列的費率與滑價。這些數字取決於本次回測的設定，包括期間、成本設定，以及樣本內與樣本外的長度；設定不同，結果也可能不同。";
export const L13 =
  "本子區塊呈現的是以歷史價格資料模擬的結果，不是對未來報酬或損失幅度的預測。所列欄位皆由本次回測的價格資料與設定算出，不含當時的新聞或事件說明。";
export const L14_NO_POSITION = "本區段內沒有進場過，也沒有被排除的回合，所以沒有完整回合可列。";
export const L14_EXCLUDED_ONLY =
  "本區段沒有完整回合可列：與本區段相關的回合都已被排除（進場或出場不在本區段內，或到回測資料最後一根仍未平倉）。";
export const L02N =
  "回合報酬率＝該回合已實現損益 ÷ 進場前的權益，不等同於標的價格的漲跌幅。持有日數的單位是日線根數；資料若有缺漏，日線根數可能少於實際的交易日。";
export const L18A =
  "回測資料的最後 45 根日線（2026-05-20 至 2026-07-20）不屬於樣本內，也不屬於樣本外。這段期間的模擬損益沒有計入任何指標、權益曲線或回合明細；在這段期間內才進場的回合，也沒有計入被排除的回合數。這段期間的長度，取決於資料總根數、訓練窗與測試窗的長度。";
export const L18B = "本次回測資料的每一根日線，都屬於樣本內或樣本外。";

function grouped(value: number): string {
  return value.toLocaleString("zh-Hant-TW");
}

export function segmentLabels(
  detail: SegmentRoundTripDetail,
  title: string,
  segmentName: string,
  pointer: string,
): SegmentRoundTripLabels {
  const n = grouped(detail.num_round_trips);
  const expand = `展開全部 ${n} 筆完整回合明細`;
  const collapse = `收合全部 ${n} 筆完整回合明細`;
  const streak = detail.longest_losing_streak;
  return {
    detail_title: title,
    lowest_returns_heading: `回合報酬率最低的幾筆（由低到高排列）：列出 ${grouped(
      detail.lowest_return_round_trips.length,
    )} 筆／共 ${n} 筆`,
    longest_losing_streak_value:
      streak === null
        ? "—"
        : streak.length === 0
          ? "0"
          : `${grouped(streak.length)}（${streak.start_date} 至 ${streak.end_date}）`,
    mean_winning_return_suffix: `（${grouped(detail.num_winning_round_trips)} 筆獲利回合）`,
    mean_losing_return_suffix: `（${grouped(detail.num_losing_round_trips)} 筆虧損回合）`,
    payoff_ratio_pointer: pointer,
    in_market_ratio_definition: L08N_TEMPLATE.replace("{warmup}", grouped(detail.warmup_flat_intervals)),
    expand_control: expand,
    collapse_control: collapse,
    expand_control_aria: `${segmentName}：${expand}`,
    collapse_control_aria: `${segmentName}：${collapse}`,
  };
}

export function detailLabels(
  inSample: SegmentRoundTripDetail,
  outOfSample: SegmentRoundTripDetail,
  tail: string,
): RoundTripDetailLabels {
  return {
    entry_date: "進場日",
    exit_date: "出場日",
    holding_bars: "持有日數（日線根數）",
    return_on_entry_equity: "回合報酬率（相對進場前權益）",
    realized_pnl: "已實現損益",
    columns_note: L02N,
    longest_losing_streak: "最長連續虧損回合數",
    longest_losing_streak_definition: L04N,
    mean_winning_return: "平均獲利回合報酬率",
    mean_losing_return: "平均虧損回合報酬率",
    payoff_ratio: "盈虧比",
    payoff_ratio_definition: L06D,
    profit_factor_definition: L07,
    in_market_ratio: "在場時間比例",
    sample_below_minimum: L09,
    sample_count_reminder: L10,
    excluded_heading: EXCLUDED_HEADING,
    excluded_closed_trips: L11A,
    excluded_open_trips: L11B_TEMPLATE.replace("{date}", LAST_BAR_DATE),
    excluded_note: L11N,
    cost_and_settings_note: L12,
    detail_opening: L13,
    empty_state_no_position: L14_NO_POSITION,
    empty_state_excluded_only: L14_EXCLUDED_ONLY,
    unattributed_tail: tail,
    in_sample: segmentLabels(inSample, IN_SAMPLE_TITLE, "樣本內", POINTER_IN_SAMPLE),
    out_of_sample: segmentLabels(outOfSample, OUT_OF_SAMPLE_TITLE, "樣本外", POINTER_OUT_OF_SAMPLE),
  };
}

/** A deterministic list of `count` round trips, earliest entry first. */
export function makeRows(count: number, startDay = 1): RoundTripRow[] {
  return Array.from({ length: count }, (_, index) => {
    const day = startDay + index * 3;
    const month = 1 + Math.floor(day / 28);
    const entryDay = 1 + (day % 28);
    const pad = (value: number) => String(value).padStart(2, "0");
    return {
      entry_date: `2025-${pad(month)}-${pad(entryDay)}`,
      exit_date: `2025-${pad(month)}-${pad(Math.min(28, entryDay + 2))}`,
      holding_bars: 2 + (index % 5),
      return_on_entry_equity: (index % 2 === 0 ? 1 : -1) * (0.011 + index * 0.0007),
      realized_pnl: (index % 2 === 0 ? 1 : -1) * (10_250.5 + index * 311.25),
    };
  });
}

export function makeDetail(overrides: Partial<SegmentRoundTripDetail> = {}): SegmentRoundTripDetail {
  const rows = overrides.round_trips ?? makeRows(34);
  return {
    num_round_trips: rows.length,
    num_winning_round_trips: 18,
    num_losing_round_trips: 16,
    round_trips: rows,
    lowest_return_round_trips: rows.slice(0, 5),
    mean_winning_return: 0.0213,
    mean_losing_return: -0.0156,
    longest_losing_streak: { length: 3, start_date: "2025-02-03", end_date: "2025-03-10" },
    excluded_boundary_trips: 2,
    open_trip_at_end: 1,
    in_market_ratio: 0.4213,
    buy_and_hold_in_market_ratio: 1,
    warmup_flat_intervals: 0,
    below_display_minimum: false,
    empty_state: null,
    ...overrides,
  };
}

/** An empty segment as the backend describes it for the given empty-state code. */
export function makeEmptyDetail(
  code: RoundTripEmptyState,
  overrides: Partial<SegmentRoundTripDetail> = {},
): SegmentRoundTripDetail {
  return makeDetail({
    num_round_trips: 0,
    num_winning_round_trips: 0,
    num_losing_round_trips: 0,
    round_trips: [],
    lowest_return_round_trips: [],
    mean_winning_return: null,
    mean_losing_return: null,
    longest_losing_streak: null,
    excluded_boundary_trips: code === "excluded_only" ? 1 : 0,
    open_trip_at_end: 0,
    in_market_ratio: code === "excluded_only" ? 0.3 : 0,
    below_display_minimum: true,
    empty_state: code,
    ...overrides,
  });
}

export function makeMetrics(overrides: Partial<PerformanceMetricsWithPayoff> = {}): PerformanceMetricsWithPayoff {
  return {
    label: "策略",
    start_date: "2024-01-02",
    end_date: "2024-12-30",
    observations: 240,
    start_equity: 1_000_000,
    end_equity: 1_080_000,
    total_return: 0.08,
    cagr: 0.081,
    annualized_volatility: 0.2,
    sharpe: 0.5,
    sortino: 0.6,
    max_drawdown: -0.08,
    max_drawdown_peak_date: "2024-03-01",
    max_drawdown_trough_date: "2024-04-01",
    win_rate: 0.5294,
    profit_factor: 1.31,
    num_trades: 40,
    num_closing_trades: 20,
    turnover: 0.3,
    num_round_trips: 34,
    round_trip_payoff_ratio: 1.37,
    ...overrides,
  };
}

export function makeBuyAndHold(): PerformanceMetricsWithPayoff {
  return makeMetrics({
    label: "Buy & Hold",
    win_rate: null,
    profit_factor: null,
    num_trades: 1,
    num_closing_trades: 0,
    turnover: 0.01,
    num_round_trips: null,
    round_trip_payoff_ratio: null,
  });
}

export interface ResponseOptions {
  inSample?: SegmentRoundTripDetail;
  outOfSample?: SegmentRoundTripDetail;
  inSampleMetrics?: Partial<PerformanceMetricsWithPayoff>;
  outOfSampleMetrics?: Partial<PerformanceMetricsWithPayoff>;
  /** `true`: 45 unattributed tail bars (L-18a); `false`: none (L-18b). */
  withTail?: boolean;
  market?: string;
}

export function makeResponse(options: ResponseOptions = {}): BacktestResponse {
  const inSample = options.inSample ?? makeDetail({ below_display_minimum: false });
  const outOfSample = options.outOfSample ?? makeDetail({ below_display_minimum: false });
  const withTail = options.withTail ?? true;
  const coverage: RoundTripCoverage = {
    last_bar_date: LAST_BAR_DATE,
    unattributed_tail_bars: withTail ? 45 : 0,
    unattributed_tail_start_date: withTail ? "2026-05-20" : null,
  };
  return {
    symbol: "2330",
    market: options.market ?? "TW",
    strategy: "ma_cross",
    status: "ok",
    reason: null,
    report: {
      in_sample: {
        strategy: makeMetrics({ num_round_trips: inSample.num_round_trips, ...options.inSampleMetrics }),
        buy_and_hold: makeBuyAndHold(),
      },
      out_of_sample: {
        strategy: makeMetrics({ num_round_trips: outOfSample.num_round_trips, ...options.outOfSampleMetrics }),
        buy_and_hold: makeBuyAndHold(),
      },
    },
    curves: null,
    round_trip_detail: {
      in_sample: inSample,
      out_of_sample: outOfSample,
      coverage,
      labels: detailLabels(inSample, outOfSample, withTail ? L18A : L18B),
    },
    folds: [{ fold: 0, train_start: 0, train_stop: 200, test_start: 200, test_stop: 260 }],
    cost_model: {
      tw_broker_fee_rate: 0.001425,
      tw_tax_rate_stock: 0.003,
      tw_tax_rate_etf: 0.001,
      us_broker_fee_rate: 0,
      us_sell_regulatory_fee_rate: 0.0000278,
      slippage_bps: 0,
      verified_on: null,
    },
    rates_verified: false,
    dividend_adjustment: {
      requested: true,
      applied: false,
      reason_code: "never_synced",
      note: null,
      events_applied: 0,
      events_skipped: 0,
      first_ex_date: null,
      last_ex_date: null,
      raw_return_understatement: null,
      last_synced_at: null,
    },
    notes: ["note-one"],
    data_warning: null,
    data: {
      status: "fresh",
      source: "twse",
      staleness_minutes: 5,
      is_within_ttl: null,
      bar_count: 445,
      first_bar_date: "2024-01-02",
      last_bar_date: LAST_BAR_DATE,
      trading_days_behind: null,
      reason: null,
    },
    as_of: "2026-07-25T06:00:00Z",
    metric_labels: { win_rate: "<win-rate-label>", round_trips: "<round-trips-label>" },
  };
}
