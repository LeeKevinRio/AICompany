/**
 * `SectorMomentumCardView` state coverage (第四波，
 * `work/stock-desk-族群動能-派工單.md` §12/§13) — rendered with
 * `renderToStaticMarkup` against the pure view component (same convention as
 * `alertStatusStrip.test.ts`). Covers: every NE code, `failed`, `passed`, the
 * five `insufficient_data` reasons, `held: null`, demo data (ok and
 * insufficient), an unrecognized code falling back to `ErrorPanel`,
 * `lookback_days`/`holding_days` substitution, the collapsed-view character
 * budget and the default headline count.
 */

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SectorMomentumCardView } from "../../components/SectorMomentumCard";
import {
  buildAverageSentence,
  buildBeatCountSentence,
  buildBenchmarkReturnSentence,
  buildBootstrapIntervalSentence,
  buildFailedMainSentence,
  buildListingOrderSentence,
  buildPassedMainSentence,
  buildRelativeReturnSentence,
  buildSectorReturnSentence,
  buildSingleStockDominatedSentence,
  buildWilsonIntervalSentence,
  computeConfidenceLevelPercent,
  DEMO_DATA_CARD_WARNING,
  GROSS_COST_GROUP_TITLE,
  KNOWN_NOT_EVALUATED_REASONS,
  NET_COST_GROUP_TITLE,
  notEvaluatedSentences,
  SAMPLING_RULE_LABEL,
  SINGLE_STOCK_DOMINATED_TAG,
} from "../sectorMomentumWording";
import type {
  SectorAccumulation,
  SectorConstituent,
  SectorCoverage,
  SectorHistoricalStat,
  SectorMomentumResponse,
  SectorNotEvaluatedReason,
  SectorRankedItem,
  SectorReasonCode,
} from "../types";

function coverage(overrides: Partial<SectorCoverage> = {}): SectorCoverage {
  return {
    expected_count: 10,
    calculation_count: 9,
    // 預設 0：族群層級缺漏 tag 的專屬測試另外覆寫，避免耦合到其他不相干案例
    // （含收合態字數測試）。
    missing_count: 0,
    ex_date_excluded_count: 1,
    corporate_action_excluded_count: 0,
    suspended_count: null,
    coverage_ratio: 0.9,
    completeness_ratio: 1,
    ...overrides,
  };
}

function constituent(overrides: Partial<SectorConstituent> = {}): SectorConstituent {
  return { symbol: "2330", name: "台積電", return_L: 0.021, held: false, ...overrides };
}

function sector(overrides: Partial<SectorRankedItem> = {}): SectorRankedItem {
  return {
    rank: 1,
    sector_code: "24",
    sector_name: "半導體業",
    sector_return_L: 0.032,
    benchmark_return_L: 0.01,
    rel_return_L: 0.022,
    up_count: 6,
    constituent_count: 8,
    turnover_value_ratio_5_20: 1.2,
    reference_taiex_return_L: 0.015,
    coverage: coverage(),
    top_contributor_share: 0.3,
    single_stock_dominated: false,
    constituents: [
      constituent({ symbol: "2330", name: "台積電", return_L: 0.05, held: true }),
      constituent({ symbol: "2454", name: "聯發科", return_L: 0.04, held: false }),
      constituent({ symbol: "3034", name: "聯詠", return_L: -0.02, held: false }),
    ],
    ...overrides,
  };
}

function accumulation(overrides: Partial<SectorAccumulation> = {}): SectorAccumulation {
  return { accumulated_samples: 12, accumulation_start: "2026-01-05", required_samples: 150, ...overrides };
}

function historicalStat(overrides: Partial<SectorHistoricalStat> = {}): SectorHistoricalStat {
  return {
    rank_scope: "rank_1",
    method_version: "sector-momentum-v1",
    m_at_evaluation: 3,
    sample_count: 80,
    effective_sample_count: 65,
    beat_count_net: 50,
    beat_count_gross: 52,
    base_rate_net: 0.5,
    base_rate_gross: 0.5,
    ci_low_net: 0.55,
    ci_high_net: 0.7,
    bootstrap_low_net: 0.54,
    bootstrap_high_net: 0.71,
    delta_real: 3.2,
    delta_shuffle: 1.1,
    benchmark: "equal_weight_market",
    sample_start: "2023-01-05",
    sample_end: "2026-08-01",
    stats_as_of: "2026-08-01",
    computed_at: "2026-08-02T00:00:00Z",
    run_id: "run-1",
    ...overrides,
  };
}

const FOUR_SECTORS: SectorRankedItem[] = [
  sector({ rank: 1, sector_code: "24", sector_name: "半導體業", up_count: 6, constituent_count: 8 }),
  sector({ rank: 2, sector_code: "20", sector_name: "其他電子業", up_count: 4, constituent_count: 7 }),
  sector({ rank: 3, sector_code: "12", sector_name: "化學工業", up_count: 3, constituent_count: 6 }),
  sector({ rank: 4, sector_code: "08", sector_name: "塑膠工業", up_count: 2, constituent_count: 5 }),
];

