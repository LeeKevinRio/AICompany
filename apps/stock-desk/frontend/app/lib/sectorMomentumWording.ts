/**
 * Single source of truth for the 族群動能排行 (sector momentum) card's own
 * wording — every constant/builder below is copied **verbatim** (含標點) from
 * `work/stock-desk-族群動能-派工單.md`, chiefly §13.5 (「由前端依碼選用、後端不
 * 輸出的定稿句」, the third-wave risk ruling), plus §4.6 CL-2 (title/chip/
 * constituent-header) and §12 (CEO 核可, the standing 「僅上市」 tag). Nothing
 * here may be reworded; a change goes back to risk-compliance-officer first.
 *
 * The backend's own standing/insufficient-reason sentences
 * (`app/api/sectors_wording.py`) are **not** duplicated here — they arrive
 * ready-made on `SectorMomentumResponse.reason` / `.disclosures` and are
 * rendered as-is by `SectorMomentumCard.tsx`. This module only holds the
 * sentences ADR-0012 D-8 assigns to the front end: the ones selected by
 * `gate_status` / `not_evaluated_reason` / `pit_gaps` / `reason_code`.
 *
 * Two substitutions are sanctioned by risk (派工單 §6 前言, §13 前言), both
 * mirrored here exactly like the backend's own `with_lookback`:
 *
 * - "5" in 「近 5 日」／「近 5 個交易日」 is `lookback_days` (`withLookback`);
 * - "5" in 「其後 5 個交易日」／「第 5 個交易日」 is `holding_days`
 *   (`withHoldingDays`) — a different parameter, never shared with the above.
 *
 * Every other number substituted below comes from the response's own fields
 * (never computed or guessed client-side), except the one ratio ADR-0012 D-10
 * explicitly assigns to the front end: 「比例由前端計算。主視圖顯示
 * `beat_count_net / sample_count` 對 `base_rate_net`」 — see `formatRatioPercent`
 * and `buildPassedMainSentence`.
 */

import type {
  SectorAccumulation,
  SectorExcludedItem,
  SectorHistoricalStat,
  SectorNotEvaluatedReason,
  SectorPitGap,
} from "./types";

// ---------------------------------------------------------------------------
// Title, chip, standing tags (§1 FR-1, §4.6 CL-2 定稿, §12 CEO 核可)
// ---------------------------------------------------------------------------

/** §4.6 CL-2 定稿：卡片標題。 */
export const SECTOR_CARD_TITLE = "族群動能排行";

/** §4.6 CL-2 定稿：緊鄰標題的時間窗 chip（{lookbackDays} 只能是 5 或 20）。 */
export function buildLookbackChip(lookbackDays: number): string {
  return `近 ${lookbackDays} 日`;
}

/**
 * §12 CEO 核可第 2 項（逐字）：「上櫃本階段排除，畫面常駐「僅上市」」。獨立於
 * `gate_status`／`status`，只要 `market_scope === "twse_only"` 就常駐顯示
 * （目前恆為 true）。
 */
export const TWSE_ONLY_TAG = "僅上市";

// ---------------------------------------------------------------------------
// Lookback / holding-day substitution (mirrors backend `with_lookback`)
// ---------------------------------------------------------------------------

/**
 * The only sanctioned substitution for 「近 5 日」／「近 5 個交易日」（派工單
 * §6 前言／§13 前言）。Mirrors `app/api/sectors_wording.py::with_lookback`
 * exactly so the two sides cannot drift.
 */
export function withLookback(text: string, lookbackDays: number): string {
  return text
    .replaceAll("近 5 日", `近 ${lookbackDays} 日`)
    .replaceAll("近 5 個交易日", `近 ${lookbackDays} 個交易日`);
}

/**
 * The only sanctioned substitution for 「其後 5 個交易日」／「第 5 個交易日」
 * （`holding_days`——與 `lookback_days` 是兩個獨立參數，不得共用，派工單 §6
 * 前言／§13 前言）。
 */
export function withHoldingDays(text: string, holdingDays: number): string {
  return text
    .replaceAll("其後 5 個交易日", `其後 ${holdingDays} 個交易日`)
    .replaceAll("第 5 個交易日", `第 ${holdingDays} 個交易日`);
}

// ---------------------------------------------------------------------------
// §4.4-2 / §13.5-13, §8-1 C1-2 / §13.5-12, §4.5-3 / §13.5-14 (main-view, standing)
// ---------------------------------------------------------------------------

