import type {
  BetaResult,
  DrawdownResult,
  IndicatorResult,
  SignalsPayload,
  VolatilityResult,
} from "../../lib/types";
import { formatNumber, formatPercent } from "../../lib/format";
import { kdBand, percentBBand, rsiBand, volumeZBand } from "../../lib/indicatorBands";
import type { IndicatorBand } from "../../lib/indicatorBands";
import { buildFooterGuidance } from "../../lib/footerDisclosureWording";
import { TECHNICAL_ANALYSIS_TITLE } from "../../lib/sectionTitles";

/**
 * FR-C2 (Phase 8): renders every technical/risk indicator `compute_signals()`
 * already produces (app/signals/service.py, verified) — no indicator math
 * lives here, this component only formats the `IndicatorResult` /
 * `VolatilityResult` / `DrawdownResult` / `BetaResult` shapes verbatim as
 * received from `GET /api/signals/{symbol}`. Every card honours the signal
 * layer's own `insufficient_data` semantics: an empty `series` never gets a
 * chart, and a `null` `last` value is shown as an explicit reason, never a
 * blank or a zero (AC-C2.2, AC-C2.3).
 */

const RECENT_ROWS = 5;

/* ---------- 圖形化 item 3 (CEO 2026-09-06)：指標速覽與區帶標籤 ---------- */

/**
 * Band chips: every indicator that has a textbook 0–100 / 0–1 / z scale gets a
 * small glyph+colour+label chip saying which band its latest value sits in.
 * Bands come from `app/lib/indicatorBands.ts` (pure, tested); this file only
 * maps band → chip.
 *
 * 風控 2026-09-06 圖形化審查 R1/R2/R3/R8 落地：
 * - R1: glyphs are FILL levels (○ ◐ ●), never direction arrows/triangles —
 *   `componentWordingScan.test.ts` rejects arrow/triangle glyphs in this file.
 * - R2: colour is ONE hue in three steps (sky-950 → sky-800), the same
 *   sequential device `RangeGauge` uses; amber stays reserved for the page's
 *   warning vocabulary (insufficient / stale / downgraded), so a 高區帶 chip
 *   can never look like an alert.
 * - R3/R4: no 收盤 vs MA chip — a binary relation is not a band, and its
 *   inputs would have crossed two API payloads with different timestamps.
 * - R8: chips render ONLY inside 指標速覽, next to the legend sentence that
 *   says what the colour does and does not mean; per-card chips were removed.
 * Every chip's wording is an exported constant pinned by
 * `componentWordingScan.test.ts`; the threshold in brackets is the exact number
 * the classifier uses.
 */

export const INDICATOR_OVERVIEW_TITLE = "指標速覽";

export const INDICATOR_OVERVIEW_LEGEND =
  "色帶只標示各指標最新值落在自身量尺的哪個區帶（低／中／高），不代表多空方向，也不是任何買賣判斷。";

export const INDICATOR_OVERVIEW_EMPTY = "目前沒有可分區帶的指標數值。";

export const RSI_BAND_LABELS: Record<IndicatorBand, string> = {
  low: "RSI 低區帶（≤30）",
  mid: "RSI 中區帶（30–70）",
  high: "RSI 高區帶（≥70）",
};

export const KD_BAND_LABELS: Record<IndicatorBand, string> = {
  low: "K 值低區帶（≤20）",
  mid: "K 值中區帶（20–80）",
  high: "K 值高區帶（≥80）",
};

export const PERCENT_B_BAND_LABELS: Record<IndicatorBand, string> = {
  low: "%B 低於下軌（<0）",
  mid: "%B 通道內（0–1）",
  high: "%B 高於上軌（>1）",
};

export const VOLUME_Z_BAND_LABELS: Record<IndicatorBand, string> = {
  low: "成交量明顯偏低（z≤−2）",
  mid: "成交量接近近期平均（|z|<2）",
  high: "成交量明顯偏高（z≥2）",
};

const BAND_CHIP_CLASS: Record<IndicatorBand, string> = {
  low: "border-sky-900 bg-sky-950/40 text-sky-200",
  mid: "border-sky-800 bg-sky-900/50 text-sky-100",
  high: "border-sky-600 bg-sky-800/60 text-sky-50",
};