function makeResponse(overrides: Partial<SectorMomentumResponse> = {}): SectorMomentumResponse {
  return {
    market: "TW",
    status: "ok",
    insufficient_reason: null,
    reason: null,
    method_version: "sector-momentum-v1",
    lookback_days: 5,
    holding_days: 5,
    data_as_of: "2026-09-19",
    market_scope: "twse_only",
    benchmark: "equal_weight_market",
    data_source: "twse_snapshot",
    coverage: coverage({ expected_count: 900, calculation_count: 850, missing_count: 30, coverage_ratio: 0.944, completeness_ratio: 0.967 }),
    min_constituents: 5,
    sector_coverage_threshold: 0.9,
    overall_coverage_threshold: 0.98,
    computable_ratio: 0.94,
    computable_ratio_min: 0.8,
    computable_ratio_pct_display: 94.4,
    completeness_pct_display: 96.7,
    market_expected_count: 900,
    market_missing_count: 0,
    market_ex_date_excluded_count: 15,
    market_corporate_action_excluded_count: 5,
    market_ex_date_excluded_ratio: 0.0167,
    ex_date_tag_ratio_min: 0.05,
    ex_date_tag: false,
    excluded_reason_counts: null,
    headline_count: 3,
    sectors: FOUR_SECTORS,
    excluded_sectors: [],
    gate_status: "not_evaluated",
    not_evaluated_reason: "accumulating",
    not_evaluated_reasons: ["accumulating"],
    pit_gaps: [],
    accumulation: accumulation(),
    historical_stat: null,
    gate_checks: null,
    fee_verified_on: null,
    disclosures: [
      "本排行與歷史比例僅為歷史統計描述，不代表未來會重演。",
      "本排行以全市場盤後日線計算，非即時資料；資料截至日之後的市場變動未反映在排行中。",
      "本階段尚無上櫃產業分類的資料來源，族群排行、等權全市場與成分股皆僅含上市普通股；持有的上櫃個股不會出現在本卡。",
      "等權全市場：本卡合格母體內每檔上市普通股權重相同的平均報酬，不是加權指數。",
      "成交金額倍數＝族群成分股近 5 個交易日平均成交金額 ÷ 近 20 個交易日平均成交金額（近 20 日含近 5 日）；僅描述過去，不列入排名，不代表資金流向。",
      "列示順序僅依近 5 日漲跌幅，不代表任何優先順序。",
      "本次全市場應納入計算的上市普通股共 900 檔；其中近 5 日因資料缺漏排除 0 檔、因除權息排除 15 檔、因單日價格變動超過漲跌幅限制（例如減資後恢復交易）排除 5 檔，這些個股皆未納入族群報酬與等權全市場的計算。",
    ],
    data: {
      status: "cached_stale",
      source: "twse_snapshot",
      staleness_minutes: 30,
      is_within_ttl: true,
      bar_count: 5,
      first_bar_date: "2026-09-15",
      last_bar_date: "2026-09-19",
      trading_days_behind: 0,
      reason: null,
    },
    as_of: "2026-09-19T10:00:00Z",
    ...overrides,
  };
}

function render(data: SectorMomentumResponse): string {
  return renderToStaticMarkup(createElement(SectorMomentumCardView, { data }));
}

function stripDetails(html: string): string {
  return html.replace(/<details[\s\S]*?<\/details>/g, "");
}

function detailsHtmlOf(html: string): string {
  return (html.match(/<details[\s\S]*?<\/details>/g) ?? []).join("");
}

describe("SectorMomentumCardView — not_evaluated 每碼各一個獨立案例（R-4）", () => {
  for (const reason of KNOWN_NOT_EVALUATED_REASONS) {
    it(`not_evaluated_reason = ${reason}：主視圖句與詳細句都出現，且不出現任何比例數字`, () => {
      const isDemo = reason === "demo_data";
      const html = render(
        makeResponse({
          gate_status: "not_evaluated",
          not_evaluated_reason: reason,
          not_evaluated_reasons: [reason],
          data_source: isDemo ? "demo_synthetic" : "twse_snapshot",
          pit_gaps: reason === "pit_history_missing" ? ["pit_universe", "de5_unverified"] : [],
        }),
      );
      const expected = notEvaluatedSentences({
        reason,
        lookbackDays: 5,
        pitGaps: reason === "pit_history_missing" ? ["pit_universe", "de5_unverified"] : [],
        accumulation: accumulation(),
      });
      expect(html).toContain(expected.main);
      for (const sentence of expected.detail) {
        expect(html).toContain(sentence);
      }
      // C-23 / AC-3: no比例數字 (k/N/p/q) anywhere.
      expect(html).not.toMatch(/beat_count|base_rate/);
      if (isDemo) expect(html).toContain(DEMO_DATA_CARD_WARNING);
    });
  }
});