/**
 * §4.4-2 絕對底線 tag（字面見 §4.5-2）：「缺 {m} 檔資料」。`{m}` 綁
 * `market_missing_count`；只在 `market_missing_count > 0` 且 `status === "ok"`
 * 時渲染（§13.2：不足狀態依 IP-5／IP-6 不渲染）。
 */
export function buildMarketMissingTag(m: number): string {
  return `缺 ${m} 檔資料`;
}

/**
 * §8-1 C1-2 定稿 tag：「除權息排除 {m} 檔」。`{m}` 綁 `market_ex_date_excluded_count`；
 * 出現條件是 `ex_date_tag === true`（前端不得自行判斷比例，見 T-24）。
 */
export function buildExDateTag(m: number): string {
  return `除權息排除 ${m} 檔`;
}

/**
 * 族群層級缺漏 tag（風控 ALL-1 複審裁定，2026-09-25）：沿用 §4.5-2「缺 {m} 檔
 * 資料」的同一文字，但 `{m}` 綁的是**族群層級**的 `sectors[].coverage.missing_count`
 * ——與 {@link buildMarketMissingTag} 綁的**全市場**層級 `market_missing_count`
 * 同名不同義，兩者不得混用同一數字來源。放在該族群成分股表頭同一行，主視圖
 * 前幾名與「詳細」完整排行皆須顯示（missing_count > 0 時）。
 */
export function buildSectorMissingTag(m: number): string {
  return `缺 ${m} 檔資料`;
}

/**
 * §4.5-3 定稿句（主視圖常駐）：條件 `data.trading_days_behind >= 1`。
 * `{date}` 綁 `data_as_of`、`{d}` 綁 `data.trading_days_behind`。
 */
export function buildStaleDataSentence(date: string, d: number): string {
  return `本排行所依據的全市場收盤資料為 ${date}，距今已 ${d} 個交易日未更新，排行不代表最新市況。`;
}

/**
 * §6.1 NE-8 卡片層級常駐警告（絕對底線，依 `data_source` 驅動，與
 * `gate_status` 無關；不受整卡不足替換影響，IP-6）。
 */
export const DEMO_DATA_CARD_WARNING = "警告：本卡使用的是離線示範資料（demo_synthetic），不是市場資料。";

// ---------------------------------------------------------------------------
// §4.1e / §6.3 H-2 / §13.5-16: held 未知時帶回主視圖的句子
// ---------------------------------------------------------------------------

/**
 * 字串取自後端 `disclosures` 中已代入 `lookback_days` 的那一句
 * （`app/api/sectors_wording.py::LISTING_ORDER`），這裡以同一模板＋同一代入
 * 規則重建，不寫死 "5"（派工單 §13.5-16 required：不得寫死 5）。
 */
export function buildListingOrderSentence(lookbackDays: number): string {
  return withLookback("列示順序僅依近 5 日漲跌幅，不代表任何優先順序。", lookbackDays);
}

// ---------------------------------------------------------------------------
// §4.6 CL-2 定稿：成分股表頭 / 上漲家數
// ---------------------------------------------------------------------------

/** §4.6 CL-2 定稿：「成分股（依近 5 日漲跌幅，共 {n} 檔）」。 */
export function buildConstituentHeader(lookbackDays: number, n: number): string {
  return withLookback(`成分股（依近 5 日漲跌幅，共 ${n} 檔）`, lookbackDays);
}

/** §4.2 APPROVE：「上漲 k／n 家」（族群層級，與族群名稱同層）。 */
export function buildUpCountLabel(k: number, n: number): string {
  return `上漲 ${k}／${n} 家`;
}

/** §6.3：持有徽章字面核可（兩態皆標示）。 */
export const SECTOR_NOT_HELD_BADGE = "未持有";
export const SECTOR_HELD_BADGE = "持有中";

// ---------------------------------------------------------------------------
// §14 第四波風控定稿與 CEO 字數裁定（2026-09-26，dev-lead 轉達；派工單 §14
// 尚待併入 `work/stock-desk-族群動能-派工單.md`——`sectorMomentumWording.test.ts`
// 的逐字掃描測試在 §14 落地前預期為紅，這是刻意的，不是實作錯誤）。
//
// 取代先前 `buildRelativeReturnPlaceholder` 的暫時佔位格式：族群相對報酬改用
// 「個百分點」呈現（不是 `%`），主視圖與「詳細」完整排行同一句式。
// ---------------------------------------------------------------------------

