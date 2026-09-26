"use client";

import { Fragment } from "react";
import Link from "next/link";
import { AS_OF_CALENDAR_UNCONFIRMED_STATEMENT } from "../lib/adviceWording";
import { numberColorClass } from "../lib/format";
import { buildDataAsOfBadge } from "../lib/oneLinerWording";
import { useSectorMomentum } from "../lib/queries";
import {
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
  computeConfidenceLevelPercent,
  COST_DEFINITION_SENTENCE,
  DEMO_DATA_CARD_WARNING,
  DISPLAY_THRESHOLD_RULE_SENTENCE,
  GROSS_COST_GROUP_TITLE,
  HISTORICAL_STAT_SECTOR_ONLY_SENTENCE,
  KNOWN_NOT_EVALUATED_REASONS,
  KNOWN_SECTOR_REASON_CODES,
  NET_COST_GROUP_TITLE,
  notEvaluatedSentences,
  SAMPLING_RULE_LABEL,
  SECTOR_CARD_TITLE,
  SECTOR_HELD_BADGE,
  SECTOR_NOT_HELD_BADGE,
  SINGLE_STOCK_DOMINATED_TAG,
  T8_1_SENTENCE,
  thresholdPercent,
  TWSE_ONLY_TAG,
} from "../lib/sectorMomentumWording";
import type { SectorConstituent, SectorMomentumResponse, SectorRankedItem } from "../lib/types";
import { DataMetaStatusBadge } from "./DataMetaStatusBadge";
import { ErrorPanel } from "./ErrorPanel";
import { InsufficientPanel } from "./InsufficientPanel";
import { SkeletonBlock } from "./SkeletonBlock";

/**
 * 後端 §6.2(d) 揭露句（`app/api/sectors_wording.py::TAIEX_REFERENCE`）逐字複
 * 製，**只用來在 `disclosures` 陣列中定位插入點**（緊接其前插入加權指數參考
 * 數字，風控 ALL-1 複審裁定），本身從不在畫面上單獨渲染——實際顯示的字串一
 * 律來自後端回應的 `disclosures`，不是這個常數。
 */
const TAIEX_REFERENCE_SENTENCE =
  "加權指數報酬僅供參考，不用於排名或歷史比例的判定；兩者一律以等權全市場為基準。" +
  "加權指數以市值加權且不含股利，與等權全市場不可直接比較。";

/**
 * 詳細展開的摺疊摘要文字——UI chrome，非風控逐字定稿句（比照既有 `<details>`
 * 慣例）。刻意維持最短（僅「詳細」二字，本卡全文一律用此詞指稱展開區，見派工
 * 單各節「詳細」用語），因為 `<summary>` 本身在收合態即可見，計入 170 字上限。
 */
const DETAILS_SUMMARY = "詳細";

/**
 * `gate_status` 的三態敘事（派工單 R-4 required）：`ok` 攜帶主視圖句與詳細句；
 * `unrecognized` 是「`not_evaluated` 但 `not_evaluated_reason` 為 null／不認得
 * 的碼」或「`passed`／`failed` 卻沒有 `historical_stat`」——這兩種都是契約破
 * 壞，不得照常顯示排行而沒有這句，必須改走 `ErrorPanel`。
 */
type HistoricalNarrative =
  | { kind: "ok"; main: string; detail: string[] }
  | { kind: "unrecognized" };

function resolveHistoricalNarrative(data: SectorMomentumResponse): HistoricalNarrative {
  const lookbackDays = data.lookback_days ?? 5;
  const holdingDays = data.holding_days ?? 5;

  if (data.gate_status === "not_evaluated") {
    const reason = data.not_evaluated_reason;
    if (reason === null || !KNOWN_NOT_EVALUATED_REASONS.includes(reason)) {
      return { kind: "unrecognized" };
    }
    const { main, detail } = notEvaluatedSentences({
      reason,
      lookbackDays,
      pitGaps: data.pit_gaps,
      accumulation: data.accumulation,
    });
    return { kind: "ok", main, detail };
  }

  if (data.gate_status === "failed" || data.gate_status === "passed") {
    const stat = data.historical_stat;
    if (stat === null) return { kind: "unrecognized" };
    // §13.5-5／-7／-4：passed／failed 皆附這七句 + 四數（僅主視圖句不同）。
    const detail = [
      HISTORICAL_STAT_SECTOR_ONLY_SENTENCE,
      buildStatsAsOfSentence(stat),
      COST_DEFINITION_SENTENCE,
      DISPLAY_THRESHOLD_RULE_SENTENCE,
      buildReturnWindowSentence(holdingDays),
      T8_1_SENTENCE,
      buildT82Sentence(stat),
    ];
    const main =
      data.gate_status === "failed" ? buildFailedMainSentence(lookbackDays) : buildPassedMainSentence(stat, holdingDays);
    return { kind: "ok", main, detail };
  }

  // Unrecognized `gate_status` string (contract drift) — fail closed, never
  // render a ranking with no historical sentence (R-4).
  return { kind: "unrecognized" };
}