describe("SectorMomentumCardView — failed／passed", () => {
  it("failed：主視圖降級句 + 詳細兩組數字列（已扣來回成本／未扣成本，明顯分隔）+ T8-1/T8-2", () => {
    const stat = historicalStat({ beat_count_net: 50, beat_count_gross: 52, base_rate_net: 0.5, base_rate_gross: 0.45 });
    const html = render(
      makeResponse({
        gate_status: "failed",
        not_evaluated_reason: null,
        not_evaluated_reasons: [],
        historical_stat: stat,
      }),
    );
    expect(html).toContain(buildFailedMainSentence(5));
    // 組 1（已扣來回成本）。
    expect(html).toContain(NET_COST_GROUP_TITLE);
    expect(html).toContain(buildBeatCountSentence(80, 50, 5));
    expect(html).toContain(buildAverageSentence(0.5));
    const level = computeConfidenceLevelPercent(3);
    expect(html).toContain(buildWilsonIntervalSentence(level, 0.55, 0.7));
    expect(html).toContain(buildBootstrapIntervalSentence(level, 0.54, 0.71));
    // 組 2（未扣成本）——與組 1 的內容不同，證明沒有混用口徑。
    expect(html).toContain(GROSS_COST_GROUP_TITLE);
    expect(html).toContain(buildBeatCountSentence(80, 52, 5));
    expect(html).toContain(buildAverageSentence(0.45));
    // 組 2 不含區間句（規格只要求組 1 有 Wilson／bootstrap 兩列）。「未扣成本」
    // 這個子字串也出現在 DISPLAY_THRESHOLD_RULE_SENTENCE 裡（「須高於未扣成本
    // 的全部族群平均...」），所以要找組 2 標題自己的（最後一次）出現位置。
    const grossIndex = html.lastIndexOf(GROSS_COST_GROUP_TITLE);
    expect(html.slice(grossIndex)).not.toContain("區間（");
    expect(html).toContain("本統計另做過時間平移對照");
    expect(html).not.toContain("歷史統計尚未建立");
  });

  // The banned literals are assembled from parts: repo-wide Kelly wording scans
  // (backend tests/test_kelly_wording.py, condition 7) forbid them anywhere in
  // shipped sources, test files included.
  const BANNED_LITERALS = [["信賴", "區間"], ["信心", "水準"], ["信賴", "水準"], ["95% ", "CI"]].map((parts) =>
    parts.join(""),
  );

  // 風控 suggested（§14.2 附帶意見）：禁用字掃描不只 passed，failed／
  // not_evaluated／insufficient_data 各渲染一個狀態都要掃到。
  it("§14-2 required：畫面上不得出現落地條件 7 禁用字面與固定 95% 的區間標示（passed）", () => {
    const html = render(
      makeResponse({
        gate_status: "passed",
        not_evaluated_reason: null,
        not_evaluated_reasons: [],
        historical_stat: historicalStat(),
      }),
    );
    for (const banned of BANNED_LITERALS) {
      expect(html).not.toContain(banned);
    }
  });

  it("§14-2 suggested：畫面上不得出現落地條件 7 禁用字面（failed）", () => {
    const html = render(
      makeResponse({
        gate_status: "failed",
        not_evaluated_reason: null,
        not_evaluated_reasons: [],
        historical_stat: historicalStat(),
      }),
    );
    for (const banned of BANNED_LITERALS) {
      expect(html).not.toContain(banned);
    }
  });

  it("§14-2 suggested：畫面上不得出現落地條件 7 禁用字面（not_evaluated）", () => {
    const html = render(makeResponse()); // 預設 gate_status: not_evaluated
    for (const banned of BANNED_LITERALS) {
      expect(html).not.toContain(banned);
    }
  });

  it("§14-2 suggested：畫面上不得出現落地條件 7 禁用字面（insufficient_data）", () => {
    const html = render(
      makeResponse({
        status: "insufficient_data",
        insufficient_reason: "as_of_unknown",
        reason: "本卡未取得全市場收盤資料的日期，無法標示資料時間；因此也無法判斷這份資料距今多久。本次不呈現族群動能排行。",
        sectors: [],
        excluded_sectors: [],
        historical_stat: null,
        gate_checks: null,
      }),
    );
    for (const banned of BANNED_LITERALS) {
      expect(html).not.toContain(banned);
    }
  });

  it("passed：主視圖完整比例句", () => {
    const html = render(
      makeResponse({
        gate_status: "passed",
        not_evaluated_reason: null,
        not_evaluated_reasons: [],
        historical_stat: historicalStat(),
      }),
    );
    expect(html).toContain(buildPassedMainSentence(historicalStat(), 5));
  });

  it("holding_days=20：passed 主視圖句換成「其後 20 個交易日」，不與 lookback 的 5 混用", () => {
    const html = render(
      makeResponse({
        gate_status: "passed",
        not_evaluated_reason: null,
        not_evaluated_reasons: [],
        lookback_days: 5,
        holding_days: 20,
        historical_stat: historicalStat(),
      }),
    );
    expect(html).toContain("其後 20 個交易日");
    expect(html).not.toContain("其後 5 個交易日");
    expect(html).toContain("近 5 日"); // lookback stays 5 independently
  });

  it("lookback_days=20：chip、成分股表頭、not_evaluated 句同步換窗", () => {
    // disclosures 清空：這裡只驗證前端自己代入 lookback_days 的位置（chip／
    // 表頭／not_evaluated 句），後端 disclosures 是否已代入不是本測試範圍
    // （後端自己的逐字測試見 test_api_sectors_wording.py）。
    const html = render(
      makeResponse({
        lookback_days: 20,
        holding_days: 20,
        gate_status: "not_evaluated",
        not_evaluated_reason: "accumulating",
        not_evaluated_reasons: ["accumulating"],
        disclosures: [],
      }),
    );
    expect(html).toContain("近 20 日");
    expect(html).not.toContain("近 5 日");
    expect(html).toContain("依近 20 日漲跌幅");
  });
});