/** §14-1 定稿（逐字，含 `{sign}{value}` 佔位）：主視圖與「詳細」完整排行同句式。 */
export const RELATIVE_RETURN_SENTENCE_TEMPLATE = "{sign}{value} 個百分點（近 5 日／相對等權全市場）";

/**
 * §14-1：`relReturnL`（`rel_return_L`，排名依據 S_A）→ 上述句式。`{value}` 為
 * `relReturnL × 100`，小數一位，一律帶正負號（0 顯示 `+0.0`）。
 */
export function buildRelativeReturnSentence(relReturnL: number, lookbackDays: number): string {
  const { sign, value } = signedParts(relReturnL);
  return withLookback(
    RELATIVE_RETURN_SENTENCE_TEMPLATE.replace("{sign}", sign).replace("{value}", value),
    lookbackDays,
  );
}

/** §14-1 定稿：「詳細」逐族群一句，`sector_return_L`。 */
export const SECTOR_RETURN_SENTENCE_TEMPLATE = "族群報酬（近 5 日）：{sign}{value}%";

export function buildSectorReturnSentence(sectorReturnL: number, lookbackDays: number): string {
  const { sign, value } = signedParts(sectorReturnL);
  return withLookback(
    SECTOR_RETURN_SENTENCE_TEMPLATE.replace("{sign}", sign).replace("{value}", value),
    lookbackDays,
  );
}

/**
 * §14-1 定稿：「詳細」整卡一次，`benchmark_return_L`，放在「完整排行」小標之
 * 後、族群清單之前。呼叫端須先確認同一回應中每個族群的 `benchmark_return_L`
 * 皆相等（board 層級數字），不相等時改走 `ErrorPanel`（契約破壞）。
 */
export const BENCHMARK_RETURN_SENTENCE_TEMPLATE = "等權全市場報酬（近 5 日）：{sign}{value}%";

export function buildBenchmarkReturnSentence(benchmarkReturnL: number, lookbackDays: number): string {
  const { sign, value } = signedParts(benchmarkReturnL);
  return withLookback(
    BENCHMARK_RETURN_SENTENCE_TEMPLATE.replace("{sign}", sign).replace("{value}", value),
    lookbackDays,
  );
}

// ---------------------------------------------------------------------------
// §14-2 passed／failed「詳細」數字列（兩組，各自標題，明顯分隔）
// ---------------------------------------------------------------------------

/** §14-2 定稿：組 1 標題（扣成本口徑）。 */
export const NET_COST_GROUP_TITLE = "已扣來回成本";
/** §14-2 定稿：組 2 標題（未扣成本口徑）。 */
export const GROSS_COST_GROUP_TITLE = "未扣成本";

/** §14-2 定稿（兩組皆用，僅 {N}/{k}/{p} 依口徑代入不同數字）。 */
export const BEAT_COUNT_SENTENCE_TEMPLATE = "第 1 名族群其後 5 個交易日報酬高於等權全市場：{N} 次中 {k} 次（{p}%）";

/**
 * §14-2：{N}＝`sample_count`、{k}＝`beat_count_net`／`beat_count_gross`、
 * {p}＝`k / sample_count`，無條件捨去到小數一位。
 */
export function buildBeatCountSentence(sampleCount: number, beatCount: number, holdingDays: number): string {
  const p = formatRatioPercent(sampleCount === 0 ? 0 : beatCount / sampleCount);
  return withHoldingDays(BEAT_COUNT_SENTENCE_TEMPLATE, holdingDays)
    .replace("{N}", String(sampleCount))
    .replace("{k}", String(beatCount))
    .replace("{p}", p);
}

/** §14-2 定稿（兩組皆用，{q} 依口徑代入 `base_rate_net`／`base_rate_gross`）。 */
export const AVERAGE_SENTENCE_TEMPLATE = "同期全部族群平均：{q}%";

export function buildAverageSentence(rate: number): string {
  return AVERAGE_SENTENCE_TEMPLATE.replace("{q}", formatRatioPercent(rate));
}

/** §14-2 定稿：組 1 專屬，Wilson 法區間。 */
export const WILSON_INTERVAL_SENTENCE_TEMPLATE = "{level}% 區間（Wilson 法）：{lo}%～{hi}%";
/** §14-2 定稿：組 1 專屬，circular block bootstrap 法區間。 */
export const BOOTSTRAP_INTERVAL_SENTENCE_TEMPLATE = "{level}% 區間（circular block bootstrap 法）：{lo}%～{hi}%";

