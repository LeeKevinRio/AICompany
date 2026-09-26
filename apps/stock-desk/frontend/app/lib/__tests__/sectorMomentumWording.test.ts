/**
 * Verbatim guard for the sector-momentum card's own wording
 * (`sectorMomentumWording.ts`) — every sentence retyped fresh here (not
 * imported from the module under test for the literal comparison, so a typo
 * introduced in both places at once would still be caught) against
 * `work/stock-desk-族群動能-派工單.md` §13.5 (third-wave risk ruling), §4.6
 * CL-2 and §12. Mirrors the backend's own
 * `apps/stock-desk/backend/tests/test_api_sectors_wording.py` approach.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  assertNoForbiddenTerms,
  findBareRealtimeClaims,
} from "./wordingScanHelpers";
import { FRONTEND_FORBIDDEN_TERMS } from "../adviceWording";
import type { SectorAccumulation, SectorExcludedItem, SectorHistoricalStat } from "../types";
import {
  AVERAGE_SENTENCE_TEMPLATE,
  BEAT_COUNT_SENTENCE_TEMPLATE,
  BENCHMARK_RETURN_SENTENCE_TEMPLATE,
  BOOTSTRAP_INTERVAL_SENTENCE_TEMPLATE,
  buildAccumulationSentence,
  buildAverageSentence,
  buildBeatCountSentence,
  buildBenchmarkReturnSentence,
  buildBootstrapIntervalSentence,
  buildConstituentHeader,
  buildExDateTag,
  buildExclusionSentence,
  buildFailedMainSentence,
  buildListingOrderSentence,
  buildLookbackChip,
  buildMarketMissingTag,
  buildPassedMainSentence,
  buildPitGapSentence,
  buildRelativeReturnSentence,
  buildReturnWindowSentence,
  buildSectorMissingTag,
  buildSectorReturnSentence,
  buildSingleStockDominatedSentence,
  buildStaleDataSentence,
  buildStatsAsOfSentence,
  buildT82Sentence,
  buildTaiexReferenceLine,
  buildTurnoverRatioLabel,
  buildUpCountLabel,
  buildWilsonIntervalSentence,
  ceilRatioPercent,
  computeConfidenceLevelPercent,
  COST_DEFINITION_SENTENCE,
  DEMO_DATA_CARD_WARNING,
  DISPLAY_THRESHOLD_RULE_SENTENCE,
  formatPercentagePoints,
  formatRatioPercent,
  formatSignedPercent,
  formatSignedPoints,
  GROSS_COST_GROUP_TITLE,
  HISTORICAL_STAT_SECTOR_ONLY_SENTENCE,
  KNOWN_NOT_EVALUATED_REASONS,
  KNOWN_SECTOR_REASON_CODES,
  NET_COST_GROUP_TITLE,
  notEvaluatedSentences,
  RELATIVE_RETURN_SENTENCE_TEMPLATE,
  SAMPLING_RULE_LABEL,
  SECTOR_CARD_TITLE,
  SECTOR_HELD_BADGE,
  SECTOR_NOT_HELD_BADGE,
  SECTOR_RETURN_SENTENCE_TEMPLATE,
  SINGLE_STOCK_DOMINATED_SENTENCE_TEMPLATE,
  SINGLE_STOCK_DOMINATED_TAG,
  T8_1_SENTENCE,
  thresholdPercent,
  TWSE_ONLY_TAG,
  WILSON_INTERVAL_SENTENCE_TEMPLATE,
  withHoldingDays,
  withLookback,
} from "../sectorMomentumWording";

/** `work/stock-desk-族群動能-派工單.md`，供 §14 逐字掃描測試讀取。 */
const DISPATCH_ORDER_PATH = fileURLToPath(
  new URL("../../../../../../work/stock-desk-族群動能-派工單.md", import.meta.url),
);