describe("SectorMomentumCardView — 整卡不足五種原因（各一個獨立案例，T-27）", () => {
  const reasons: { insufficient_reason: SectorMomentumResponse["insufficient_reason"]; reason: string }[] = [
    { insufficient_reason: "as_of_unknown", reason: "本卡未取得全市場收盤資料的日期，無法標示資料時間；因此也無法判斷這份資料距今多久。本次不呈現族群動能排行。" },
    { insufficient_reason: "ex_dividend_feed_gap", reason: "系統保存的除權息公告未涵蓋近 5 個交易日，無法確認哪些個股需排除，本次不呈現族群動能排行。" },
    { insufficient_reason: "overall_completeness_low", reason: "全市場資料完整率 90.0%，低於 98%（900 檔中缺漏 90 檔），本次不呈現族群動能排行。" },
    { insufficient_reason: "computable_ratio_low", reason: "近 5 日遇除權息或減資等事件而暫不計入的個股較多，全市場可計算比例 70.0%，低於 80%，本次不呈現族群動能排行。" },
    { insufficient_reason: "no_sector_computable", reason: "本次所有官方產業分類的族群皆未達列入排行的標準，不呈現族群動能排行。" },
  ];

  const NE_MAIN_SENTENCES = [
    "歷史統計尚未建立，本排行僅描述近 5 日的相對強弱。",
    "交易成本費率尚未查證，本排行僅描述近 5 日的相對強弱。",
    "歷史統計已超過 20 個交易日未重新計算，本排行僅描述近 5 日的相對強弱。",
    "排行版本與歷史統計版本不一致，本排行僅描述近 5 日的相對強弱。",
    "歷史統計所用資料未通過品質檢查，本排行僅描述近 5 日的相對強弱。",
    "歷史統計未通過資料偏誤檢查，本排行僅描述近 5 日的相對強弱。",
    "示範資料不計算歷史統計。",
    "歷史統計尚待風控複審，本排行僅描述近 5 日的相對強弱。",
    "歷史統計未達門檻，本排行僅描述近 5 日的相對強弱。",
  ];

  for (const { insufficient_reason, reason } of reasons) {
    it(`${insufficient_reason}：InsufficientPanel 帶入非 null reason，不渲染任何排名／族群名稱／成分股／NE 主視圖句`, () => {
      const html = render(
        makeResponse({
          status: "insufficient_data",
          insufficient_reason,
          reason,
          sectors: [],
          excluded_sectors: [],
          gate_status: "not_evaluated",
          not_evaluated_reason: "accumulating",
          not_evaluated_reasons: ["accumulating"],
          historical_stat: null,
          gate_checks: null,
          disclosures: ["（本原因對應的詳細句，僅供測試）"],
        }),
      );
      expect(html).toContain(reason);
      expect(html).not.toContain("資料不足，無法計算。");
      // IP-5: no sector name from the fixture leaks through.
      expect(html).not.toContain("半導體業");
      expect(html).not.toContain("2330");
      // S-5：整卡不足時，任何 NE 主視圖句都不得出現（IP-5：不出現任何歷史句）。
      for (const sentence of NE_MAIN_SENTENCES) {
        expect(html).not.toContain(sentence);
      }
    });
  }

  it("F-1（風控 ALL-1 複審裁定）：status = insufficient_data 但 reason 為 null 時改走 ErrorPanel，不渲染退回字面", () => {
    const html = render(
      makeResponse({
        status: "insufficient_data",
        insufficient_reason: "as_of_unknown",
        reason: null,
        sectors: [],
        excluded_sectors: [],
        historical_stat: null,
        gate_checks: null,
      }),
    );
    expect(html).toContain("族群動能排行：");
    expect(html).not.toContain("資料不足，無法計算。");
    expect(html).not.toContain("insufficient_data 但 reason 為 null"); // S-4：內部除錯訊息不得外洩到畫面
  });

  it("IP-6：不足狀態仍常駐「資料截至」徽章與「僅上市」tag", () => {
    const html = render(
      makeResponse({
        status: "insufficient_data",
        insufficient_reason: "no_sector_computable",
        reason: "本次所有官方產業分類的族群皆未達列入排行的標準，不呈現族群動能排行。",
        sectors: [],
        excluded_sectors: [],
        historical_stat: null,
        gate_checks: null,
      }),
    );
    expect(html).toContain("資料截至");
    expect(html).toContain("僅上市");
  });
});

describe("SectorMomentumCardView — held 為 null（H-2）", () => {
  it("成分股 held 為 null 時不渲染徽章，主視圖顯示列示順序句", () => {
    const sectors = [
      sector({
        constituents: [
          constituent({ symbol: "2330", name: "台積電", held: null }),
          constituent({ symbol: "2454", name: "聯發科", held: false }),
          constituent({ symbol: "3034", name: "聯詠", held: false }),
        ],
      }),
    ];
    const html = render(makeResponse({ sectors, headline_count: 3 }));
    expect(html).toContain(buildListingOrderSentence(5));
  });

  it("held 全部已知時不需要列示順序句被拉回主視圖以外的次數增加（仍可能出現在詳細常駐句中）", () => {
    const html = render(makeResponse());
    const collapsed = stripDetails(html);
    // held 全部為 boolean（非 null）時，collapsed 區不應出現「列示順序」句。
    expect(collapsed).not.toContain("列示順序僅依近 5 日漲跌幅");
  });
});

describe("SectorMomentumCardView — 示範資料（ok 與不足態）", () => {
  it("data_source = demo_synthetic 且 status = ok：卡片層級警告常駐，且 gate_status 為 not_evaluated/demo_data", () => {
    const html = render(
      makeResponse({
        data_source: "demo_synthetic",
        gate_status: "not_evaluated",
        not_evaluated_reason: "demo_data",
        not_evaluated_reasons: ["demo_data"],
      }),
    );
    expect(html).toContain(DEMO_DATA_CARD_WARNING);
  });

  it("data_source = demo_synthetic 且 status = insufficient_data：警告仍常駐（IP-6）", () => {
    const html = render(
      makeResponse({
        data_source: "demo_synthetic",
        status: "insufficient_data",
        insufficient_reason: "as_of_unknown",
        reason: "本卡未取得全市場收盤資料的日期，無法標示資料時間；因此也無法判斷這份資料距今多久。本次不呈現族群動能排行。",
        sectors: [],
        excluded_sectors: [],
        historical_stat: null,
        gate_checks: null,
      }),
    );
    expect(html).toContain(DEMO_DATA_CARD_WARNING);
  });
});