function fillIntervalSentence(template: string, level: string, low: number, high: number): string {
  return template.replace("{level}", level).replace("{lo}", formatRatioPercent(low)).replace("{hi}", ceilRatioPercent(high));
}

/** {lo}＝`ci_low_net` 無條件捨去、{hi}＝`ci_high_net` 無條件進位。 */
export function buildWilsonIntervalSentence(level: string, ciLowNet: number, ciHighNet: number): string {
  return fillIntervalSentence(WILSON_INTERVAL_SENTENCE_TEMPLATE, level, ciLowNet, ciHighNet);
}

/** {lo}＝`bootstrap_low_net` 無條件捨去、{hi}＝`bootstrap_high_net` 無條件進位。 */
export function buildBootstrapIntervalSentence(level: string, bootstrapLowNet: number, bootstrapHighNet: number): string {
  return fillIntervalSentence(BOOTSTRAP_INTERVAL_SENTENCE_TEMPLATE, level, bootstrapLowNet, bootstrapHighNet);
}

/**
 * {level}＝`(1 − 0.05 / m_at_evaluation) × 100`，無條件捨去到小數一位。
 * quant-researcher 2026-09-26 已書面確認（派工單 §14.2）：`ci_low_net`／
 * `ci_high_net`（Wilson）與 `bootstrap_low_net`／`bootstrap_high_net`
 * （circular block bootstrap，固定區塊長度 4）皆為雙側等尾區間，信賴水準
 * `1 − 0.05/m`，`m` 即同一統計列的 `m_at_evaluation`（V1 `GateRules.alpha` =
 * 0.05）。日後若有版本把 alpha 收緊，這裡的公式須同步。
 */
export function computeConfidenceLevelPercent(mAtEvaluation: number): string {
  return floorPercentValue((1 - 0.05 / mAtEvaluation) * 100);
}

// ---------------------------------------------------------------------------
// §14-3 單一個股集中（`single_stock_dominated === true`）
// ---------------------------------------------------------------------------

/** §14-3 定稿：主視圖該族群區塊內 tag。 */
export const SINGLE_STOCK_DOMINATED_TAG = "單一個股集中";

/** §14-3 定稿：「詳細」完整排行該族群區塊內說明句。 */
export const SINGLE_STOCK_DOMINATED_SENTENCE_TEMPLATE =
  "本族群各成分股近 5 日漲跌幅的絕對值合計中，漲跌幅絕對值最大的一檔占 {share}%；僅為揭露，不影響排名。";

/** {share}＝`top_contributor_share × 100`，無條件捨去到小數一位，不帶正負號。 */
export function buildSingleStockDominatedSentence(topContributorShare: number, lookbackDays: number): string {
  return withLookback(
    SINGLE_STOCK_DOMINATED_SENTENCE_TEMPLATE.replace("{share}", formatRatioPercent(topContributorShare)),
    lookbackDays,
  );
}

// ---------------------------------------------------------------------------
// §14-4 取樣規則標籤
// ---------------------------------------------------------------------------

/**
 * §14-4 定稿：`status === "ok"` 且至少渲染一個族群時，主視圖卡片層級一次
 * （放在第一個族群區塊正上方）；「詳細」的「完整排行」小標下也放一次。
 */
export const SAMPLING_RULE_LABEL = "每族群僅列漲跌幅最大 2 檔與最小 1 檔。";

// ---------------------------------------------------------------------------
// §5-3 定稿：成交金額倍數（詳細專用，5／20 為固定窗，不隨 lookback 代入）
// ---------------------------------------------------------------------------

/** 定稿：「成交金額 5 日均／20 日均 {x.x} 倍」。 */
export function buildTurnoverRatioLabel(ratio: number): string {
  return `成交金額 5 日均／20 日均 ${ratio.toFixed(1)} 倍`;
}

// ---------------------------------------------------------------------------
// §6.2(d) 加權指數參考數字（風控 ALL-1 複審裁定，2026-09-25）
// ---------------------------------------------------------------------------

