"use client";

import { KEY_LEVELS_TAGLINE } from "../../lib/sectionTaglines";
import { classifyRangeZone, computeKeyLevels } from "../../lib/keyLevels";
import type { AnchorSource, KeyLevels, RangeZone } from "../../lib/keyLevels";
import type { Bar } from "../../lib/types";

/**
 * 關鍵價位參考 (CEO 需求 2026-09-01；風控 2026-09-01 VETO R1–R12/S2–S5 後
 * 第二版)。全部面向使用者字面由 creative-lead 成稿
 * (`work/stock-desk-關鍵價位-文案成稿.md`)，逐字落地為本檔 exported 常數，
 * 待 risk-compliance-officer 逐字覆核；字面（含標點）不得再改動，任何變更
 * 視為漂移須重送風控。`componentWordingScan.test.ts` 逐字釘住＋禁用詞掃描。
 *
 * 落地條件 (風控 R7 / D4 V4)：所有揭露文字 ≥ text-sm、≥ text-neutral-400、
 * 常駐不摺疊——計算依據不得放進 <details>；S1 採納：大字不帶紅綠語意色。
 * 數值來源 `app/lib/keyLevels.ts`（display-layer derived；backend/quant
 * 正式化為追蹤中的 follow-up）。
 */

/* ---------- §0 標題與收盤列 ---------- */

export const KEY_LEVELS_PANEL_TITLE = "關鍵價位參考";

export function buildKeyLevelsCloseLine(x: string, d: string): string {
  return `收盤 ${x}（${d}）`;
}

/* ---------- §1 頭部揭露段（四句常駐，順序固定） ---------- */

export const KEY_LEVELS_PANEL_DISCLAIMER =
  "以下數字皆為本面板依固定算式計算之參考水位，僅供研究與教育用途，非投資建議，亦非任何買賣指示；" +
  "每個數字的計算方式，包括收盤資料的來源，皆在「計算依據」中逐項揭露。";

export const KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE =
  "本面板不判斷、也不另行標示所使用的日線資料是否已經過舊。";

export const KEY_LEVELS_HEADER_UNADJUSTED_NOTICE =
  "以下所有計算皆以未還原權值之原始收盤價進行；跨除權息日之區間、均線與 ATR(14) 可能因此失真。";

export const KEY_LEVELS_HEADER_DASH_NOTICE =
  "面板中以「—」呈現的欄位，代表可用日線根數尚未達最低計算門檻，並非數值為零或計算結果為零。";

/* ---------- §2 位階卡 ---------- */

export function buildRangeCardTitle(n: number): string {
  return `近 ${n} 根日線位階`;
}

export const KEY_LEVELS_ZONE_LABEL_LOW = "區間下緣";
export const KEY_LEVELS_ZONE_LABEL_MID = "區間中段";
export const KEY_LEVELS_ZONE_LABEL_HIGH = "區間上緣";

const ZONE_LABEL: Record<RangeZone, string> = {
  low: KEY_LEVELS_ZONE_LABEL_LOW,
  mid: KEY_LEVELS_ZONE_LABEL_MID,
  high: KEY_LEVELS_ZONE_LABEL_HIGH,
};

export function buildRangeLabel(n: number): string {
  return `近 ${n} 根區間`;
}

export const KEY_LEVELS_MA60_DEVIATION_LABEL = "對 MA60 乖離";

export function buildRangeNotValuationNote(n: number): string {
  return `位階描述價格相對自身近 ${n} 根區間的位置，不等於便宜或昂貴的估值判斷。`;
}

export function buildRangeInsufficientReason(n: number): string {
  return `日線根數不足，本次無法計算區間位階（僅有 ${n} 根，至少需要 60 根）。`;
}

export function buildRangeFlatReason(n: number): string {
  return `本次採樣的 ${n} 根日線中，最高價與最低價相同，位階公式的分母為零，無法定義位階。`;
}

/* ---------- §3 拉回觀察卡 ---------- */

export const KEY_LEVELS_PULLBACK_CARD_TITLE = "拉回觀察參考";