describe("SectorMomentumCardView — 未知碼改走 ErrorPanel（R-4 required）", () => {
  it("not_evaluated 但 not_evaluated_reason 為 null 時改走 ErrorPanel，不照常顯示排行", () => {
    const html = render(
      makeResponse({
        gate_status: "not_evaluated",
        not_evaluated_reason: null,
        not_evaluated_reasons: [],
      }),
    );
    expect(html).toContain("族群動能排行：");
    expect(html).not.toContain("半導體業");
    // S-4：ErrorPanel 只用既有「未知錯誤」字面，內部除錯訊息不得外洩到畫面。
    expect(html).toContain("未知錯誤");
    expect(html).not.toContain("gate_status 或 not_evaluated_reason 無法辨識");
  });

  it("not_evaluated_reason 是不認得的碼時改走 ErrorPanel", () => {
    const html = render(
      makeResponse({
        gate_status: "not_evaluated",
        not_evaluated_reason: "some_unknown_code" as unknown as SectorNotEvaluatedReason,
        not_evaluated_reasons: ["some_unknown_code" as unknown as SectorNotEvaluatedReason],
      }),
    );
    expect(html).toContain("族群動能排行：");
    expect(html).not.toContain("半導體業");
    expect(html).toContain("未知錯誤");
  });

  it("gate_status 本身不認得時改走 ErrorPanel", () => {
    const html = render(
      makeResponse({
        gate_status: "weird_status" as unknown as SectorMomentumResponse["gate_status"],
        not_evaluated_reason: null,
        not_evaluated_reasons: [],
      }),
    );
    expect(html).toContain("族群動能排行：");
    expect(html).not.toContain("半導體業");
    expect(html).toContain("未知錯誤");
  });

  it("passed 卻沒有 historical_stat 時改走 ErrorPanel（契約破壞防呆）", () => {
    const html = render(
      makeResponse({
        gate_status: "passed",
        not_evaluated_reason: null,
        not_evaluated_reasons: [],
        historical_stat: null,
      }),
    );
    expect(html).toContain("族群動能排行：");
    expect(html).not.toContain("半導體業");
  });

  it("S-2：excluded_sectors 出現不認得的 reason_code 時改走 ErrorPanel，不自行造原因文案", () => {
    const html = render(
      makeResponse({
        excluded_sectors: [
          {
            sector_code: "99",
            sector_name: "神秘產業",
            reason_code: "totally_unknown_reason" as unknown as SectorReasonCode,
            computable_count: 1,
            expected_count: 2,
            coverage: coverage(),
          },
        ],
      }),
    );
    expect(html).toContain("族群動能排行：");
    expect(html).toContain("未知錯誤");
    expect(html).not.toContain("神秘產業");
    expect(html).not.toContain("半導體業");
  });
});

describe("SectorMomentumCardView — 預設顯示 3 個族群（headline_count）", () => {
  it("收合態只顯示前 3 名，第 4 名只出現在「詳細」的完整排行", () => {
    const html = render(makeResponse());
    const collapsed = stripDetails(html);
    const details = detailsHtmlOf(html);
    expect(collapsed).toContain("半導體業");
    expect(collapsed).toContain("其他電子業");
    expect(collapsed).toContain("化學工業");
    expect(collapsed).not.toContain("塑膠工業");
    expect(details).toContain("塑膠工業");
  });

  it("headline_count 由 API 決定，前端照用（此處驗證 3）", () => {
    const html = render(makeResponse());
    expect(html).toContain("上漲 6／8 家"); // sector 1
    expect(html).toContain("上漲 4／7 家"); // sector 2
    expect(html).toContain("上漲 3／6 家"); // sector 3
  });
});

describe("SectorMomentumCardView — 族群層級缺漏 tag（風控 ALL-1 複審裁定）", () => {
  it("sectors[].coverage.missing_count > 0 時，主視圖與詳細都在成分股表頭同一行顯示，且不取自 market_missing_count", () => {
    const sectors = [
      sector({ sector_code: "24", sector_name: "半導體業", coverage: coverage({ missing_count: 4 }) }),
      sector({ sector_code: "20", sector_name: "其他電子業", coverage: coverage({ missing_count: 0 }) }),
      sector({ sector_code: "12", sector_name: "化學工業", coverage: coverage({ missing_count: 0 }) }),
    ];
    const html = render(
      makeResponse({ sectors, headline_count: 3, market_missing_count: 999 /* 刻意設不同值，證明未混用 */ }),
    );
    // 族群層級的 4 檔要出現（主視圖，headline 就含這個族群）。
    expect(html).toContain("缺 4 檔資料");
    // 市場層級的 tag（絕對底線，market_missing_count 綁定）各自獨立仍照常顯示
    // 一次（卡片標題列），兩個 tag 同一份回應各自綁自己的數字，互不混用。
    expect(html.match(/缺 999 檔資料/g)?.length).toBe(1);
    // 沒有缺漏的另外兩個族群不應該各自多印一個「缺 0 檔資料」。
    expect(html.match(/缺 0 檔資料/g)).toBeNull();
  });

  it("完整排行（詳細）也要顯示族群層級缺漏 tag（不只主視圖 headline）", () => {
    const sectors = [
      ...FOUR_SECTORS.slice(0, 3),
      sector({
        sector_code: "08",
        sector_name: "塑膠工業",
        coverage: coverage({ missing_count: 2 }),
      }),
    ];
    const html = render(makeResponse({ sectors, headline_count: 3 }));
    const details = detailsHtmlOf(html);
    expect(details).toContain("塑膠工業");
    expect(details).toContain("缺 2 檔資料");
  });
});