/**
 * §6.3 H-1：字級與對比皆不低於正文（本卡成分股列 `text-sm`）——徽章不得用
 * `text-xs`，也不得用紅／綠／金色（H-4），不得 hover-only 或以圖示取代文字
 * （H-3；本徽章一律是可見文字，從不隱藏於 hover）。
 */
function heldBadge(held: boolean | null) {
  if (held === null) return null;
  return (
    <span className="ml-2 rounded bg-neutral-800 px-1.5 py-0.5 text-sm text-neutral-200">
      {held ? SECTOR_HELD_BADGE : SECTOR_NOT_HELD_BADGE}
    </span>
  );
}

function ConstituentRow({ item }: { item: SectorConstituent }) {
  return (
    <li className="flex items-center justify-between gap-2 text-sm">
      <Link
        href={`/position/${encodeURIComponent(item.symbol)}?market=TW`}
        className="text-sky-400 underline hover:text-sky-300"
      >
        {item.symbol} {item.name}
      </Link>
      <span className="flex items-center">
        {item.return_L !== null ? (
          <span className={`font-mono ${numberColorClass(item.return_L)}`}>
            {(item.return_L * 100) >= 0 ? "+" : ""}
            {(item.return_L * 100).toFixed(1)}%
          </span>
        ) : (
          <span className="text-neutral-500">—</span>
        )}
        {heldBadge(item.held)}
      </span>
    </li>
  );
}

function SectorBlock({ sector, lookbackDays }: { sector: SectorRankedItem; lookbackDays: number }) {
  return (
    <div className="rounded-md border border-neutral-800 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-neutral-100">{sector.sector_name}</span>
          {/* §14-3：主視圖該族群區塊內 tag（單一個股集中，主視圖與詳細皆渲染，
              因為 SectorBlock 兩處共用）。 */}
          {sector.single_stock_dominated && (
            <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-sm text-neutral-300">
              {SINGLE_STOCK_DOMINATED_TAG}
            </span>
          )}
        </span>
        {/* §14-1：主視圖與「詳細」完整排行同句式，改綁 rel_return_L（排名依據）。 */}
        {sector.rel_return_L !== null ? (
          <span className={`font-mono text-sm ${numberColorClass(sector.rel_return_L)}`}>
            {buildRelativeReturnSentence(sector.rel_return_L, lookbackDays)}
          </span>
        ) : (
          <span className="text-sm text-neutral-500">—</span>
        )}
      </div>
      <p className="mt-1 text-sm text-neutral-400">{buildUpCountLabel(sector.up_count, sector.constituent_count)}</p>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-neutral-400">
        <span>{buildConstituentHeader(lookbackDays, sector.constituent_count)}</span>
        {/* 族群層級缺漏 tag（風控 ALL-1 複審裁定）：{m} 綁本族群自己的
            coverage.missing_count，與卡片層級的 market_missing_count 各自獨立。 */}
        {sector.coverage.missing_count > 0 && (
          <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-sm text-neutral-300">
            {buildSectorMissingTag(sector.coverage.missing_count)}
          </span>
        )}
      </p>
      <ul className="mt-1 space-y-1">
        {sector.constituents.map((item) => (
          <ConstituentRow key={item.symbol} item={item} />
        ))}
      </ul>
    </div>
  );
}

/**
 * Pure half of the card, split out so it can be unit-tested with
 * `renderToStaticMarkup` (same convention as `AlertStatusStripView`).
 */