/**
 * 加權指數參考數字：整卡只顯示一次（不是每個族群各印一次——`reference_taiex_return_L`
 * 是同一個 board 層級數字複寫在每個 `SectorItem` 上），位置緊接在後端
 * §6.2(d) `TAIEX_REFERENCE` 揭露句之前，且只能出現在「詳細」，不得出現在任
 * 何族群區塊內或主視圖。字面「加權指數（近 {L} 日，僅供參考）：」核可，數值
 * 一律用 {@link formatSignedPercent}。
 */
export function buildTaiexReferenceLine(value: number, lookbackDays: number): string {
  return `加權指數（近 ${lookbackDays} 日，僅供參考）：${formatSignedPercent(value)}`;
}

// ---------------------------------------------------------------------------
// §6.2(c) 族群排除句（依 reason_code；§8-2 短語逐字）
// ---------------------------------------------------------------------------

/** The set of `reason_code` values this module knows how to render (S-2). */
export const KNOWN_SECTOR_REASON_CODES: readonly string[] = [
  "unranked_category",
  "too_few_members",
  "low_coverage",
  "ex_dividend_exclusion",
];

export interface ExclusionPhraseContext {
  minConstituents: number;
  sectorCoverageThresholdPct: string;
  lookbackDays: number;
}

function exclusionReasonPhrase(item: SectorExcludedItem, ctx: ExclusionPhraseContext): string {
  switch (item.reason_code) {
    case "unranked_category":
      return "屬雜項分類，不列入排名；成分股仍計入等權全市場";
    case "too_few_members":
      return `合格成分股不足 ${ctx.minConstituents} 檔`;
    case "low_coverage":
      return `資料覆蓋率低於 ${ctx.sectorCoverageThresholdPct}%`;
    case "ex_dividend_exclusion":
      return withLookback(
        `近 5 日遇除權息或減資等事件的成分股暫不計入，可計算成分股 ${item.computable_count}／${item.expected_count} 檔，未達列入排行的標準`,
        ctx.lookbackDays,
      );
    default:
      return item.reason_code;
  }
}

/** §6.2(c) 通用句型：「{族群名稱} 本次未納入排行：{原因}。」 */
export function buildExclusionSentence(item: SectorExcludedItem, ctx: ExclusionPhraseContext): string {
  return `${item.sector_name} 本次未納入排行：${exclusionReasonPhrase(item, ctx)}。`;
}

/**
 * Mirrors backend `app/api/sectors_wording.py::threshold_pct` for display
 * only (a threshold ratio the API echoes, e.g. `0.9` -> `"90"`,
 * `0.825` -> `"82.5"`) — never used to *judge* a threshold, only to print one
 * the backend already decided (T-20: the frontend must not hard-code 90/98/
 * 80/5 as literal percent text).
 */
export function thresholdPercent(threshold: number): string {
  const percent = threshold * 100;
  const rounded = Math.round(percent * 1e6) / 1e6;
  if (Number.isInteger(rounded)) return String(rounded);
  return rounded
    .toFixed(6)
    .replace(/0+$/, "")
    .replace(/\.$/, "");
}

// ---------------------------------------------------------------------------
// §6.1 not_evaluated 原因句（§13.5-1／-2／-3；NE-1/NE-2 特別組成，其餘各自一對）
// ---------------------------------------------------------------------------

const PIT_HISTORY_MAIN = "歷史統計尚未建立，本排行僅描述近 5 日的相對強弱。";
const PIT_HISTORY_DETAIL_1 =
  "本卡目前不提供歷史比例。系統開始逐日保存資料以前的期間，已下市個股資料、當時的產業分類與除權息紀錄皆無可用來源，以那段期間回推的結果會有無法估計幅度的系統性偏誤，因此不予使用。";
const PIT_HISTORY_DETAIL_3 = "本排行的族群依臺灣證券交易所目前公布的產業分類，僅含上市普通股。";

const PIT_GAP_LABELS: Record<SectorPitGap, string> = {
  pit_universe: "當時上市名單（含其後下市個股）的逐日保存",
  pit_classification: "當時產業分類的逐日保存",
  pit_ex_dividend: "除權息紀錄的逐日保存",
  de5_unverified: "除權息還原所需參考價欄位的定義查證",
};

/** §8-3 句 G（僅 NE-1 且 `pit_gaps` 非空時）——`null` when there is no gap to name. */
export function buildPitGapSentence(pitGaps: SectorPitGap[]): string | null {
  if (pitGaps.length === 0) return null;
  const list = pitGaps.map((gap) => PIT_GAP_LABELS[gap]).join("、");
  return `目前仍待補齊：${list}；補齊前不進行門檻判定。`;
}