function stat(overrides: Partial<SectorHistoricalStat> = {}): SectorHistoricalStat {
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

function accumulation(overrides: Partial<SectorAccumulation> = {}): SectorAccumulation {
  return { accumulated_samples: 12, accumulation_start: "2026-01-05", required_samples: 150, ...overrides };
}

describe("sectorMomentumWording — §4.6 CL-2 / §12 標題與常駐 tag 定稿", () => {
  it("卡片標題", () => {
    expect(SECTOR_CARD_TITLE).toBe("族群動能排行");
  });

  it("時間窗 chip", () => {
    expect(buildLookbackChip(5)).toBe("近 5 日");
    expect(buildLookbackChip(20)).toBe("近 20 日");
  });

  it("§12 CEO 核可第 2 項：僅上市 tag", () => {
    expect(TWSE_ONLY_TAG).toBe("僅上市");
  });

  it("成分股表頭", () => {
    expect(buildConstituentHeader(5, 8)).toBe("成分股（依近 5 日漲跌幅，共 8 檔）");
    expect(buildConstituentHeader(20, 8)).toBe("成分股（依近 20 日漲跌幅，共 8 檔）");
  });

  it("上漲家數", () => {
    expect(buildUpCountLabel(6, 8)).toBe("上漲 6／8 家");
  });

  it("持有徽章字面", () => {
    expect(SECTOR_NOT_HELD_BADGE).toBe("未持有");
    expect(SECTOR_HELD_BADGE).toBe("持有中");
  });
});

describe("sectorMomentumWording — §4.4-2／§8-1／§4.5-3 常駐 tag 與句子", () => {
  it("缺 {m} 檔資料", () => {
    expect(buildMarketMissingTag(30)).toBe("缺 30 檔資料");
  });

  it("除權息排除 {m} 檔", () => {
    expect(buildExDateTag(15)).toBe("除權息排除 15 檔");
  });

  it("資料過舊定稿句", () => {
    expect(buildStaleDataSentence("2026-09-18", 2)).toBe(
      "本排行所依據的全市場收盤資料為 2026-09-18，距今已 2 個交易日未更新，排行不代表最新市況。",
    );
  });

  it("NE-8 卡片層級常駐警告", () => {
    expect(DEMO_DATA_CARD_WARNING).toBe("警告：本卡使用的是離線示範資料（demo_synthetic），不是市場資料。");
  });

  it("§4.1e／§6.3 H-2 列示順序句", () => {
    expect(buildListingOrderSentence(5)).toBe("列示順序僅依近 5 日漲跌幅，不代表任何優先順序。");
    expect(buildListingOrderSentence(20)).toBe("列示順序僅依近 20 日漲跌幅，不代表任何優先順序。");
  });
});

describe("sectorMomentumWording — 族群層級缺漏 tag（風控 ALL-1 複審裁定，2026-09-25）", () => {
  it("同一文字「缺 {m} 檔資料」，但函式與市場層級各自獨立，綁定不同欄位", () => {
    expect(buildSectorMissingTag(4)).toBe("缺 4 檔資料");
    // 兩個 tag 同一份回應下各自綁定不同數字來源：市場層級 30 檔、族群層級 4 檔。
    expect(buildMarketMissingTag(30)).toBe("缺 30 檔資料");
    expect(buildSectorMissingTag(4)).not.toBe(buildMarketMissingTag(30));
  });
});

describe("sectorMomentumWording — §6.2(d) 加權指數參考數字（風控 ALL-1 複審裁定）", () => {
  it("字面核可＋formatSignedPercent（整卡只顯示一次，見元件測試）", () => {
    expect(buildTaiexReferenceLine(0.015, 5)).toBe("加權指數（近 5 日，僅供參考）：+1.5%");
    expect(buildTaiexReferenceLine(-0.008, 20)).toBe("加權指數（近 20 日，僅供參考）：-0.8%");
  });
});

describe("sectorMomentumWording — §14-1 族群相對報酬（rel_return_L，主視圖與詳細同句式）", () => {
  it("formatSignedPoints：{sign}{value}，不含 % 或「個百分點」後綴，0 顯示 +0.0", () => {
    expect(formatSignedPoints(0.022)).toBe("+2.2");
    expect(formatSignedPoints(-0.018)).toBe("-1.8");
    expect(formatSignedPoints(0)).toBe("+0.0");
  });

  it("buildRelativeReturnSentence：{sign}{value} 個百分點（近 5 日／相對等權全市場）", () => {
    expect(buildRelativeReturnSentence(0.022, 5)).toBe("+2.2 個百分點（近 5 日／相對等權全市場）");
    expect(buildRelativeReturnSentence(-0.031, 20)).toBe("-3.1 個百分點（近 20 日／相對等權全市場）");
    expect(buildRelativeReturnSentence(0, 5)).toBe("+0.0 個百分點（近 5 日／相對等權全市場）");
  });

  it("buildSectorReturnSentence（詳細逐族群，sector_return_L，% 呈現）", () => {
    expect(buildSectorReturnSentence(0.032, 5)).toBe("族群報酬（近 5 日）：+3.2%");
    expect(buildSectorReturnSentence(-0.01, 20)).toBe("族群報酬（近 20 日）：-1.0%");
  });

  it("buildBenchmarkReturnSentence（詳細整卡一次，benchmark_return_L，% 呈現）", () => {
    expect(buildBenchmarkReturnSentence(0.01, 5)).toBe("等權全市場報酬（近 5 日）：+1.0%");
  });
});

describe("sectorMomentumWording — §6.1 not_evaluated 原因句（每碼各一個單獨案例）", () => {
  it("每一個已知碼都有對應句", () => {
    expect(KNOWN_NOT_EVALUATED_REASONS).toHaveLength(9);
  });

  it("NE-1 pit_history_missing：句 1 + 句 G（缺口非空）+ 句 2 + 句 3", () => {
    const { main, detail } = notEvaluatedSentences({
      reason: "pit_history_missing",
      lookbackDays: 5,
      pitGaps: ["pit_universe", "pit_classification", "pit_ex_dividend", "de5_unverified"],
      accumulation: accumulation({ accumulation_start: "2026-01-05", accumulated_samples: 7 }),
    });
    expect(main).toBe("歷史統計尚未建立，本排行僅描述近 5 日的相對強弱。");
    expect(detail).toEqual([
      "本卡目前不提供歷史比例。系統開始逐日保存資料以前的期間，已下市個股資料、當時的產業分類與除權息紀錄皆無可用來源，以那段期間回推的結果會有無法估計幅度的系統性偏誤，因此不予使用。",
      "目前仍待補齊：當時上市名單（含其後下市個股）的逐日保存、當時產業分類的逐日保存、除權息紀錄的逐日保存、除權息還原所需參考價欄位的定義查證；補齊前不進行門檻判定。",
      "自 2026-01-05 起，系統逐日保存當時的上市名單、產業分類與除權息公告；累積滿 150 個不重疊的 5 日樣本後才進行門檻判定，依每年約 49 個樣本估算約需 3 年，目前已累積 7 個。",
      "本排行的族群依臺灣證券交易所目前公布的產業分類，僅含上市普通股。",
    ]);
  });

  it("NE-1 缺口只有部分成立時，缺口清單依固定順序只列成立者", () => {
    expect(buildPitGapSentence(["pit_classification", "de5_unverified"])).toBe(
      "目前仍待補齊：當時產業分類的逐日保存、除權息還原所需參考價欄位的定義查證；補齊前不進行門檻判定。",
    );
  });

  it("accumulation_start 為 null 時用句 2'", () => {
    expect(buildAccumulationSentence(accumulation({ accumulation_start: null, accumulated_samples: 0 }))).toBe(
      "系統尚未開始逐日保存上述資料，目前已累積 0 個樣本。",
    );
  });

  it("NE-2 accumulating：句 1（無句 G）+ 句 2 + 句 3", () => {
    const { main, detail } = notEvaluatedSentences({
      reason: "accumulating",
      lookbackDays: 5,
      pitGaps: [],
      accumulation: accumulation({ accumulation_start: "2026-01-05", accumulated_samples: 20 }),
    });
    expect(main).toBe("歷史統計尚未建立，本排行僅描述近 5 日的相對強弱。");
    expect(detail).toEqual([
      "本卡目前不提供歷史比例。系統開始逐日保存資料以前的期間，已下市個股資料、當時的產業分類與除權息紀錄皆無可用來源，以那段期間回推的結果會有無法估計幅度的系統性偏誤，因此不予使用。",
      "自 2026-01-05 起，系統逐日保存當時的上市名單、產業分類與除權息公告；累積滿 150 個不重疊的 5 日樣本後才進行門檻判定，依每年約 49 個樣本估算約需 3 年，目前已累積 20 個。",
      "本排行的族群依臺灣證券交易所目前公布的產業分類，僅含上市普通股。",
    ]);
  });

  it("NE-3 fee_unverified", () => {
    const { main, detail } = notEvaluatedSentences({
      reason: "fee_unverified",
      lookbackDays: 5,
      pitGaps: [],
      accumulation: accumulation(),
    });
    expect(main).toBe("交易成本費率尚未查證，本排行僅描述近 5 日的相對強弱。");
    expect(detail).toEqual(["計算歷史比例所需的成本費率（手續費與證交稅）尚未完成查證；查證前，系統不列示歷史比例。"]);
  });

  it("NE-4 stale_recompute", () => {
    const { main, detail } = notEvaluatedSentences({
      reason: "stale_recompute",
      lookbackDays: 5,
      pitGaps: [],
      accumulation: accumulation(),
    });
    expect(main).toBe("歷史統計已超過 20 個交易日未重新計算，本排行僅描述近 5 日的相對強弱。");
    expect(detail).toEqual([
      "本排行的歷史統計於每累積一個新的 5 日樣本時重新計算；超過 20 個交易日未重新計算時（例如排程未執行或資料中斷），系統停止列示歷史比例，待重新計算完成後再依門檻重新判定。",
    ]);
  });

  it("NE-5 version_mismatch", () => {
    const { main, detail } = notEvaluatedSentences({
      reason: "version_mismatch",
      lookbackDays: 5,
      pitGaps: [],
      accumulation: accumulation(),
    });
    expect(main).toBe("排行版本與歷史統計版本不一致，本排行僅描述近 5 日的相對強弱。");
    expect(detail).toEqual([
      "本次排行所用的計算版本與歷史統計所依據的版本不同；新版本須重新計算並經風控複審，在此之前系統不列示歷史比例，也不混用不同版本的統計數字。",
    ]);
  });

  it("NE-6 data_quality", () => {
    const { main, detail } = notEvaluatedSentences({
      reason: "data_quality",
      lookbackDays: 5,
      pitGaps: [],
      accumulation: accumulation(),
    });
    expect(main).toBe("歷史統計所用資料未通過品質檢查，本排行僅描述近 5 日的相對強弱。");
    expect(detail).toEqual(["系統計算歷史統計前，會檢查所用資料是否有未來日期、重複紀錄或覆蓋率不足；本次檢查未通過，因此不列示歷史比例。"]);
  });

  it("NE-7 lookahead_tests_failed", () => {
    const { main, detail } = notEvaluatedSentences({
      reason: "lookahead_tests_failed",
      lookbackDays: 5,
      pitGaps: [],
      accumulation: accumulation(),
    });
    expect(main).toBe("歷史統計未通過資料偏誤檢查，本排行僅描述近 5 日的相對強弱。");
    expect(detail).toEqual(["系統計算歷史統計前，會檢查是否用到當時還不知道的資料等偏誤；本次檢查未全部通過，因此不列示歷史比例。"]);
  });

  it("NE-8 demo_data", () => {
    const { main, detail } = notEvaluatedSentences({
      reason: "demo_data",
      lookbackDays: 5,
      pitGaps: [],
      accumulation: accumulation(),
    });
    expect(main).toBe("示範資料不計算歷史統計。");
    expect(detail).toEqual(["系統偵測到資料來源為離線示範資料時，一律不計算也不列示歷史比例；示範資料只用於介面展示。"]);
  });

  it("pending_review", () => {
    const { main, detail } = notEvaluatedSentences({
      reason: "pending_review",
      lookbackDays: 5,
      pitGaps: [],
      accumulation: accumulation(),
    });
    expect(main).toBe("歷史統計尚待風控複審，本排行僅描述近 5 日的相對強弱。");
    expect(detail).toEqual(["本計算版本的歷史統計已具備判定條件，但首次列示前須經風控複審；複審完成前，系統不列示歷史比例，也不顯示判定結果。"]);
  });

  it("lookback_days=20 時，全部 not_evaluated 主視圖句同步換窗，不與 5 混用", () => {
    for (const reason of KNOWN_NOT_EVALUATED_REASONS) {
      const { main, detail } = notEvaluatedSentences({
        reason,
        lookbackDays: 20,
        pitGaps: reason === "pit_history_missing" ? ["pit_universe"] : [],
        accumulation: accumulation(),
      });
      expect(main + detail.join("")).not.toContain("近 5 日");
      if (main.includes("近")) expect(main).toContain("近 20 日");
    }
  });
});

describe("sectorMomentumWording — §5-4／§5-2／§8-4 failed／passed（§13.5-4／-5／-6／-7／-10）", () => {
  it("failed 主視圖降級句", () => {
    expect(buildFailedMainSentence(5)).toBe("歷史統計未達門檻，本排行僅描述近 5 日的相對強弱。");
    expect(buildFailedMainSentence(20)).toBe("歷史統計未達門檻，本排行僅描述近 20 日的相對強弱。");
  });

  it("passed 主視圖完整比例句（holding_days 代入，不與 lookback 共用）", () => {
    const sentence = buildPassedMainSentence(stat({ sample_count: 80, beat_count_net: 50, base_rate_net: 0.5 }), 5);
    expect(sentence).toBe(
      "歷史：第 1 名族群其後 5 個交易日報酬高於等權全市場，80 次中 50 次（62.5%）；" +
        "同期全部族群平均為 50.0%（兩者皆已扣來回成本）",
    );
  });

  it("passed 主視圖句 holding_days=20 時換窗，句中不出現「其後 5 個交易日」", () => {
    const sentence = buildPassedMainSentence(stat(), 20);
    expect(sentence).toContain("其後 20 個交易日");
    expect(sentence).not.toContain("其後 5 個交易日");
  });

  it("§4.3 詳細兩句", () => {
    expect(HISTORICAL_STAT_SECTOR_ONLY_SENTENCE).toBe("本比例為族群等權指數的統計，不適用於個別成分股。");
    expect(buildStatsAsOfSentence(stat())).toBe("歷史比例統計截至 2026-08-01，樣本外期間 2023-01-05～2026-08-01。");
  });

  it("§5-2 詳細第 1～3 句", () => {
    expect(COST_DEFINITION_SENTENCE).toBe(
      "「已扣來回成本」指族群一方每次扣除一次買進與賣出的手續費及證交稅；等權全市場為對照，不扣成本。",
    );
    expect(DISPLAY_THRESHOLD_RULE_SENTENCE).toBe(
      "是否列示本比例，以較嚴格的口徑判定：扣成本後的第 1 名比例，須高於未扣成本的全部族群平均至少 5 個百分點，且須高於 50%。",
    );
    expect(buildReturnWindowSentence(5)).toBe("報酬自排行次一交易日開盤起算，至第 5 個交易日收盤。");
    expect(buildReturnWindowSentence(20)).toBe("報酬自排行次一交易日開盤起算，至第 20 個交易日收盤。");
  });

  it("§8-4 T8-1／T8-2", () => {
    expect(T8_1_SENTENCE).toBe(
      "本統計另做過時間平移對照，可排除「不論何時都成立」的結構性偏誤，但無法排除只在特定期間出現的偏誤。",
    );
    expect(buildT82Sentence(stat({ delta_shuffle: 1.1, delta_real: 3.2 }))).toBe(
      "對照檢查：打亂產業歸屬後，第 1 名比例高出全部族群平均 1.1 個百分點（實際為 3.2 個百分點）；" +
        "兩者越接近，表示本比例越可能來自個股本身，而非族群。",
    );
  });
});

describe("sectorMomentumWording — §14-2 passed／failed 詳細數字列（兩組，CEO 字數裁定 2026-09-26）", () => {
  it("組標題", () => {
    expect(NET_COST_GROUP_TITLE).toBe("已扣來回成本");
    expect(GROSS_COST_GROUP_TITLE).toBe("未扣成本");
  });

  it("buildBeatCountSentence：{N} 次中 {k} 次（{p}%），p 無條件捨去，holding_days 代入", () => {
    expect(buildBeatCountSentence(80, 50, 5)).toBe(
      "第 1 名族群其後 5 個交易日報酬高於等權全市場：80 次中 50 次（62.5%）",
    );
    expect(buildBeatCountSentence(80, 50, 20)).toBe(
      "第 1 名族群其後 20 個交易日報酬高於等權全市場：80 次中 50 次（62.5%）",
    );
    // p 無條件捨去：19.96% 不得四捨五入成 20.0%。
    expect(buildBeatCountSentence(10000, 1996, 5)).toBe(
      "第 1 名族群其後 5 個交易日報酬高於等權全市場：10000 次中 1996 次（19.9%）",
    );
  });

  it("buildAverageSentence：q 無條件捨去", () => {
    expect(buildAverageSentence(0.5)).toBe("同期全部族群平均：50.0%");
    expect(buildAverageSentence(0.1996)).toBe("同期全部族群平均：19.9%");
  });

  it("ceilRatioPercent：無條件進位（區間上界專用）", () => {
    expect(ceilRatioPercent(0.5521)).toBe("55.3");
    expect(ceilRatioPercent(0.8)).toBe("80.0");
  });

  it("computeConfidenceLevelPercent：(1 − 0.05/m) × 100，無條件捨去到小數一位", () => {
    // m = 3 -> (1 - 0.05/3) * 100 = 98.3333... -> 捨去 98.3。
    expect(computeConfidenceLevelPercent(3)).toBe("98.3");
    // m = 1 -> 95.0 恰好整數邊界，捨去仍為 95.0。
    expect(computeConfidenceLevelPercent(1)).toBe("95.0");
  });

  it("buildWilsonIntervalSentence／buildBootstrapIntervalSentence：下界捨去、上界進位", () => {
    expect(buildWilsonIntervalSentence("98.3", 0.5521, 0.7009)).toBe("98.3% 區間（Wilson 法）：55.2%～70.1%");
    expect(buildBootstrapIntervalSentence("98.3", 0.5432, 0.7109)).toBe(
      "98.3% 區間（circular block bootstrap 法）：54.3%～71.1%",
    );
  });
});

describe("sectorMomentumWording — §14-3 單一個股集中（single_stock_dominated）", () => {
  it("主視圖 tag", () => {
    expect(SINGLE_STOCK_DOMINATED_TAG).toBe("單一個股集中");
  });

  it("詳細說明句：{share} 無條件捨去、不帶正負號、近 5 日依 lookback 代入", () => {
    expect(buildSingleStockDominatedSentence(0.351, 5)).toBe(
      "本族群各成分股近 5 日漲跌幅的絕對值合計中，漲跌幅絕對值最大的一檔占 35.1%；僅為揭露，不影響排名。",
    );
    expect(buildSingleStockDominatedSentence(0.351, 20)).toBe(
      "本族群各成分股近 20 日漲跌幅的絕對值合計中，漲跌幅絕對值最大的一檔占 35.1%；僅為揭露，不影響排名。",
    );
    // 無條件捨去、不帶正負號：35.19% 不得四捨五入或加正號。
    expect(buildSingleStockDominatedSentence(0.3519, 5)).not.toContain("+");
    expect(buildSingleStockDominatedSentence(0.3519, 5)).toContain("35.1%");
  });
});

describe("sectorMomentumWording — §14-4 取樣規則標籤", () => {
  it("定稿字面", () => {
    expect(SAMPLING_RULE_LABEL).toBe("每族群僅列漲跌幅最大 2 檔與最小 1 檔。");
  });
});

/**
 * §14 逐字掃描：比對 `work/stock-desk-族群動能-派工單.md` 是否已收錄本輪四件
 * 定稿字面的原始模板（含 `{sign}{value}` 等佔位符號）。§14 已併入派工單（含
 * §14.1～§14.5，2026-09-26），本段應全綠；若仍紅代表模板字面與派工單定稿不
 * 一致，需要重新核對。
 */
describe("sectorMomentumWording — §14 逐字掃描（派工單原文，§14 已併入，本段應全綠）", () => {
  const dispatchOrderText = (() => {
    try {
      return readFileSync(DISPATCH_ORDER_PATH, "utf-8");
    } catch {
      return null;
    }
  })();

  const templates: Record<string, string> = {
    RELATIVE_RETURN_SENTENCE_TEMPLATE,
    SECTOR_RETURN_SENTENCE_TEMPLATE,
    BENCHMARK_RETURN_SENTENCE_TEMPLATE,
    BEAT_COUNT_SENTENCE_TEMPLATE,
    AVERAGE_SENTENCE_TEMPLATE,
    WILSON_INTERVAL_SENTENCE_TEMPLATE,
    BOOTSTRAP_INTERVAL_SENTENCE_TEMPLATE,
    NET_COST_GROUP_TITLE,
    GROSS_COST_GROUP_TITLE,
    SINGLE_STOCK_DOMINATED_TAG,
    SINGLE_STOCK_DOMINATED_SENTENCE_TEMPLATE,
    SAMPLING_RULE_LABEL,
  };

  for (const [name, template] of Object.entries(templates)) {
    it(`§14 已收錄「${name}」原始模板字面`, () => {
      expect(dispatchOrderText, `讀不到 ${DISPATCH_ORDER_PATH}`).not.toBeNull();
      expect(dispatchOrderText).toContain(template);
    });
  }
});

describe("sectorMomentumWording — §6.2(c) 族群排除句（§8-2 短語逐字）", () => {
  function excluded(overrides: Partial<SectorExcludedItem> = {}): SectorExcludedItem {
    return {
      sector_code: "20",
      sector_name: "其他業",
      reason_code: "unranked_category",
      computable_count: 5,
      expected_count: 8,
      coverage: {
        expected_count: 8,
        calculation_count: 5,
        missing_count: 1,
        ex_date_excluded_count: 2,
        corporate_action_excluded_count: 0,
        suspended_count: null,
        coverage_ratio: 0.625,
        completeness_ratio: 0.875,
      },
      ...overrides,
    };
  }

  const ctx = { minConstituents: 5, sectorCoverageThresholdPct: thresholdPercent(0.9), lookbackDays: 5 };

  it("unranked_category", () => {
    expect(buildExclusionSentence(excluded({ sector_name: "其他業", reason_code: "unranked_category" }), ctx)).toBe(
      "其他業 本次未納入排行：屬雜項分類，不列入排名；成分股仍計入等權全市場。",
    );
  });

  it("too_few_members", () => {
    expect(
      buildExclusionSentence(excluded({ sector_name: "貿易百貨業", reason_code: "too_few_members" }), ctx),
    ).toBe("貿易百貨業 本次未納入排行：合格成分股不足 5 檔。");
  });

  it("low_coverage（{門檻} 不得寫死，取自 sector_coverage_threshold）", () => {
    expect(
      buildExclusionSentence(excluded({ sector_name: "橡膠工業", reason_code: "low_coverage" }), {
        ...ctx,
        sectorCoverageThresholdPct: thresholdPercent(0.9),
      }),
    ).toBe("橡膠工業 本次未納入排行：資料覆蓋率低於 90%。");
  });

  it("ex_dividend_exclusion（{c}／{e} 綁族群層級欄位，近 5 日依 lookback 代入）", () => {
    expect(
      buildExclusionSentence(
        excluded({ sector_name: "金融保險業", reason_code: "ex_dividend_exclusion", computable_count: 3, expected_count: 9 }),
        ctx,
      ),
    ).toBe("金融保險業 本次未納入排行：近 5 日遇除權息或減資等事件的成分股暫不計入，可計算成分股 3／9 檔，未達列入排行的標準。");
  });

  it("thresholdPercent 不得寫死 90／98／80／5 字面（T-20）——以商數計算得出", () => {
    expect(thresholdPercent(0.9)).toBe("90");
    expect(thresholdPercent(0.98)).toBe("98");
    expect(thresholdPercent(0.8)).toBe("80");
    expect(thresholdPercent(0.05)).toBe("5");
    expect(thresholdPercent(0.825)).toBe("82.5");
  });

  it("KNOWN_SECTOR_REASON_CODES 恰為四碼（S-2：元件遇到其餘碼須改走 ErrorPanel）", () => {
    expect(KNOWN_SECTOR_REASON_CODES).toEqual([
      "unranked_category",
      "too_few_members",
      "low_coverage",
      "ex_dividend_exclusion",
    ]);
  });
});

describe("sectorMomentumWording — 成交金額倍數（§5-3 定稿，5／20 為固定窗不隨 lookback 代入）", () => {
  it("定稿標籤", () => {
    expect(buildTurnoverRatioLabel(1.234)).toBe("成交金額 5 日均／20 日均 1.2 倍");
  });
});

describe("sectorMomentumWording — 數字格式（正負號、扣成本口徑百分比）", () => {
  it("formatSignedPercent 永遠帶正負號（FR-2 底線 8）", () => {
    expect(formatSignedPercent(0.032)).toBe("+3.2%");
    expect(formatSignedPercent(-0.018)).toBe("-1.8%");
    expect(formatSignedPercent(0)).toBe("+0.0%");
  });

  it("formatRatioPercent 不含正負號（給既定為非負比例的欄位使用）", () => {
    expect(formatRatioPercent(0.552)).toBe("55.2");
  });

  it("formatRatioPercent 一律無條件捨去，不四捨五入（S-3，比照 §9／C-37）", () => {
    // 0.1996 -> 19.96% -> 一般四捨五入會變 20.0，但這裡必須捨去為 19.9。
    expect(formatRatioPercent(0.1996)).toBe("19.9");
    // 恰好等於邊界時不捨去（跟門檻邊界一致，不因浮點雜訊被推低一格）。
    expect(formatRatioPercent(0.8)).toBe("80.0");
    expect(formatRatioPercent(50 / 80)).toBe("62.5");
  });

  it("formatPercentagePoints：delta_real／delta_shuffle 已是百分點，不再乘 100", () => {
    expect(formatPercentagePoints(3.2)).toBe("3.2");
    expect(formatPercentagePoints(-1.4)).toBe("-1.4");
  });
});

describe("sectorMomentumWording — withLookback／withHoldingDays 互不共用（§6／§13 前言）", () => {
  it("withLookback 只替換「近 5 日」類字串，不動「其後 5 個交易日」", () => {
    const text = "近 5 日相對強弱；其後 5 個交易日報酬。";
    expect(withLookback(text, 20)).toBe("近 20 日相對強弱；其後 5 個交易日報酬。");
  });

  it("withHoldingDays 只替換「其後 5 個交易日」類字串，不動「近 5 日」", () => {
    const text = "近 5 日相對強弱；其後 5 個交易日報酬。";
    expect(withHoldingDays(text, 20)).toBe("近 5 日相對強弱；其後 20 個交易日報酬。");
  });
});

describe("sectorMomentumWording — 全文禁用詞掃描（C-26／FRONTEND_FORBIDDEN_TERMS）", () => {
  const samples: Record<string, string> = {
    SECTOR_CARD_TITLE,
    TWSE_ONLY_TAG,
    DEMO_DATA_CARD_WARNING,
    listingOrder: buildListingOrderSentence(5),
    failedMain: buildFailedMainSentence(5),
    passedMain: buildPassedMainSentence(stat(), 5),
    t8_1: T8_1_SENTENCE,
    t8_2: buildT82Sentence(stat()),
    costDefinition: COST_DEFINITION_SENTENCE,
    displayThresholdRule: DISPLAY_THRESHOLD_RULE_SENTENCE,
    returnWindow: buildReturnWindowSentence(5),
    historicalStatSectorOnly: HISTORICAL_STAT_SECTOR_ONLY_SENTENCE,
    statsAsOf: buildStatsAsOfSentence(stat()),
    turnoverRatio: buildTurnoverRatioLabel(1.2),
    marketMissingTag: buildMarketMissingTag(1),
    exDateTag: buildExDateTag(1),
    staleData: buildStaleDataSentence("2026-09-18", 1),
  };

  for (const [name, text] of Object.entries(samples)) {
    it(`${name}：不含 §1.3／C-26 禁用詞`, () => {
      assertNoForbiddenTerms(text, FRONTEND_FORBIDDEN_TERMS, name);
    });

    it(`${name}：每個「即時」都是「非即時」否定語境`, () => {
      expect(findBareRealtimeClaims(text)).toEqual([]);
    });
  }

  it("全部 not_evaluated／NE 句都不含禁用詞", () => {
    for (const reason of KNOWN_NOT_EVALUATED_REASONS) {
      const { main, detail } = notEvaluatedSentences({
        reason,
        lookbackDays: 5,
        pitGaps: reason === "pit_history_missing" ? ["pit_universe"] : [],
        accumulation: accumulation(),
      });
      assertNoForbiddenTerms(main, FRONTEND_FORBIDDEN_TERMS, `${reason} main`);
      for (const sentence of detail) {
        assertNoForbiddenTerms(sentence, FRONTEND_FORBIDDEN_TERMS, `${reason} detail`);
      }
    }
  });
});