export const KEY_LEVELS_PULLBACK_EXPLAIN_NOTE =
  "本面板固定以 MA20、MA60、近 60 日低點作為拉回觀察區；是否跌破為觀察條件，不是進出指令；" +
  "並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料。";

export const KEY_LEVELS_PULLBACK_ROW_MA20 = "MA20";
export const KEY_LEVELS_PULLBACK_ROW_MA60 = "MA60";
export const KEY_LEVELS_PULLBACK_ROW_RECENT_LOW60 = "近 60 日低點";

/* ---------- §4 停損參考卡 ---------- */

export const KEY_LEVELS_STOP_CARD_TITLE = "停損參考";

export function buildStopBasisHeldWithCost(x: string): string {
  return `本卡以你的持倉平均成本 ${x} 為基準計算。`;
}

export function buildStopBasisConfirmedNotHeld(x: string): string {
  return `未持有此標的，以最新收盤 ${x} 試算；此數字不是任何進場暗示。`;
}

export function buildStopBasisUnknown(x: string): string {
  return `持倉成本尚未取得，暫以最新收盤 ${x} 試算。`;
}

export const KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE =
  "大字為 2×ATR(14) 與 −8% 兩者中較緊（虧損較小）者。";

export const KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE =
  "ATR(14) 資料不足，大字僅為 −8% 固定停損。";

export const KEY_LEVELS_STOP_ROW_ATR = "2×ATR(14)";
export const KEY_LEVELS_STOP_ROW_FIXED_PCT = "−8% 固定停損";

export const KEY_LEVELS_STOP_S5_NEUTRAL_NOTE =
  "停損參考水位與最新收盤的相對高低，因基準價與波動不同而不同，可能高於也可能低於最新收盤。";

/* ---------- §5 停利參考卡 ---------- */

export const KEY_LEVELS_TARGET_CARD_TITLE = "停利參考";

export const KEY_LEVELS_TARGET_ANCHOR_CROSS_REF =
  "本卡數字所用之基準價，與「停損參考」卡片相同。";

export const KEY_LEVELS_TARGET_STANDING_NOTICE =
  "以下數字皆由固定算式自基準價推得，僅為算式計算結果，不代表價格未來會到達此水位；" +
  "「2R」所稱賺賠比 2:1，僅描述算式中兩個差值之間的比例關係，不代表任何達成機率。";

export const KEY_LEVELS_TARGET_ROW_2R = "2R（賺賠比 2:1）";
export const KEY_LEVELS_TARGET_ROW_FIXED_PCT = "+20% 固定停利";
export const KEY_LEVELS_TARGET_ROW_TRAILING_LABEL = "移動停利觀察";

export const KEY_LEVELS_TARGET_ROW_TRAILING_NOTE =
  "（與「拉回觀察」卡片的 MA20 為同一數字；系統並未另行計算移動停利水位，僅以跌破 MA20 作為觀察條件）";

/* ---------- §6 計算依據（常駐清單，不摺疊——風控 R7） ---------- */

export const KEY_LEVELS_BASIS_SECTION_TITLE = "計算依據（逐項揭露）";

export function buildBasisClose(x: string, d: string): string {
  return (
    "收盤：本面板所有計算所稱之「收盤」，皆為系統行情資料鏈中該標的最近一根日線的收盤價，" +
    `與面板頂部「收盤 ${x}（${d}）」為同一數字。`
  );
}

export function buildBasisRange(n: number): string {
  return (
    `位階（近 ${n} 根區間）＝（收盤 − 近 ${n} 根 K 最低價）÷（近 ${n} 根 K 最高價 − 近 ${n} 根 K 最低價）×100%；` +
    `${n} 最多取 252 根，不足 252 根時以實際根數計算，未滿 60 根時不計算位階。`
  );
}

export const KEY_LEVELS_BASIS_ZONE =
  "分類：≤30% 標示為「區間下緣」、≥70% 標示為「區間上緣」，其餘標示為「區間中段」；" +
  "30%／70% 這兩個門檻為本面板自訂之分類標準，並無實證依據，亦非任何機構或研究之結論。";