/** Fill-level glyphs (R1): empty / half / full — position on a scale, not a direction. */
const BAND_ICON: Record<IndicatorBand, string> = { low: "○", mid: "◐", high: "●" };

function BandChip({ band, label }: { band: IndicatorBand; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${BAND_CHIP_CLASS[band]}`}
    >
      <span aria-hidden="true">{BAND_ICON[band]}</span>
      {label}
    </span>
  );
}

interface OverviewChip {
  key: string;
  band: IndicatorBand;
  label: string;
}

/**
 * Collects every chip the payload supports. A `null` band (indicator
 * insufficient) contributes nothing — the card's own insufficient-data note
 * stays the single explanation.
 */
function collectOverviewChips(payload: SignalsPayload): OverviewChip[] {
  const tech = payload.technical;
  if (!tech) return [];
  const chips: OverviewChip[] = [];

  const rsi = tech.rsi.status === "ok" ? rsiBand(tech.rsi.last.rsi ?? null) : null;
  if (rsi !== null) chips.push({ key: "rsi", band: rsi, label: RSI_BAND_LABELS[rsi] });

  const kd = tech.kd.status === "ok" ? kdBand(tech.kd.last.k ?? null) : null;
  if (kd !== null) chips.push({ key: "kd", band: kd, label: KD_BAND_LABELS[kd] });

  const pb = tech.bollinger.status === "ok" ? percentBBand(tech.bollinger.last.percent_b ?? null) : null;
  if (pb !== null) chips.push({ key: "bollinger", band: pb, label: PERCENT_B_BAND_LABELS[pb] });

  const vz = tech.volume_zscore.status === "ok" ? volumeZBand(tech.volume_zscore.last.zscore ?? null) : null;
  if (vz !== null) chips.push({ key: "volume_zscore", band: vz, label: VOLUME_Z_BAND_LABELS[vz] });

  return chips;
}

function IndicatorOverview({ chips }: { chips: OverviewChip[] }) {
  return (
    <div className="rounded-lg border border-neutral-800 bg-neutral-900/40 p-4">
      <h4 className="text-sm font-semibold text-neutral-100">{INDICATOR_OVERVIEW_TITLE}</h4>
      <div className="mt-2">
        <ChipsList chips={chips} />
      </div>
      {/*
        Legend (`INDICATOR_OVERVIEW_LEGEND`)：CEO 第二次裁定 2026-09-06 推翻風控 A+8，下沉頁尾
        （`buildTechnicalFooterItems`）；原位留指引句（L5）。
      */}
      <p className="mt-2 text-sm text-neutral-300">{buildFooterGuidance(TECHNICAL_ANALYSIS_TITLE)}</p>
    </div>
  );
}

function ChipsList({ chips }: { chips: OverviewChip[] }) {
  if (chips.length === 0) return <p className="text-sm text-neutral-400">{INDICATOR_OVERVIEW_EMPTY}</p>;
  return (
    <ul className="flex flex-wrap gap-2">
      {chips.map((chip) => (
        <li key={chip.key}>
          <BandChip band={chip.band} label={chip.label} />
        </li>
      ))}
    </ul>
  );
}

/**
 * 一眼一句 §2.2 主視圖：只放 chips 一列（無標題／無圖例／無 footer 指引），供
 * `page.tsx` 在技術分析主視圖直接渲染；完整版（標題＋圖例指引＋同一份 chips）
 * 留在 `<details>` 內的 `IndicatorOverview`（見上）——`collectOverviewChips`
 * 是唯一的資料來源，兩處不會算出不同的 chips。
 */
export function IndicatorOverviewChipsRow({ payload }: { payload: SignalsPayload }) {
  if (!payload.technical) return null;
  return (
    <div className="mt-3">
      <ChipsList chips={collectOverviewChips(payload)} />
    </div>
  );
}

function requiredBarsLabel(name: string, window: Record<string, number>): string {
  switch (name) {
    case "rsi":
    case "atr":
      return `${(window.period ?? 0) + 1} 根`;
    case "macd":
      return `${(window.slow ?? 0) + (window.signal ?? 0)} 根`;
    case "bollinger":
    case "volume_zscore":
      return `${window.window ?? 0} 根`;
    case "kd":
      return `${window.period ?? 0} 根`;
    default:
      return "更多根";
  }
}

function IndicatorCard({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <h4 className="text-sm font-semibold text-neutral-100">{title}</h4>
      <p className="mt-1 text-xs text-neutral-500">{description}</p>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function InsufficientNote({ message }: { message: string }) {
  return (
    <p className="rounded-md border border-amber-800 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
      {message}
    </p>
  );
}

function RecentValuesTable({
  dates,
  series,
  lines,
  formatter = (value: number | null) => formatNumber(value, 2),
}: {
  dates: string[];
  series: Record<string, (number | null)[]>;
  lines: { key: string; label: string }[];
  formatter?: (value: number | null) => string;
}) {
  if (dates.length === 0) return null;
  const start = Math.max(0, dates.length - RECENT_ROWS);
  const recentDates = dates.slice(start);
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-xs text-neutral-400">
        <thead>
          <tr className="border-b border-neutral-800 text-neutral-500">
            <th className="py-1 pr-3 font-normal">日期</th>
            {lines.map((line) => (
              <th key={line.key} className="py-1 pr-3 font-normal">
                {line.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {recentDates.map((date, i) => {
            const idx = start + i;
            return (
              <tr key={date}>
                <td className="py-1 pr-3">{date}</td>
                {lines.map((line) => (
                  <td key={line.key} className="py-1 pr-3">
                    {formatter(series[line.key]?.[idx] ?? null)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** MA5/MA20/MA60 each has its own sufficiency window, even when the overall indicator `status` is `ok` (AC-C2.2). */
function MovingAveragesCard({ result, barCount }: { result: IndicatorResult; barCount: number }) {
  const windows: { key: string; label: string; window: number }[] = [
    { key: "ma_5", label: "MA5", window: 5 },
    { key: "ma_20", label: "MA20", window: 20 },
    { key: "ma_60", label: "MA60", window: 60 },
  ];
  return (
    <IndicatorCard
      title="移動平均線（MA5／MA20／MA60）"
      description="近 N 日收盤價的簡單平均，用於觀察價格趨勢；三個天期分別各自判斷資料是否足夠，不以其他天期的數值代替。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote message={`資料不足，目前僅 ${barCount} 根日線，最短的 MA5 也需要至少 5 根。`} />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {windows.map((w) => {
            const value = result.last[w.key] ?? null;
            return (
              <div key={w.key}>
                <p className="text-xs text-neutral-500">{w.label}</p>
                {value === null ? (
                  <p className="mt-1 text-xs text-amber-300">
                    資料不足，需要至少 {w.window} 根日線（目前 {barCount} 根）。
                  </p>
                ) : (
                  <p className="mt-1 text-sm text-neutral-200">{formatNumber(value, 2)}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </IndicatorCard>
  );
}

function RsiCard({ result, barCount }: { result: IndicatorResult; barCount: number }) {
  return (
    <IndicatorCard
      title="RSI（14 日相對強弱指標）"
      description="以近 14 日漲跌幅計算的動能數值，範圍 0–100，僅為數值觀察，不代表買賣訊號。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote
          message={`資料不足，需要至少 ${requiredBarsLabel("rsi", result.inputs_used.window)}日線（目前 ${barCount} 根）。`}
        />
      ) : (
        <>
          <p className="text-sm text-neutral-200">最新值：{formatNumber(result.last.rsi ?? null, 2)}</p>
          <RecentValuesTable
            dates={result.dates}
            series={result.series}
            lines={[{ key: "rsi", label: "RSI" }]}
          />
        </>
      )}
    </IndicatorCard>
  );
}

function KdCard({ result, barCount }: { result: IndicatorResult; barCount: number }) {
  return (
    <IndicatorCard
      title="KD 隨機指標（9,3,3）"
      description="收盤價於近期高低區間之相對位置，K、D 介於 0–100；僅為數值觀察。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote
          message={`資料不足，需要至少 ${requiredBarsLabel("kd", result.inputs_used.window)}日線（目前 ${barCount} 根）。`}
        />
      ) : (
        <>
          <p className="text-sm text-neutral-200">
            K：{formatNumber(result.last.k ?? null, 2)}　D：{formatNumber(result.last.d ?? null, 2)}
          </p>
          <RecentValuesTable
            dates={result.dates}
            series={result.series}
            lines={[
              { key: "k", label: "K" },
              { key: "d", label: "D" },
            ]}
          />
        </>
      )}
    </IndicatorCard>
  );
}

function MacdCard({ result, barCount }: { result: IndicatorResult; barCount: number }) {
  return (
    <IndicatorCard
      title="MACD（12,26,9）"
      description="短期與長期指數移動平均線的差值，用於觀察趨勢動能變化，數值本身不代表買賣訊號。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote
          message={`資料不足，需要至少 ${requiredBarsLabel("macd", result.inputs_used.window)}日線（目前 ${barCount} 根）。`}
        />
      ) : (
        <>
          <p className="text-sm text-neutral-200">
            MACD：{formatNumber(result.last.macd ?? null, 2)}　訊號線：
            {formatNumber(result.last.signal ?? null, 2)}
            　柱狀圖：{formatNumber(result.last.histogram ?? null, 2)}
          </p>
          <RecentValuesTable
            dates={result.dates}
            series={result.series}
            lines={[
              { key: "macd", label: "MACD" },
              { key: "signal", label: "訊號線" },
              { key: "histogram", label: "柱狀圖" },
            ]}
          />
        </>
      )}
    </IndicatorCard>
  );
}

function BollingerCard({ result, barCount }: { result: IndicatorResult; barCount: number }) {
  return (
    <IndicatorCard
      title="布林通道（20 日，2 倍標準差）"
      description="以 20 日均線為中軌、加減 2 倍標準差為上下軌，用於觀察價格相對近期波動區間的位置。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote
          message={`資料不足，需要至少 ${requiredBarsLabel("bollinger", result.inputs_used.window)}日線（目前 ${barCount} 根）。`}
        />
      ) : (
        <>
          <p className="text-sm text-neutral-200">
            上軌：{formatNumber(result.last.upper ?? null, 2)}　中軌：
            {formatNumber(result.last.middle ?? null, 2)}
            　下軌：{formatNumber(result.last.lower ?? null, 2)}
          </p>
          <p className="mt-1 text-xs text-neutral-500">
            %B：{formatPercent(result.last.percent_b ?? null)}　通道寬度：
            {formatPercent(result.last.bandwidth ?? null)}
          </p>
          <RecentValuesTable
            dates={result.dates}
            series={result.series}
            lines={[
              { key: "upper", label: "上軌" },
              { key: "middle", label: "中軌" },
              { key: "lower", label: "下軌" },
            ]}
          />
        </>
      )}
    </IndicatorCard>
  );
}

function AtrCard({ result, barCount }: { result: IndicatorResult; barCount: number }) {
  return (
    <IndicatorCard
      title="ATR（14 日真實波幅均值）"
      description="衡量近期價格波動幅度之統計量；不代表方向。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote
          message={`資料不足，需要至少 ${requiredBarsLabel("atr", result.inputs_used.window)}日線（目前 ${barCount} 根）。`}
        />
      ) : (
        <>
          <p className="text-sm text-neutral-200">最新值：{formatNumber(result.last.atr ?? null, 2)}</p>
          <RecentValuesTable
            dates={result.dates}
            series={result.series}
            lines={[{ key: "atr", label: "ATR" }]}
          />
        </>
      )}
    </IndicatorCard>
  );
}

function VolumeZscoreCard({ result, barCount }: { result: IndicatorResult; barCount: number }) {
  const anomaly = result.last.anomaly ?? null;
  return (
    <IndicatorCard
      title="成交量 Z 分數（20 日）"
      description="衡量當日成交量偏離近 20 日平均之程度（正值偏高、負值偏低）；屬統計描述，不代表方向判斷。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote
          message={`資料不足，需要至少 ${requiredBarsLabel("volume_zscore", result.inputs_used.window)}日線（目前 ${barCount} 根）。`}
        />
      ) : (
        <>
          <p className="text-sm text-neutral-200">最新值：{formatNumber(result.last.zscore ?? null, 2)}</p>
          {anomaly === 1 && (
            <p className="mt-1 text-xs text-amber-300">最新一日成交量明顯偏離近期平均。</p>
          )}
          <RecentValuesTable
            dates={result.dates}
            series={result.series}
            lines={[{ key: "zscore", label: "Z 分數" }]}
          />
        </>
      )}
    </IndicatorCard>
  );
}

function VolatilityCard({ result }: { result: VolatilityResult }) {
  return (
    <IndicatorCard
      title="年化波動度"
      description="以近期日報酬標準差換算之年化數值，衡量價格波動程度之統計量；不代表方向或預測。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote message="資料不足，可用的日報酬筆數不足以計算。" />
      ) : (
        <p className="text-sm text-neutral-200">
          年化：{formatPercent(result.annualized_volatility)}　日：
          {formatPercent(result.daily_volatility, 3)}
        </p>
      )}
    </IndicatorCard>
  );
}

function DrawdownCard({ result }: { result: DrawdownResult }) {
  return (
    <IndicatorCard
      title="最大回撤"
      description="觀察區間內高點到低點之最大跌幅，屬歷史統計描述，不代表未來會重演。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote message="資料不足，可用天數不足以計算。" />
      ) : (
        <p className="text-sm text-neutral-200">
          {formatPercent(result.max_drawdown)}（高點 {result.peak_date ?? "—"} → 低點{" "}
          {result.trough_date ?? "—"}）
        </p>
      )}
    </IndicatorCard>
  );
}

function BetaCard({ result }: { result: BetaResult }) {
  return (
    <IndicatorCard
      title="Beta（相對比較基準指數的敏感度）"
      description="衡量此標的報酬相對比較基準指數（大盤）的敏感程度，數值來自過去資料的統計關係。"
    >
      {result.status === "insufficient_data" ? (
        <InsufficientNote
          message={
            result.benchmark === null
              ? "資料不足：缺少比較基準指數的資料，無法計算 Beta。"
              : "資料不足：與比較基準指數的重疊資料筆數不足以計算。"
          }
        />
      ) : (
        <p className="text-sm text-neutral-200">
          {formatNumber(result.beta, 2)}（比較基準：{result.benchmark ?? "—"}）
        </p>
      )}
    </IndicatorCard>
  );
}

export function TechnicalIndicatorsPanel({ payload }: { payload: SignalsPayload }) {
  const barCount = payload.bar_count;
  const tech = payload.technical;
  const risk = payload.risk;

  if (!tech && !risk) {
    return (
      <InsufficientNote message="本次回應未包含技術指標與風險量測，請稍後重試。" />
    );
  }

  return (
    <div className="space-y-6">
      {tech && <IndicatorOverview chips={collectOverviewChips(payload)} />}
      {tech && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
            技術指標
          </h4>
          <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <MovingAveragesCard result={tech.moving_averages} barCount={barCount} />
            <RsiCard result={tech.rsi} barCount={barCount} />
            <KdCard result={tech.kd} barCount={barCount} />
            <MacdCard result={tech.macd} barCount={barCount} />
            <BollingerCard result={tech.bollinger} barCount={barCount} />
            <AtrCard result={tech.atr} barCount={barCount} />
            <VolumeZscoreCard result={tech.volume_zscore} barCount={barCount} />
          </div>
        </div>
      )}

      {risk && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
            風險量測
          </h4>
          <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-2">
            <VolatilityCard result={risk.volatility} />
            <DrawdownCard result={risk.drawdown} />
            <BetaCard result={risk.beta} />
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * The 技術分析 group of `PageFooterDisclosures` (CEO 第二次裁定 2026-09-06): the
 * overview legend, exactly when the overview strip (and its pointer) renders —
 * i.e. the payload carries a technical block.
 */
export function buildTechnicalFooterItems(payload: SignalsPayload): string[] {
  return payload.technical ? [INDICATOR_OVERVIEW_LEGEND] : [];
}