/** §8-3 句 2（有 D0）／句 2'（`accumulation_start` 為 null，取代句 2）。 */
export function buildAccumulationSentence(accumulation: SectorAccumulation): string {
  if (accumulation.accumulation_start === null) {
    return "系統尚未開始逐日保存上述資料，目前已累積 0 個樣本。";
  }
  return (
    `自 ${accumulation.accumulation_start} 起，系統逐日保存當時的上市名單、產業分類與除權息公告；` +
    `累積滿 150 個不重疊的 5 日樣本後才進行門檻判定，依每年約 49 個樣本估算約需 3 年，` +
    `目前已累積 ${accumulation.accumulated_samples} 個。`
  );
}

interface SimpleNeEntry {
  main: string;
  detail: string;
}

/** NE-3～NE-8、`pending_review`：各自獨立的 (main, detail) 一對（§6.1 表）。 */
const NE_SIMPLE: Record<
  Exclude<SectorNotEvaluatedReason, "pit_history_missing" | "accumulating">,
  SimpleNeEntry
> = {
  fee_unverified: {
    main: "交易成本費率尚未查證，本排行僅描述近 5 日的相對強弱。",
    detail: "計算歷史比例所需的成本費率（手續費與證交稅）尚未完成查證；查證前，系統不列示歷史比例。",
  },
  stale_recompute: {
    main: "歷史統計已超過 20 個交易日未重新計算，本排行僅描述近 5 日的相對強弱。",
    detail:
      "本排行的歷史統計於每累積一個新的 5 日樣本時重新計算；超過 20 個交易日未重新計算時（例如排程未執行或資料中斷），系統停止列示歷史比例，待重新計算完成後再依門檻重新判定。",
  },
  version_mismatch: {
    main: "排行版本與歷史統計版本不一致，本排行僅描述近 5 日的相對強弱。",
    detail:
      "本次排行所用的計算版本與歷史統計所依據的版本不同；新版本須重新計算並經風控複審，在此之前系統不列示歷史比例，也不混用不同版本的統計數字。",
  },
  data_quality: {
    main: "歷史統計所用資料未通過品質檢查，本排行僅描述近 5 日的相對強弱。",
    detail: "系統計算歷史統計前，會檢查所用資料是否有未來日期、重複紀錄或覆蓋率不足；本次檢查未通過，因此不列示歷史比例。",
  },
  lookahead_tests_failed: {
    main: "歷史統計未通過資料偏誤檢查，本排行僅描述近 5 日的相對強弱。",
    detail: "系統計算歷史統計前，會檢查是否用到當時還不知道的資料等偏誤；本次檢查未全部通過，因此不列示歷史比例。",
  },
  demo_data: {
    main: "示範資料不計算歷史統計。",
    detail: "系統偵測到資料來源為離線示範資料時，一律不計算也不列示歷史比例；示範資料只用於介面展示。",
  },
  pending_review: {
    main: "歷史統計尚待風控複審，本排行僅描述近 5 日的相對強弱。",
    detail: "本計算版本的歷史統計已具備判定條件，但首次列示前須經風控複審；複審完成前，系統不列示歷史比例，也不顯示判定結果。",
  },
};

/** The set of `not_evaluated_reason` codes this module knows how to render. */
export const KNOWN_NOT_EVALUATED_REASONS: readonly SectorNotEvaluatedReason[] = [
  "pit_history_missing",
  "accumulating",
  "fee_unverified",
  "stale_recompute",
  "version_mismatch",
  "data_quality",
  "lookahead_tests_failed",
  "demo_data",
  "pending_review",
];

export interface NotEvaluatedInput {
  reason: SectorNotEvaluatedReason;
  lookbackDays: number;
  pitGaps: SectorPitGap[];
  accumulation: SectorAccumulation;
}

export interface NotEvaluatedSentences {
  main: string;
  detail: string[];
}

/**
 * R-4 required：`gate_status === "not_evaluated"` 時的主視圖句 + 詳細句組合。
 * 呼叫端必須先確認 `reason` 屬於 `KNOWN_NOT_EVALUATED_REASONS`（不認得的碼改走
 * `ErrorPanel`，不得照常顯示排行而沒有這句）。
 */