describe("SectorMomentumCardView — §6.2(d) 加權指數參考數字（風控 ALL-1 複審裁定）", () => {
  const TAIEX_REFERENCE_SENTENCE =
    "加權指數報酬僅供參考，不用於排名或歷史比例的判定；兩者一律以等權全市場為基準。" +
    "加權指數以市值加權且不含股利，與等權全市場不可直接比較。";

  it("整卡只顯示一次，位置緊接在 §6.2(d) 揭露句之前，且只出現在「詳細」內", () => {
    const html = render(
      makeResponse({
        disclosures: [
          "本排行以全市場盤後日線計算，非即時資料；資料截至日之後的市場變動未反映在排行中。",
          TAIEX_REFERENCE_SENTENCE,
        ],
      }),
    );
    const numberLine = "加權指數（近 5 日，僅供參考）：+1.5%";
    // 只出現一次。
    expect(html.match(/加權指數（近 5 日，僅供參考）：/g)?.length).toBe(1);
    // 緊接在揭露句之前。
    const numberIndex = html.indexOf(numberLine);
    const sentenceIndex = html.indexOf(TAIEX_REFERENCE_SENTENCE);
    expect(numberIndex).toBeGreaterThan(-1);
    expect(sentenceIndex).toBeGreaterThan(numberIndex);
    // 只在「詳細」內，主視圖看不到。
    const collapsed = stripDetails(html);
    expect(collapsed).not.toContain(numberLine);
    // 不落在任何單一族群的區塊（3 個族群名稱都不與這行相鄰在同一個 rounded-md 卡片內）。
    expect(html.indexOf(numberLine)).toBeLessThan(html.indexOf("完整排行"));
  });

  it("沒有揭露句時（has_taiex_reference 為 false）不顯示，即使 sectors 帶了數字", () => {
    const html = render(makeResponse()); // 預設 disclosures 沒有 TAIEX_REFERENCE_SENTENCE
    expect(html).not.toContain("加權指數（近 5 日，僅供參考）：");
  });
});