export const KEY_LEVELS_BASIS_MA =
  "MA20／MA60＝最近 20／60 根收盤價之簡單平均；對 MA60 乖離＝收盤 ÷ MA60 − 1，以百分比表示。";

export const KEY_LEVELS_BASIS_RECENT_LOW60 = "近 60 日低點＝最近 60 根日線最低價中的最小值。";

export const KEY_LEVELS_BASIS_ATR =
  "ATR(14)＝最近 14 根日線真實波幅（TR）的簡單平均；未滿 15 根日線時無法計算，本面板不以其他方式估算或填補。";

export const KEY_LEVELS_BASIS_STOP =
  "停損參考：若 ATR(14) 可得，大字為「基準價 − 2×ATR(14)」與「基準價 × 0.92（固定 −8% 停損）」兩者中較緊（虧損較小）者；" +
  "若 ATR(14) 不可得，大字僅為「基準價 × 0.92」。本面板固定採 −8% 作為固定停損比例，僅為本面板自訂之算式參數，" +
  "並非本系統對任何族群實際行為的統計，本系統未持有此類統計資料。";

export const KEY_LEVELS_BASIS_TARGET =
  "停利參考：2R＝基準價 +2 ×（基準價 − 上方停損參考大字），此為算式定義下賺賠比 2:1 的計算結果，不代表任何達成機率；" +
  "固定停利＝基準價 × 1.2（本面板固定採 +20%），同樣僅為本面板自訂之算式參數，並非本系統對任何族群實際行為的統計，" +
  "本系統未持有此類統計資料；「移動停利觀察」顯示的是 MA20 的同一數字，系統並未另行計算移動停利水位，" +
  "僅以跌破 MA20 作為觀察條件。";

export const KEY_LEVELS_BASIS_ANCHOR =
  "基準價：若持有此標的且成本可得，為持倉平均成本；若持有此標的但持倉成本尚未取得，暫以最新收盤試算；" +
  "若確認未持有此標的，以最新收盤試算，此數字不是任何進場暗示。";

export const KEY_LEVELS_BASIS_PULLBACK =
  "拉回觀察區（MA20、MA60、近 60 日低點）為本面板固定採用之觀察價位，是否跌破為觀察條件，不是進出指令；" +
  "其餘限制說明見上方『拉回觀察參考』卡片，本處不重複列出。";

export const KEY_LEVELS_BASIS_UNADJUSTED_XREF =
  "以上計算皆以未還原權值之原始收盤價進行，跨除權息日可能失真；完整說明見面板頂部揭露。";

/* ---------- §7 無資料狀態句 ---------- */

export const KEY_LEVELS_NO_DATA_STATEMENT =
  "目前沒有可用的日線資料，本面板無法計算任何關鍵價位。";

/* ---------- §8 頁尾樣本句 ---------- */

export function buildFooterSample(n: number, d: string): string {
  return `計算樣本：${n} 根日線，最後一根 ${d}。本面板僅供研究與教育用途，不構成投資建議。`;
}

/* ---------- 呈現 ---------- */