export function notEvaluatedSentences(input: NotEvaluatedInput): NotEvaluatedSentences {
  if (input.reason === "pit_history_missing" || input.reason === "accumulating") {
    const detail = [withLookback(PIT_HISTORY_DETAIL_1, input.lookbackDays)];
    if (input.reason === "pit_history_missing") {
      const gapSentence = buildPitGapSentence(input.pitGaps);
      if (gapSentence !== null) detail.push(gapSentence);
    }
    detail.push(buildAccumulationSentence(input.accumulation));
    detail.push(PIT_HISTORY_DETAIL_3);
    return { main: withLookback(PIT_HISTORY_MAIN, input.lookbackDays), detail };
  }
  const entry = NE_SIMPLE[input.reason];
  return {
    main: withLookback(entry.main, input.lookbackDays),
    detail: [withLookback(entry.detail, input.lookbackDays)],
  };
}

// ---------------------------------------------------------------------------
// §4.3 / §5-2 / §5-4 / §8-4: failed / passed 主視圖與詳細（§13.5-4／-5／-6／-7／-10）
// ---------------------------------------------------------------------------

/** §5-4 定稿（failed 主視圖）：「歷史統計未達門檻，本排行僅描述近 5 日的相對強弱。」 */
export function buildFailedMainSentence(lookbackDays: number): string {
  return withLookback("歷史統計未達門檻，本排行僅描述近 5 日的相對強弱。", lookbackDays);
}

/**
 * §5-2 定稿（passed 主視圖）：
 * 「歷史：第 1 名族群其後 5 個交易日報酬高於等權全市場，{N} 次中 {k} 次
 * （{p}%）；同期全部族群平均為 {q}%（兩者皆已扣來回成本）」
 *
 * ADR-0012 D-10：「比例由前端計算。主視圖顯示 beat_count_net / sample_count
 * 對 base_rate_net，兩者都已扣來回成本」——`{p}` 由本函式計算，`{q}` 直接讀
 * `base_rate_net`（已是 net 口徑），皆不得由風控以外的人改動口徑選擇。
 */
export function buildPassedMainSentence(stat: SectorHistoricalStat, holdingDays: number): string {
  const template =
    "歷史：第 1 名族群其後 5 個交易日報酬高於等權全市場，{N} 次中 {k} 次（{p}%）；" +
    "同期全部族群平均為 {q}%（兩者皆已扣來回成本）";
  const p = formatRatioPercent(stat.beat_count_net / stat.sample_count);
  const q = formatRatioPercent(stat.base_rate_net);
  return withHoldingDays(template, holdingDays)
    .replace("{N}", String(stat.sample_count))
    .replace("{k}", String(stat.beat_count_net))
    .replace("{p}", p)
    .replace("{q}", q);
}

/** §4.3「詳細」兩句之一（passed／failed 皆適用，§13.5-5）。 */
export const HISTORICAL_STAT_SECTOR_ONLY_SENTENCE = "本比例為族群等權指數的統計，不適用於個別成分股。";

/** §4.3「詳細」兩句之二（passed／failed 皆適用，§13.5-5）：{起}/{迄} 為樣本外期間。 */
export function buildStatsAsOfSentence(stat: SectorHistoricalStat): string {
  return `歷史比例統計截至 ${stat.stats_as_of}，樣本外期間 ${stat.sample_start}～${stat.sample_end}。`;
}

/** §5-2「詳細」第 1 句（passed／failed 皆適用，§13.5-7）。 */
export const COST_DEFINITION_SENTENCE =
  "「已扣來回成本」指族群一方每次扣除一次買進與賣出的手續費及證交稅；等權全市場為對照，不扣成本。";

/** §5-2「詳細」第 2 句（passed／failed 皆適用，§13.5-7）。 */
export const DISPLAY_THRESHOLD_RULE_SENTENCE =
  "是否列示本比例，以較嚴格的口徑判定：扣成本後的第 1 名比例，須高於未扣成本的全部族群平均至少 5 個百分點，且須高於 50%。";

/** §5-2「詳細」第 3 句（passed／failed 皆適用，§13.5-7；「第 5 個交易日」依 holding_days 代入）。 */
export function buildReturnWindowSentence(holdingDays: number): string {
  return withHoldingDays("報酬自排行次一交易日開盤起算，至第 5 個交易日收盤。", holdingDays);
}

/** §8-4 T8-1（passed／failed「詳細」必放，§13.5-4）。 */
export const T8_1_SENTENCE =
  "本統計另做過時間平移對照，可排除「不論何時都成立」的結構性偏誤，但無法排除只在特定期間出現的偏誤。";