describe("SectorMomentumCardView — §14-1 族群相對報酬／族群報酬／等權全市場報酬", () => {
  it("主視圖與詳細完整排行同句式：數字來自 rel_return_L，不是 sector_return_L", () => {
    const sectors = [
      sector({
        sector_code: "24",
        sector_name: "半導體業",
        sector_return_L: 0.099, // 刻意與 rel_return_L 不同，證明沒有誤配
        rel_return_L: 0.022,
        benchmark_return_L: 0.01,
      }),
    ];
    const html = render(makeResponse({ sectors, headline_count: 1 }));
    const relativeSentence = buildRelativeReturnSentence(0.022, 5);
    expect(relativeSentence).toBe("+2.2 個百分點（近 5 日／相對等權全市場）");
    // 主視圖與「詳細」都要看到同一句（headline 與完整排行各出現一次）。
    expect(html.match(new RegExp(relativeSentence.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"))?.length).toBe(2);
    expect(html).not.toContain("+9.9 個百分點");
  });

  it("族群報酬（sector_return_L）只出現在「詳細」完整排行，不出現在主視圖", () => {
    const sectors = [sector({ sector_code: "24", sector_name: "半導體業", sector_return_L: 0.032 })];
    const html = render(makeResponse({ sectors, headline_count: 1 }));
    const sentence = buildSectorReturnSentence(0.032, 5);
    const collapsed = stripDetails(html);
    expect(collapsed).not.toContain(sentence);
    expect(detailsHtmlOf(html)).toContain(sentence);
  });

  it("等權全市場報酬（benchmark_return_L）整卡只顯示一次，放在「完整排行」小標之後、族群清單之前", () => {
    const html = render(makeResponse()); // FOUR_SECTORS 全部 benchmark_return_L = 0.01（一致）
    const sentence = buildBenchmarkReturnSentence(0.01, 5);
    expect(html.match(new RegExp(sentence.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g"))?.length).toBe(1);
    const details = detailsHtmlOf(html);
    const fullRankingIndex = details.indexOf("完整排行");
    const sentenceIndex = details.indexOf(sentence);
    const firstSectorIndex = details.indexOf("半導體業", fullRankingIndex);
    expect(sentenceIndex).toBeGreaterThan(fullRankingIndex);
    expect(sentenceIndex).toBeLessThan(firstSectorIndex);
    // 主視圖看不到。
    expect(stripDetails(html)).not.toContain(sentence);
  });

  it("同一回應中各族群 benchmark_return_L 不相等時改走 ErrorPanel", () => {
    const sectors = [
      sector({ sector_code: "24", sector_name: "半導體業", benchmark_return_L: 0.01 }),
      sector({ sector_code: "20", sector_name: "其他電子業", benchmark_return_L: 0.02 }),
    ];
    const html = render(makeResponse({ sectors, headline_count: 2 }));
    expect(html).toContain("族群動能排行：");
    expect(html).toContain("未知錯誤");
    expect(html).not.toContain("半導體業");
  });
});

describe("SectorMomentumCardView — §14-3 單一個股集中", () => {
  it("主視圖該族群區塊內顯示 tag，「詳細」完整排行該族群區塊內顯示說明句", () => {
    const sectors = [
      sector({
        sector_code: "24",
        sector_name: "半導體業",
        single_stock_dominated: true,
        top_contributor_share: 0.351,
      }),
      sector({ sector_code: "20", sector_name: "其他電子業", single_stock_dominated: false }),
    ];
    const html = render(makeResponse({ sectors, headline_count: 2 }));
    // 主視圖：tag 出現在收合態。
    const collapsed = stripDetails(html);
    expect(collapsed).toContain(SINGLE_STOCK_DOMINATED_TAG);
    // 詳細完整排行：說明句出現。
    const sentence = buildSingleStockDominatedSentence(0.351, 5);
    expect(detailsHtmlOf(html)).toContain(sentence);
    // 沒有 single_stock_dominated 的族群不應該印出這個 tag／句子。
    expect(html.match(new RegExp(SINGLE_STOCK_DOMINATED_TAG, "g"))?.length).toBe(2); // headline + 完整排行各一次（同一族群）
  });
});

describe("SectorMomentumCardView — §14-4 取樣規則標籤", () => {
  it("status=ok 且至少渲染一個族群時，主視圖卡片層級一次（放在第一個族群區塊正上方），字級不小於 text-sm", () => {
    const html = render(makeResponse());
    const collapsed = stripDetails(html);
    expect(collapsed).toContain(SAMPLING_RULE_LABEL);
    const match = collapsed.match(/<p class="([^"]*)">每族群僅列漲跌幅最大/);
    expect(match).not.toBeNull();
    expect(match?.[1]).not.toContain("text-xs");
    // 緊接在第一個族群區塊（半導體業）正上方。
    const labelIndex = collapsed.indexOf(SAMPLING_RULE_LABEL);
    const firstSectorIndex = collapsed.indexOf("半導體業");
    expect(labelIndex).toBeGreaterThan(-1);
    expect(firstSectorIndex).toBeGreaterThan(labelIndex);
  });

  it("「詳細」的「完整排行」小標下也放一次", () => {
    const html = render(makeResponse());
    const details = detailsHtmlOf(html);
    const fullRankingIndex = details.indexOf("完整排行");
    const labelIndex = details.indexOf(SAMPLING_RULE_LABEL, fullRankingIndex);
    expect(labelIndex).toBeGreaterThan(fullRankingIndex);
  });

  it("整卡不足（無族群可渲染）時不顯示取樣規則標籤", () => {
    const html = render(
      makeResponse({
        status: "insufficient_data",
        insufficient_reason: "as_of_unknown",
        reason: "本卡未取得全市場收盤資料的日期，無法標示資料時間；因此也無法判斷這份資料距今多久。本次不呈現族群動能排行。",
        sectors: [],
        excluded_sectors: [],
        historical_stat: null,
        gate_checks: null,
      }),
    );
    expect(html).not.toContain(SAMPLING_RULE_LABEL);
  });
});

describe("SectorMomentumCardView — 字級不低於正文（F-4）", () => {
  it("成分股表頭與 H-2 列示順序句不得用 text-xs（正文為 text-sm）", () => {
    const sectors = [
      sector({
        constituents: [
          constituent({ symbol: "2330", name: "台積電", held: null }),
          constituent({ symbol: "2454", name: "聯發科", held: false }),
          constituent({ symbol: "3034", name: "聯詠", held: false }),
        ],
      }),
    ];
    const html = render(makeResponse({ sectors, headline_count: 1 }));
    // 成分股表頭所在的 <p> 不使用 text-xs。
    const headerMatch = html.match(/<p class="[^"]*"><span>成分股（依近 5 日漲跌幅[^<]*<\/span>/);
    expect(headerMatch).not.toBeNull();
    expect(headerMatch?.[0]).not.toContain("text-xs");
    expect(headerMatch?.[0]).toContain("text-sm");
    // H-2 列示順序句同樣不得用 text-xs。
    const listingOrderMatch = html.match(/<p class="[^"]*">列示順序僅依近 5 日漲跌幅/);
    expect(listingOrderMatch).not.toBeNull();
    expect(listingOrderMatch?.[0]).not.toContain("text-xs");
  });
});

describe("SectorMomentumCardView — S-1：「詳細」展開後先放後端 disclosures 再放完整排行", () => {
  it("disclosures 的文字出現在「完整排行」標籤之前", () => {
    const html = render(makeResponse());
    const details = detailsHtmlOf(html);
    const disclosureIndex = details.indexOf("本排行與歷史比例僅為歷史統計描述");
    const fullRankingIndex = details.indexOf("完整排行");
    expect(disclosureIndex).toBeGreaterThan(-1);
    expect(fullRankingIndex).toBeGreaterThan(-1);
    expect(disclosureIndex).toBeLessThan(fullRankingIndex);
  });
});

/**
 * §14.6 CEO 字數重訂（2026-09-26）supersedes the 185 of §14.5: 恆常項目上限 205 字
 * （依 PRD AC-1 計數法重量後）。§14.5 原文：恆常項目上限由 170 字調為 185
 * 字；預設仍顯示 3 個族群。**全部八項條件式底線**觸發時各自另計，不計入
 * 185 字基準，也不得以此壓縮、刪減或弱化任何一項：
 *   1. NE-8 示範資料警告；2. 卡片層級除權息 tag；3. 卡片層級「缺 {m} 檔資
 *   料」tag；4. §4.5-3 資料過舊句；5. §4.5-4 交易日曆無法確認句；6. §6.3
 *   H-2 列示順序句；7. 族群層級「缺 {m} 檔資料」tag；8. 單一個股集中 tag。
 * 第 4、5 項互斥（`trading_days_behind` 不可能同時 ≥ 1 與為 null），最壞情
 * 境因此是其餘七項全觸發、第 4／5 項取較長的第 4 項（§14.5 原文）。
 * - 「一般情境」：八項皆未觸發，斷言 ≤205 字（§14.6），並逐項斷言確實未觸發，避免
 *   fixture 日後漂移而讓測試失去意義。
 * - 「最壞情境」：七項全部觸發，只印出實測字數供 qa-e2e 參考，不設斷言上
 *   限（coordinator 明確要求「不設斷言上限，但要印出數字」）。
 */
function collapsedVisibleCharCount(html: string, namesToStrip: string[]): number {
  const collapsed = stripDetails(html);
  const text = collapsed.replace(/<[^>]+>/g, "");
  let stripped = text;
  for (const name of namesToStrip) stripped = stripped.split(name).join("");
  // AC-1（`work/stock-desk-族群動能-PRD.md` 約 679～681 行）：只不含「族群名
  // 稱、個股代號名稱、報酬與家數數字本身」——只剝除下列三種數字符記，其餘數
  // 字（時間窗「近 5 日」、「共 n 檔」、日期、缺漏檔數等）一律計入：
  // (a) 每族群相對報酬 {sign}{value}（緊接在「個百分點」之前）；
  // (b) 個股報酬 {sign}{value}%；
  // (c) 「上漲 k／n 家」的 k、n（家數）。
  stripped = stripped.replace(/[+-]\d+(\.\d+)?(?=\s*個百分點)/g, "");
  stripped = stripped.replace(/[+-]\d+(\.\d+)?%/g, "");
  stripped = stripped.replace(/上漲 \d+／\d+ 家/g, "上漲／家");
  stripped = stripped.replace(/\s+/g, "");
  return [...stripped].length;
}

const CHAR_COUNT_NAMES_TO_STRIP = ["半導體業", "其他電子業", "化學工業", "台積電", "聯發科", "聯詠", "2330", "2454", "3034"];

describe("SectorMomentumCardView — 收合態字數 ≤205 字（CEO 字數重訂 2026-09-26，§14.6，一般情境）", () => {
  it("典型 not_evaluated 情境（3 個族群、9 檔成分股，八項條件式底線皆未觸發）收合態可見文字 ≤205 字", () => {
    const data = makeResponse();
    // 逐項確認八項條件式底線確實未觸發，避免 fixture 日後漂移讓上限測試失去意義。
    expect(data.data_source).not.toBe("demo_synthetic"); // 1
    expect(data.ex_date_tag).toBe(false); // 2
    expect(data.market_missing_count).toBe(0); // 3
    expect(data.data.trading_days_behind).toBe(0); // 4（非 ≥ 1）
    expect(data.data.trading_days_behind).not.toBeNull(); // 5（非 null）
    expect(data.sectors.every((s) => s.constituents.every((c) => c.held !== null))).toBe(true); // 6
    expect(data.sectors.every((s) => s.coverage.missing_count === 0)).toBe(true); // 7
    expect(data.sectors.every((s) => s.single_stock_dominated === false)).toBe(true); // 8

    const html = render(data);
    const length = collapsedVisibleCharCount(html, CHAR_COUNT_NAMES_TO_STRIP);
    expect(length).toBeLessThanOrEqual(205);
  });
});

describe("SectorMomentumCardView — 收合態字數（最壞情境，七項條件式底線全部觸發，僅供 qa-e2e 參考）", () => {
  it("列印最壞情境實測字數（不設斷言上限）", () => {
    const sectors = [
      sector({
        sector_code: "24",
        sector_name: "半導體業",
        up_count: 6,
        constituent_count: 8,
        single_stock_dominated: true, // 第 8 項
        top_contributor_share: 0.351,
        coverage: coverage({ missing_count: 4 }), // 第 7 項
        constituents: [
          constituent({ symbol: "2330", name: "台積電", return_L: 0.05, held: null }), // 第 6 項
          constituent({ symbol: "2454", name: "聯發科", return_L: 0.04, held: false }),
          constituent({ symbol: "3034", name: "聯詠", return_L: -0.02, held: false }),
        ],
      }),
      sector({ sector_code: "20", sector_name: "其他電子業", up_count: 4, constituent_count: 7 }),
      sector({ sector_code: "12", sector_name: "化學工業", up_count: 3, constituent_count: 6 }),
    ];
    const html = render(
      makeResponse({
        sectors,
        headline_count: 3,
        data_source: "demo_synthetic", // 第 1 項
        gate_status: "not_evaluated",
        not_evaluated_reason: "demo_data",
        not_evaluated_reasons: ["demo_data"],
        ex_date_tag: true, // 第 2 項
        market_ex_date_excluded_count: 15,
        market_missing_count: 30, // 第 3 項
        data: {
          status: "cached_stale",
          source: "twse_snapshot",
          staleness_minutes: 30,
          is_within_ttl: false,
          bar_count: 5,
          first_bar_date: "2026-09-10",
          last_bar_date: "2026-09-17",
          trading_days_behind: 2, // 第 4 項（與第 5 項互斥，§14.5 取第 4 項）
          reason: null,
        },
      }),
    );
    const length = collapsedVisibleCharCount(html, CHAR_COUNT_NAMES_TO_STRIP);
    // eslint-disable-next-line no-console -- 供 qa-e2e 實機驗收參考，coordinator 明確要求印出數字。
    console.log(`[sector-momentum-card] 最壞情境（七項條件式底線全部觸發）收合態可見字數 = ${length}`);
    expect(length).toBeGreaterThan(0); // 只是確保量測本身有跑，不設字數上限。
  });
});