export function SectorMomentumCardView({ data }: { data: SectorMomentumResponse }) {
  const lookbackDays = data.lookback_days ?? 5;
  const demoWarning = data.data_source === "demo_synthetic";
  const asOfBadge = buildDataAsOfBadge(data.data_as_of);
  const staleSentence =
    data.data.trading_days_behind !== null && data.data.trading_days_behind >= 1
      ? buildStaleDataSentence(data.data_as_of ?? "", data.data.trading_days_behind)
      : null;
  const calendarUnconfirmed = data.data.trading_days_behind === null;
  const exDateTagText = data.ex_date_tag ? buildExDateTag(data.market_ex_date_excluded_count ?? 0) : null;
  const marketMissingTagText =
    data.status === "ok" && data.market_missing_count !== null && data.market_missing_count > 0
      ? buildMarketMissingTag(data.market_missing_count)
      : null;

  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      {/* NE-8 卡片層級常駐警告（IP-6，絕對底線，依 data_source 驅動，不受 status 影響）。 */}
      {demoWarning && (
        <p role="alert" className="mb-2 rounded border border-amber-800 bg-amber-950/30 px-2 py-1 text-sm text-amber-300">
          {DEMO_DATA_CARD_WARNING}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">{SECTOR_CARD_TITLE}</h2>
        <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-300">
          {buildLookbackChip(lookbackDays)}
        </span>
        <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-300">{TWSE_ONLY_TAG}</span>
        {asOfBadge !== null && (
          <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-300">{asOfBadge}</span>
        )}
        {exDateTagText !== null && (
          <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-300">{exDateTagText}</span>
        )}
        {marketMissingTagText !== null && (
          <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-neutral-300">{marketMissingTagText}</span>
        )}
      </div>

      {/* §4.5-3／§4.5-4：資料過舊、交易日曆無法確認（主視圖常駐，IP-6 不足態亦常駐）。 */}
      {staleSentence !== null && <p className="mt-2 text-sm text-neutral-300">{staleSentence}</p>}
      {calendarUnconfirmed && <p className="mt-2 text-sm text-neutral-300">{AS_OF_CALENDAR_UNCONFIRMED_STATEMENT}</p>}

      {data.status === "insufficient_data" ? (
        data.reason === null ? (
          // F-1（風控 ALL-1 複審裁定）：IP-1 要求「不足狀態一律傳入非 null 的
          // reason」；reason 為 null 是契約破壞，不得落到 InsufficientPanel 的
          // 「資料不足，無法計算。」退回字面，改走 ErrorPanel（沿用既有元件的
          // 「未知錯誤」字面，不新造使用者可見文案，S-4）。
          <div className="mt-3">
            <ErrorPanel label={SECTOR_CARD_TITLE} error={new Error("insufficient_data 但 reason 為 null")} />
          </div>
        ) : (
          <>
            <div className="mt-3">
              <InsufficientPanel reason={data.reason} />
            </div>
            <details className="group mt-3">
              <summary className="cursor-pointer text-sm text-neutral-400 hover:text-neutral-300">
                {DETAILS_SUMMARY}
              </summary>
              <div className="mt-2 space-y-2 border-t border-neutral-800 pt-2 text-xs text-neutral-400">
                {data.disclosures.map((sentence, index) => (
                  // eslint-disable-next-line react/no-array-index-key -- IP-5: exactly one fixed reason sentence, order is stable.
                  <p key={index}>{sentence}</p>
                ))}
              </div>
            </details>
          </>
        )
      ) : (
        <SectorMomentumOkBody data={data} lookbackDays={lookbackDays} />
      )}
    </section>
  );
}

function SectorMomentumOkBody({ data, lookbackDays }: { data: SectorMomentumResponse; lookbackDays: number }) {
  const narrative = resolveHistoricalNarrative(data);

  // R-4: an unrecognized gate_status / not_evaluated_reason must never render
  // a ranking with no historical sentence — fail closed to ErrorPanel.
  if (narrative.kind === "unrecognized") {
    return (
      <div className="mt-3">
        <ErrorPanel label={SECTOR_CARD_TITLE} error={new Error("gate_status 或 not_evaluated_reason 無法辨識")} />
      </div>
    );
  }

  // S-2：任一被排除族群的 reason_code 不認得時，同樣不得照常顯示排行——改走
  // ErrorPanel，不自行造一句「未知原因」文案（沿用 ErrorPanel 既有「未知錯
  // 誤」字面）。
  const hasUnknownExclusionReason = data.excluded_sectors.some(
    (item) => !KNOWN_SECTOR_REASON_CODES.includes(item.reason_code),
  );
  if (hasUnknownExclusionReason) {
    return (
      <div className="mt-3">
        <ErrorPanel label={SECTOR_CARD_TITLE} error={new Error("excluded_sectors 的 reason_code 無法辨識")} />
      </div>
    );
  }

  // §14-1 required：整卡一次的「等權全市場報酬」數字是 board 層級數字，理論上
  // 每個族群的 benchmark_return_L 都應相等；不相等即契約破壞，改走 ErrorPanel。
  const benchmarkReturns = new Set(data.sectors.map((sector) => sector.benchmark_return_L));
  if (benchmarkReturns.size > 1) {
    return (
      <div className="mt-3">
        <ErrorPanel label={SECTOR_CARD_TITLE} error={new Error("sectors[].benchmark_return_L 不一致")} />
      </div>
    );
  }
  const benchmarkReturn = data.sectors[0]?.benchmark_return_L ?? null;

  const headline = data.sectors.slice(0, data.headline_count);
  const heldUnknown = data.sectors.some((sector) => sector.constituents.some((item) => item.held === null));
  const holdingDays = data.holding_days ?? 5;
  const stat = data.historical_stat;
  // 加權指數參考數字：整卡只取一次（board 層級數字複寫在每個 SectorItem 上，
  // 取第一個非 null 的即可），只放「詳細」，緊接後端 §6.2(d) 揭露句之前。
  const taiexReturn = data.sectors.find((sector) => sector.reference_taiex_return_L !== null)
    ?.reference_taiex_return_L ?? null;

  return (
    <>
      {/* §14-4：取樣規則標籤，卡片層級一次，放在第一個族群區塊正上方（僅在至少
          渲染一個族群時），字級不小於 text-sm。 */}
      {headline.length > 0 && <p className="mt-3 text-sm text-neutral-400">{SAMPLING_RULE_LABEL}</p>}

      <div className={headline.length > 0 ? "mt-2 space-y-2" : "mt-3 space-y-2"}>
        {headline.map((sector) => (
          <SectorBlock key={sector.sector_code} sector={sector} lookbackDays={lookbackDays} />
        ))}
      </div>

      {/* §4.1e／§6.3 H-2：held 未知時把「列示順序」句帶回主視圖。F-4：字級不低於
          所說明的成分股列（text-sm）。 */}
      {heldUnknown && <p className="mt-2 text-sm text-neutral-300">{buildListingOrderSentence(lookbackDays)}</p>}

      {/* FR-4 底線 4：歷史比例三態句之一，三者必居其一。 */}
      <p className="mt-2 text-sm text-neutral-200">{narrative.main}</p>

      <details className="group mt-3">
        <summary className="cursor-pointer text-sm text-neutral-400 hover:text-neutral-300">{DETAILS_SUMMARY}</summary>
        <div className="mt-2 space-y-3 border-t border-neutral-800 pt-2 text-xs text-neutral-400">
          {/* S-1：後端已排序、已代入的常駐「詳細」句先放（ADR-0012 D-8：依碼選句
              屬前端，其餘由後端決定），再放完整排行。加權指數參考數字（風控
              ALL-1 複審裁定）緊接在 §6.2(d) TAIEX_REFERENCE 揭露句之前插入，
              整卡只出現一次，不落在任何族群區塊或主視圖。 */}
          {data.disclosures.map((sentence, index) => (
            // eslint-disable-next-line react/no-array-index-key -- 後端已排好固定順序。
            <Fragment key={index}>
              {sentence === TAIEX_REFERENCE_SENTENCE && taiexReturn !== null && (
                <p>{buildTaiexReferenceLine(taiexReturn, lookbackDays)}</p>
              )}
              <p>{sentence}</p>
            </Fragment>
          ))}

          <div>
            <p className="font-medium text-neutral-300">完整排行</p>
            {/* §14-4 required：「完整排行」小標下也放一次取樣規則標籤。 */}
            <p className="mt-1">{SAMPLING_RULE_LABEL}</p>
            {/* §14-1：等權全市場報酬，整卡一次，放在「完整排行」小標之後、族群
                清單之前。 */}
            {benchmarkReturn !== null && (
              <p className="mt-1">{buildBenchmarkReturnSentence(benchmarkReturn, lookbackDays)}</p>
            )}
            <div className="mt-1 space-y-2">
              {data.sectors.map((sector) => (
                <div key={sector.sector_code}>
                  <SectorBlock sector={sector} lookbackDays={lookbackDays} />
                  {sector.sector_return_L !== null && (
                    <p className="mt-1">{buildSectorReturnSentence(sector.sector_return_L, lookbackDays)}</p>
                  )}
                  {sector.turnover_value_ratio_5_20 !== null && (
                    <p className="mt-1">{buildTurnoverRatioLabel(sector.turnover_value_ratio_5_20)}</p>
                  )}
                  {/* §14-3：說明句只在「詳細」完整排行的族群區塊內；tag 已在
                      SectorBlock 內常駐（主視圖與詳細皆可見）。 */}
                  {sector.single_stock_dominated && sector.top_contributor_share !== null && (
                    <p className="mt-1">
                      {buildSingleStockDominatedSentence(sector.top_contributor_share, lookbackDays)}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>

          {data.excluded_sectors.length > 0 && (
            <div>
              <p className="font-medium text-neutral-300">未納入排行的族群</p>
              <ul className="mt-1 space-y-1">
                {data.excluded_sectors.map((item) => (
                  <li key={item.sector_code}>
                    {buildExclusionSentence(item, {
                      minConstituents: data.min_constituents,
                      sectorCoverageThresholdPct: thresholdPercent(data.sector_coverage_threshold),
                      lookbackDays,
                    })}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 歷史比例三態的詳細句（NE 組合／failed／passed 共用七句 + 四數）。 */}
          {narrative.detail.map((sentence, index) => (
            // eslint-disable-next-line react/no-array-index-key -- 固定順序組成。
            <p key={index}>{sentence}</p>
          ))}

          {/* §14-2：passed／failed 詳細數字列，兩組各自標題、明顯分隔（各自獨立
              的 bordered 區塊）。 */}
          {stat !== null && (data.gate_status === "failed" || data.gate_status === "passed") && (
            <div className="space-y-2">
              <div className="rounded border border-neutral-700 p-2">
                <p className="font-medium text-neutral-300">{NET_COST_GROUP_TITLE}</p>
                <p className="mt-1">{buildBeatCountSentence(stat.sample_count, stat.beat_count_net, holdingDays)}</p>
                <p className="mt-1">{buildAverageSentence(stat.base_rate_net)}</p>
                <p className="mt-1">
                  {buildWilsonIntervalSentence(
                    computeConfidenceLevelPercent(stat.m_at_evaluation),
                    stat.ci_low_net,
                    stat.ci_high_net,
                  )}
                </p>
                <p className="mt-1">
                  {buildBootstrapIntervalSentence(
                    computeConfidenceLevelPercent(stat.m_at_evaluation),
                    stat.bootstrap_low_net,
                    stat.bootstrap_high_net,
                  )}
                </p>
              </div>
              <div className="rounded border border-neutral-700 p-2">
                <p className="font-medium text-neutral-300">{GROSS_COST_GROUP_TITLE}</p>
                <p className="mt-1">{buildBeatCountSentence(stat.sample_count, stat.beat_count_gross, holdingDays)}</p>
                <p className="mt-1">{buildAverageSentence(stat.base_rate_gross)}</p>
              </div>
            </div>
          )}

          <div>
            <DataMetaStatusBadge
              status={data.data.status}
              stalenessMinutes={data.data.staleness_minutes}
              isWithinTtl={data.data.is_within_ttl}
              lastBarDate={data.data.last_bar_date}
              reason={data.data.reason}
            />
          </div>
        </div>
      </details>
    </>
  );
}

export function SectorMomentumCard() {
  const query = useSectorMomentum(true);

  if (query.isPending) {
    return (
      <div className="rounded-lg border border-neutral-800 p-4">
        <SkeletonBlock className="h-6 w-40" />
        <div className="mt-3 space-y-2">
          <SkeletonBlock className="h-20 w-full" />
          <SkeletonBlock className="h-20 w-full" />
          <SkeletonBlock className="h-20 w-full" />
        </div>
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="rounded-lg border border-neutral-800 p-4">
        <ErrorPanel label={SECTOR_CARD_TITLE} error={query.error} />
      </div>
    );
  }

  return <SectorMomentumCardView data={query.data} />;
}