/** §8-4 T8-2（passed／failed「詳細」必放，§13.5-4）：Δ 皆為扣成本口徑，取自 API。 */
export function buildT82Sentence(stat: SectorHistoricalStat): string {
  return (
    `對照檢查：打亂產業歸屬後，第 1 名比例高出全部族群平均 ${formatPercentagePoints(stat.delta_shuffle)} 個百分點` +
    `（實際為 ${formatPercentagePoints(stat.delta_real)} 個百分點）；兩者越接近，表示本比例越可能來自個股本身，而非族群。`
  );
}

// ---------------------------------------------------------------------------
// Number formatting
// ---------------------------------------------------------------------------

/**
 * Rounds a *percent-scale* value (already `× 100`) to one decimal, absorbing
 * float representation noise first (e.g. `0.1 * 1000 === 99.99999999999999`
 * in IEEE754) so a value exactly on a tenth-of-a-percent boundary is never
 * pushed the wrong way by float error. `floor`/`ceil` mirror backend
 * `floor_pct_display` (§9／C-37: 無條件捨去) and §14-2's 無條件進位 pair.
 */
function floorPercentValue(percent: number): string {
  const safe = Math.round(percent * 10 * 1e6) / 1e6;
  return (Math.floor(safe) / 10).toFixed(1);
}
function ceilPercentValue(percent: number): string {
  const safe = Math.round(percent * 10 * 1e6) / 1e6;
  return (Math.ceil(safe) / 10).toFixed(1);
}

/**
 * A 0–1 fraction as a one-decimal percent string, no sign, **floored** (never
 * rounded) — mirrors backend `floor_pct_display` (§9／C-37: 無條件捨去，避免
 * 「80.0%，低於 80%」這種門檻邊界矛盾的顯示；p、q、區間下界、§14-3 的 share
 * 皆比照此規則). E.g. `0.629` -> `"62.9"`, `0.8` -> `"80.0"`.
 */
export function formatRatioPercent(fraction: number): string {
  return floorPercentValue(fraction * 100);
}

/**
 * Same as {@link formatRatioPercent} but **無條件進位**（ceiling）——§14-2 區
 * 間上界（{hi}）專用，其餘一律用 `formatRatioPercent`。
 */
export function ceilRatioPercent(fraction: number): string {
  return ceilPercentValue(fraction * 100);
}

/** `{sign: "+"|"-", value: "X.X"}` for a raw fraction, one decimal, `0` -> `sign: "+"`. */
function signedParts(fraction: number, decimals = 1): { sign: "+" | "-"; value: string } {
  const pct = fraction * 100;
  const rounded = Number(pct.toFixed(decimals));
  const value = Math.abs(rounded).toFixed(decimals);
  return { sign: rounded < 0 ? "-" : "+", value };
}

/**
 * A signed one-decimal percent for a raw fraction return (e.g. `0.032` ->
 * `"+3.2%"`, `-0.018` -> `"-1.8%"`) — FR-2 底線 8: 漲跌一律帶正負號，不得只在
 * 跌時才標記號。
 */
export function formatSignedPercent(fraction: number, decimals = 1): string {
  const { sign, value } = signedParts(fraction, decimals);
  return `${sign}${value}%`;
}

/**
 * Same as {@link formatSignedPercent} but without the `%` suffix — §14-1's
 * 「個百分點」句式自己接上後綴文字，不是百分比符號。
 */
export function formatSignedPoints(fraction: number, decimals = 1): string {
  const { sign, value } = signedParts(fraction, decimals);
  return `${sign}${value}`;
}

/**
 * `delta_real` / `delta_shuffle` are already expressed in percentage points
 * (backend doc comment, `HistoricalStat.delta_real`) — never multiplied by
 * 100 here, only formatted to one decimal. S-3 (風控 ALL-1 複審裁定
 * 2026-09-25): a non-negative Δ carries **no** leading "+" (the sentence's
 * own verb "高出"／"高出全部族群平均" already states the direction; a "+"
 * would be redundant with the wording, unlike a signed return figure). A
 * negative Δ still shows its "-".
 */
export function formatPercentagePoints(pp: number, decimals = 1): string {
  const rounded = Number(pp.toFixed(decimals));
  const text = Math.abs(rounded).toFixed(decimals);
  return rounded < 0 ? `-${text}` : text;
}