function fmt(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return "—";
  return n.toLocaleString("zh-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(n: number | null): string {
  if (n === null || !Number.isFinite(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function LevelRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-sm text-neutral-400">{label}</span>
      <span className="font-mono text-sm text-neutral-100">{value}</span>
    </div>
  );
}

function anchorBasisSentence(source: AnchorSource, levels: KeyLevels): string {
  const x = fmt(levels.anchorPrice);
  if (source === "cost") return buildStopBasisHeldWithCost(x);
  if (source === "close-not-held") return buildStopBasisConfirmedNotHeld(x);
  return buildStopBasisUnknown(x);
}

export function KeyLevelsPanel({
  bars,
  avgCost,
  anchorSource,
}: {
  bars: Bar[];
  avgCost: number | null;
  anchorSource: AnchorSource;
}) {
  const levels = computeKeyLevels(bars, anchorSource === "cost" ? avgCost : null);

  if (levels === null) {
    return (
      <section className="mt-6 rounded-lg border border-neutral-800 p-4">
        <h2 className="text-lg font-semibold text-neutral-100">{KEY_LEVELS_PANEL_TITLE}</h2>
        <p className="mt-2 text-sm text-neutral-400">{KEY_LEVELS_NO_DATA_STATEMENT}</p>
      </section>
    );
  }

  const zone = levels.rangePositionPct !== null ? classifyRangeZone(levels.rangePositionPct) : null;

  return (
    <section className="mt-6 rounded-lg border border-neutral-800 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">{KEY_LEVELS_PANEL_TITLE}</h2>
        <span className="text-sm text-neutral-400">{buildKeyLevelsCloseLine(fmt(levels.close), levels.closeDate)}</span>
      </div>
      <p className="mt-1 text-sm text-neutral-300">{KEY_LEVELS_TAGLINE}</p>
      {/*
        頭部揭露常駐（順序依成稿 §9）；NON_REALTIME_NOTICE 依減負 FR-3（風控 C1–C4）
        改由頁級揭露區 <PageDisclosureSection> 單一呈現，本面板不再重複。
        均 ≥ text-sm、≥ neutral-400。
      */}
      <div className="mt-2 space-y-1 text-sm text-neutral-400">
        <p className="text-neutral-300">{KEY_LEVELS_PANEL_DISCLAIMER}</p>
        <p>{KEY_LEVELS_HEADER_STALENESS_SELF_NOTICE}</p>
        <p>{KEY_LEVELS_HEADER_UNADJUSTED_NOTICE}</p>
        <p>{KEY_LEVELS_HEADER_DASH_NOTICE}</p>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* 位階卡 */}
        <div className="rounded-md border border-neutral-800 bg-neutral-900/60 p-3">
          {zone !== null && levels.rangePositionPct !== null ? (
            <>
              <p className="text-sm text-neutral-400">{buildRangeCardTitle(levels.rangeBarCount)}</p>
              <p className="mt-1 text-xl font-bold text-neutral-100">
                {ZONE_LABEL[zone]}
                <span className="ml-2 align-middle font-mono text-sm font-normal text-neutral-400">
                  {levels.rangePositionPct.toFixed(0)}%
                </span>
              </p>
              <div className="mt-2 space-y-1">
                <LevelRow
                  label={buildRangeLabel(levels.rangeBarCount)}
                  value={`${fmt(levels.rangeLow)} – ${fmt(levels.rangeHigh)}`}
                />
                <LevelRow label={KEY_LEVELS_MA60_DEVIATION_LABEL} value={fmtPct(levels.ma60DeviationPct)} />
              </div>
              <p className="mt-2 text-sm text-neutral-400">{buildRangeNotValuationNote(levels.rangeBarCount)}</p>
            </>
          ) : (
            <>
              <p className="text-sm text-neutral-400">{buildRangeCardTitle(levels.rangeBarCount)}</p>
              <p className="mt-2 text-sm text-neutral-300">
                {levels.rangeUnavailableCause === "flat-range"
                  ? buildRangeFlatReason(levels.rangeBarCount)
                  : buildRangeInsufficientReason(levels.barCount)}
              </p>
            </>
          )}
        </div>

        {/* 拉回觀察卡 */}
        <div className="rounded-md border border-neutral-800 bg-neutral-900/60 p-3">
          <p className="text-sm text-neutral-400">{KEY_LEVELS_PULLBACK_CARD_TITLE}</p>
          <div className="mt-2 space-y-1">
            <LevelRow label={KEY_LEVELS_PULLBACK_ROW_MA20} value={fmt(levels.ma20)} />
            <LevelRow label={KEY_LEVELS_PULLBACK_ROW_MA60} value={fmt(levels.ma60)} />
            <LevelRow label={KEY_LEVELS_PULLBACK_ROW_RECENT_LOW60} value={fmt(levels.recentLow60)} />
          </div>
          <p className="mt-2 text-sm text-neutral-400">{KEY_LEVELS_PULLBACK_EXPLAIN_NOTE}</p>
        </div>

        {/* 停損參考卡 */}
        <div className="rounded-md border border-neutral-800 bg-neutral-900/60 p-3">
          <p className="text-sm text-neutral-400">{KEY_LEVELS_STOP_CARD_TITLE}</p>
          <p className="mt-1 text-sm text-neutral-300">{anchorBasisSentence(anchorSource, levels)}</p>
          <p className="mt-1 font-mono text-xl font-bold text-neutral-100">{fmt(levels.stopSuggested)}</p>
          <p className="mt-1 text-sm text-neutral-400">
            {levels.atr14 !== null ? KEY_LEVELS_STOP_CONDITION_ATR_AVAILABLE : KEY_LEVELS_STOP_CONDITION_ATR_UNAVAILABLE}
          </p>
          <div className="mt-2 space-y-1">
            <LevelRow label={KEY_LEVELS_STOP_ROW_ATR} value={fmt(levels.stopAtr)} />
            <LevelRow label={KEY_LEVELS_STOP_ROW_FIXED_PCT} value={fmt(levels.stopFixedPct)} />
          </div>
          <p className="mt-2 text-sm text-neutral-400">{KEY_LEVELS_STOP_S5_NEUTRAL_NOTE}</p>
        </div>

        {/* 停利參考卡 */}
        <div className="rounded-md border border-neutral-800 bg-neutral-900/60 p-3">
          <p className="text-sm text-neutral-400">{KEY_LEVELS_TARGET_CARD_TITLE}</p>
          <p className="mt-1 text-sm text-neutral-300">{KEY_LEVELS_TARGET_ANCHOR_CROSS_REF}</p>
          <p className="mt-1 font-mono text-xl font-bold text-neutral-100">{fmt(levels.target2R)}</p>
          <p className="mt-1 text-sm text-neutral-400">{KEY_LEVELS_TARGET_STANDING_NOTICE}</p>
          <div className="mt-2 space-y-1">
            <LevelRow label={KEY_LEVELS_TARGET_ROW_2R} value={fmt(levels.target2R)} />
            <LevelRow label={KEY_LEVELS_TARGET_ROW_FIXED_PCT} value={fmt(levels.targetFixedPct)} />
            <LevelRow label={KEY_LEVELS_TARGET_ROW_TRAILING_LABEL} value={fmt(levels.ma20)} />
          </div>
          <p className="mt-1 text-sm text-neutral-400">{KEY_LEVELS_TARGET_ROW_TRAILING_NOTE}</p>
        </div>
      </div>

      {/* 計算依據：常駐清單，不摺疊（風控 R7）；開頭以 R12 交叉引用句帶入 */}
      <div className="mt-4 rounded-md border border-neutral-800 bg-neutral-900/40 p-3">
        <h3 className="text-sm font-semibold text-neutral-300">{KEY_LEVELS_BASIS_SECTION_TITLE}</h3>
        <p className="mt-1 text-sm text-neutral-400">{KEY_LEVELS_BASIS_UNADJUSTED_XREF}</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-neutral-400">
          <li>{buildBasisClose(fmt(levels.close), levels.closeDate)}</li>
          <li>{buildBasisRange(levels.rangeBarCount)}</li>
          <li>{KEY_LEVELS_BASIS_ZONE}</li>
          <li>{KEY_LEVELS_BASIS_MA}</li>
          <li>{KEY_LEVELS_BASIS_RECENT_LOW60}</li>
          <li>{KEY_LEVELS_BASIS_ATR}</li>
          <li>{KEY_LEVELS_BASIS_STOP}</li>
          <li>{KEY_LEVELS_BASIS_TARGET}</li>
          <li>{KEY_LEVELS_BASIS_ANCHOR}</li>
          <li>{KEY_LEVELS_BASIS_PULLBACK}</li>
        </ul>
      </div>
      <p className="mt-2 text-sm text-neutral-400">{buildFooterSample(levels.barCount, levels.closeDate)}</p>
    </section>
  );
}
