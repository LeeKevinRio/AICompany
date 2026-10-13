import { useId, useState } from "react";
import type {
  BacktestMetricLabels,
  BacktestResponse,
  DataMeta,
  PerformanceMetrics,
  PerformanceMetricsWithPayoff,
  RoundTripDetail,
  RoundTripDetailLabels,
  RoundTripRow,
  SegmentReport,
  SegmentRoundTripDetail,
  SegmentRoundTripLabels,
} from "../lib/types";
import { formatDateTime, formatMoneyNumber, formatNumber, formatPercent, marketCurrency } from "../lib/format";
import type { Market } from "../lib/types";
import { DataMetaStatusBadge } from "../components/DataMetaStatusBadge";
import { EquityCurveChart } from "./EquityCurveChart";

interface MetricRow {
  /**
   * Stable anchor, never displayed (F11-A-50). `segmentTableRows` inserts the
   * F-11 rows after an id and React keys rows by it: a row's label is backend
   * copy that can change with the response, so it can be neither.
   */
  id: string;
  label: string;
  render: (m: PerformanceMetrics, currency: string) => string;
}

/** The cell of a round-trip-layer row on the Buy & Hold peer: not applicable, always (AC-20). */
const NOT_APPLICABLE = "—";

/** A count column: the same rendering the 觀測筆數 row has always used. */
function formatCount(value: number | null): string {
  return value === null ? "—" : value.toLocaleString("zh-Hant-TW");
}

/**
 * A count the backend must always supply as a non-negative whole number (the two exclusion
 * counts of the round-trip detail block). Unlike `formatCount` it has no dash
 * for "missing": a missing count there is a broken data contract (F11-W-25),
 * and a dash would let the page claim a disclosure it cannot make, so it throws.
 */
function formatExactCount(value: number): string {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`round_trip_detail: expected a non-negative whole-number count, got ${String(value)}`);
  }
  return value.toLocaleString("zh-Hant-TW");
}

/**
 * The table's rows, built per render because two of the labels are **backend
 * copy** (`report.metric_labels`), not literals of this file.
 *
 * 風控 2026-08-23 C8 批審 (`work/reviews/2026-08-23-C8-顯示語意-風控批審.md`),
 * 落地條件 C8-1/C8-3(a)/C8-6:
 *
 * - The win-rate row's label is `labels.win_rate`. Since the C8 fix
 *   (`app/backtest/report.py`) this row is the **round-trip** win rate, read
 *   from the same `RoundTripStats` Kelly's own round-trip win rate is read
 *   from — one statistic, so one label, and its single definition site is
 *   `app/api/kelly_wording.py`'s `KELLY_WIN_RATE_ROUND_TRIP_QUALIFIER`. The
 *   previous label described a fill-level denominator that the C8 fix removed;
 *   keeping it would have made this row a false statement, and re-typing the
 *   new one here would have put a second copy of risk-approved copy in a file
 *   that can drift from the constant without any test going red (the hole
 *   C8-3 closes). This file therefore holds **no** Traditional-Chinese label
 *   for it at all — `componentWordingScan.test.ts` no longer needs (and no
 *   longer has) a context allowlist entry for this file, and
 *   `kellyWinRateQualifierPairing.test.ts` asserts no hard-coded win-rate row
 *   label can come back.
 *
 *   狀態: the 2026-08-23 ruling is 條件 49
 *   (`work/reviews/2026-08-19-C5-Kelly-文案批審.md` 第六輪 任務 6) 的**重送**.
 *   條件 49 required two qualified labels — one per denominator — so that no
 *   screen showed a qualified number beside a bare one. The C8 backend fix left
 *   only one denominator, so the obligation is now discharged by there being a
 *   single label with a single definition site, and the old comment on these
 *   lines (which described this row as a fill-level rate with a different
 *   denominator) was retired with it. 條件 95's pairing test is rewritten to
 *   match, not deleted.
 * - The 完整回合數 row (label `labels.round_trips`) is C8-6: it states the
 *   denominator the win rate was measured over. Required because the two
 *   counts already on this table (交易次數 / 結算) run 7-15x larger than it, so
 *   a reader judging sample size from what is visible would overrate the win
 *   rate's reliability, and because it is what distinguishes "no completed
 *   round trip in this window" (`0`) from "this column has no round trips at
 *   all" (`—`, the Buy & Hold peer) when the win rate itself renders 「—」.
 * - C8-8 (顯著度地板): it is an ordinary entry of this same list, immediately
 *   below the win-rate row — same table, same `text-sm`, same `<tr>` treatment.
 *   Do not move it into a tooltip, a collapsible or the `text-xs` footnote
 *   layer, and do not drop it (L-C8-3 turns required if it is removed or
 *   demoted). Both rows are inside `SegmentTable`, which renders *below* the
 *   standing disclaimer and the 產出時間 stamp, so adding one row cannot push
 *   either of those down or demote them.
 *
 * L-C8-1(c) / L-C8-2 (F-11, F11-R-1): putting the payoff ratio on this screen
 * triggered both. The payoff ratio, the boundary-exclusion counts and the
 * definitions that go with them are therefore rendered now, but **not by this
 * function**: it stays the fifteen rows that existed before F-11, in content
 * and order (the two C8 guard suites call it directly). `segmentTableRows`
 * below builds the list the table actually renders by calling this function
 * and inserting the F-11 rows after two anchor ids.
 */
export function metricRows(labels: BacktestMetricLabels): MetricRow[] {
  return [
    { id: "period", label: "期間", render: (m) => `${m.start_date ?? "—"} ~ ${m.end_date ?? "—"}` },
    { id: "observations", label: "觀測筆數", render: (m) => m.observations.toLocaleString("zh-Hant-TW") },
    { id: "start_equity", label: "起始權益", render: (m, c) => formatMoneyNumber(m.start_equity, c, 0) },
    { id: "end_equity", label: "結束權益", render: (m, c) => formatMoneyNumber(m.end_equity, c, 0) },
    { id: "total_return", label: "總報酬率", render: (m) => formatPercent(m.total_return) },
    { id: "cagr", label: "CAGR", render: (m) => formatPercent(m.cagr) },
    { id: "annualized_volatility", label: "年化波動度", render: (m) => formatPercent(m.annualized_volatility) },
    { id: "sharpe", label: "Sharpe", render: (m) => formatNumber(m.sharpe) },
    { id: "sortino", label: "Sortino", render: (m) => formatNumber(m.sortino) },
    {
      id: "max_drawdown",
      label: "最大回撤",
      render: (m) =>
        `${formatPercent(m.max_drawdown)}${
          m.max_drawdown_peak_date ? `（${m.max_drawdown_peak_date} → ${m.max_drawdown_trough_date}）` : ""
        }`,
    },
    { id: "win_rate", label: labels.win_rate, render: (m) => formatPercent(m.win_rate) },
    { id: "round_trips", label: labels.round_trips, render: (m) => formatCount(m.num_round_trips) },
    { id: "profit_factor", label: "獲利因子", render: (m) => formatNumber(m.profit_factor) },
    { id: "num_trades", label: "交易次數", render: (m) => `${m.num_trades}（結算 ${m.num_closing_trades}）` },
    { id: "turnover", label: "週轉率", render: (m) => formatPercent(m.turnover) },
  ];
}

/** A data row of the rendered table: one of the fifteen pre-F-11 rows, or a row F-11 adds. */
export interface MetricTableRow extends Omit<MetricRow, "render"> {
  kind: "metric";
  /** `true` for the rows F-11 adds; their label cell wraps the text in a width-limited span (F11-A-59). */
  added: boolean;
  render: (m: PerformanceMetricsWithPayoff, currency: string) => string;
  /** The Buy & Hold cell when it is not the strategy cell's renderer applied to the peer's metrics. */
  renderBuyAndHold?: (m: PerformanceMetricsWithPayoff, currency: string) => string;
}

/**
 * A definition row (F11-A-53): the one row type that carries a definition
 * sentence, directly after its anchor row. One row type, one render path; the
 * sentences are backend copy, one paragraph each.
 */
export interface DefinitionTableRow {
  kind: "definition";
  id: string;
  paragraphs: readonly string[];
}

export type SegmentTableRow = MetricTableRow | DefinitionTableRow;

function insertAfter(
  rows: readonly SegmentTableRow[],
  anchorId: string,
  added: readonly SegmentTableRow[],
): SegmentTableRow[] {
  const index = rows.findIndex((row) => row.id === anchorId);
  if (index === -1) {
    throw new Error(`segmentTableRows: anchor row "${anchorId}" is not in metricRows`);
  }
  return [...rows.slice(0, index + 1), ...added, ...rows.slice(index + 1)];
}

function definitionRow(id: string, ...paragraphs: string[]): DefinitionTableRow {
  return { kind: "definition", id, paragraphs };
}

/**
 * The list `SegmentTable` renders (F11-A-33, A-50): `metricRows(labels)` with
 * the F-11 rows inserted at exactly two anchors and nowhere else (F11-W-12(b)).
 *
 * - after the profit-factor row: its definition (L-07), the payoff ratio, and
 *   the payoff ratio's definition (L-06d, with L-06p in the same cell);
 * - after the turnover row: the two mean-return rows, the longest losing streak
 *   with its definition (L-04n), the in-market share with its definition (L-08n).
 *
 * The pre-F-11 rows are the ones `metricRows` returns, untouched, in their
 * original relative order, so the round-trip count row stays directly below
 * the win-rate row. Nothing is computed here: every value is a backend field
 * run through a formatter, or a backend sentence rendered as it came.
 */
export function segmentTableRows(
  labels: BacktestMetricLabels,
  detail: SegmentRoundTripDetail,
  detailLabels: RoundTripDetailLabels,
  segmentLabels: SegmentRoundTripLabels,
): SegmentTableRow[] {
  const base: SegmentTableRow[] = metricRows(labels).map((row) => ({
    ...row,
    kind: "metric",
    added: false,
  }));
  const afterProfitFactor: SegmentTableRow[] = [
    definitionRow("profit_factor_definition", detailLabels.profit_factor_definition),
    {
      kind: "metric",
      added: true,
      id: "payoff_ratio",
      label: detailLabels.payoff_ratio,
      render: (m) => formatNumber(m.round_trip_payoff_ratio),
      renderBuyAndHold: () => NOT_APPLICABLE,
    },
    definitionRow(
      "payoff_ratio_definition",
      detailLabels.payoff_ratio_definition,
      segmentLabels.payoff_ratio_pointer,
    ),
  ];
  const afterTurnover: SegmentTableRow[] = [
    {
      kind: "metric",
      added: true,
      id: "mean_winning_return",
      label: detailLabels.mean_winning_return,
      render: () => formatPercent(detail.mean_winning_return) + segmentLabels.mean_winning_return_suffix,
      renderBuyAndHold: () => NOT_APPLICABLE,
    },
    {
      kind: "metric",
      added: true,
      id: "mean_losing_return",
      label: detailLabels.mean_losing_return,
      render: () => formatPercent(detail.mean_losing_return) + segmentLabels.mean_losing_return_suffix,
      renderBuyAndHold: () => NOT_APPLICABLE,
    },
    {
      kind: "metric",
      added: true,
      id: "longest_losing_streak",
      label: detailLabels.longest_losing_streak,
      render: () => segmentLabels.longest_losing_streak_value,
      renderBuyAndHold: () => NOT_APPLICABLE,
    },
    definitionRow("longest_losing_streak_definition", detailLabels.longest_losing_streak_definition),
    {
      kind: "metric",
      added: true,
      id: "in_market_ratio",
      label: detailLabels.in_market_ratio,
      render: () => formatPercent(detail.in_market_ratio),
      renderBuyAndHold: () => formatPercent(detail.buy_and_hold_in_market_ratio),
    },
    definitionRow("in_market_ratio_definition", segmentLabels.in_market_ratio_definition),
  ];
  return insertAfter(insertAfter(base, "profit_factor", afterProfitFactor), "turnover", afterTurnover);
}

function SegmentTable({
  title,
  segment,
  detail,
  detailLabels,
  segmentLabels,
  currency,
  labels,
}: {
  title: string;
  segment: SegmentReport;
  detail: SegmentRoundTripDetail;
  detailLabels: RoundTripDetailLabels;
  segmentLabels: SegmentRoundTripLabels;
  currency: string;
  labels: BacktestMetricLabels;
}) {
  const rows = segmentTableRows(labels, detail, detailLabels, segmentLabels);
  return (
    <div className="mt-4">
      <h3 className="text-sm font-semibold text-neutral-200">{title}</h3>
      {/* L-09: shown by the backend's flag alone; this file never compares a count with a threshold (F11-A-23). */}
      {detail.below_display_minimum && (
        <p className="mt-2 rounded-md border border-neutral-700 bg-neutral-900/60 px-4 py-2 text-sm text-neutral-300">
          {detailLabels.sample_below_minimum}
        </p>
      )}
      {/* L-10: standing on every segment, whatever its count. */}
      <p className="mt-2 text-sm text-neutral-300">{detailLabels.sample_count_reminder}</p>
      <div className="mt-2 overflow-x-auto @container rounded-md border border-neutral-800">
        <table className="w-full table-fixed min-w-[520px] text-left text-sm">
          <colgroup>
            <col className="w-[7rem] sm:w-[11rem]" />
            <col />
            <col />
          </colgroup>
          <thead className="bg-neutral-900 text-neutral-400">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                指標
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                策略
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                Buy &amp; Hold
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) =>
              row.kind === "definition" ? (
                <tr key={row.id} className="border-t border-neutral-800">
                  <td colSpan={3} className="p-0">
                    {/*
                      F11-A-55 / F11-W-9 (scheme C): the one place `sticky` is allowed, left-0 only.
                      The block is as wide as the scroll container's visible width, so the sentence
                      stays readable at any horizontal scroll position without covering any other row.
                    */}
                    <div className="sticky left-0 w-[100cqw] space-y-2 px-3 py-2 text-sm text-neutral-300">
                      {row.paragraphs.map((paragraph, index) => (
                        <p key={index}>{paragraph}</p>
                      ))}
                    </div>
                  </td>
                </tr>
              ) : (
                <tr key={row.id} className="border-t border-neutral-800">
                  <td className="px-3 py-2 text-neutral-500">
                    {row.added ? <span className="block max-w-[8.75rem]">{row.label}</span> : row.label}
                  </td>
                  <td className="px-3 py-2 text-neutral-100">{row.render(segment.strategy, currency)}</td>
                  <td className="px-3 py-2 text-neutral-300">
                    {(row.renderBuyAndHold ?? row.render)(segment.buy_and_hold, currency)}
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-neutral-500">
        Buy &amp; Hold 為同期間、未計交易成本的被動持有基準（見後端 `app/backtest/report.py` 文件說明）。
      </p>
    </div>
  );
}

/** The source and as-of text the report header has always shown, reused verbatim by the detail blocks. */
function SourceAndAsOf({ data }: { data: DataMeta }) {
  return (
    <>
      來源：{data.source}
      {data.last_bar_date !== null && <span>｜資料截至 {data.last_bar_date}</span>}
    </>
  );
}

/**
 * The source line with its freshness badge and standing `reason`: one
 * component for the report header and both round-trip sub-blocks, so the
 * three lines are fed the same `DataMeta` fields and cannot drift apart
 * (F11-W-34). Non-compact, body size, the reason never folded away.
 */
function SourceLine({ data, marginTop }: { data: DataMeta; marginTop: "mt-1" | "mt-2" }) {
  return (
    <p className={`${marginTop} flex flex-wrap items-center gap-2 text-sm text-neutral-400`}>
      <SourceAndAsOf data={data} />
      <DataMetaStatusBadge
        status={data.status}
        stalenessMinutes={data.staleness_minutes}
        isWithinTtl={data.is_within_ttl}
        lastBarDate={data.last_bar_date}
        reason={data.reason}
      />
    </p>
  );
}

/** One list of complete round trips: five facts per row, no colour carrying good or bad. */
function RoundTripRowsTable({
  rows,
  labels,
  currency,
}: {
  rows: readonly RoundTripRow[];
  labels: RoundTripDetailLabels;
  currency: string;
}) {
  return (
    <div className="mt-2 overflow-x-auto rounded-md border border-neutral-800">
      <table className="min-w-[520px] text-left text-sm">
        <thead className="bg-neutral-900 text-neutral-400">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              {labels.entry_date}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {labels.exit_date}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {labels.holding_bars}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {labels.return_on_entry_equity}
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              {labels.realized_pnl}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.entry_date}|${row.exit_date}`} className="border-t border-neutral-800">
              <td className="px-3 py-2 text-neutral-100">{row.entry_date}</td>
              <td className="px-3 py-2 text-neutral-100">{row.exit_date}</td>
              <td className="px-3 py-2 text-neutral-100">{row.holding_bars.toLocaleString("zh-Hant-TW")}</td>
              <td className="px-3 py-2 text-neutral-100">{formatPercent(row.return_on_entry_equity)}</td>
              <td className="px-3 py-2 text-neutral-100">{formatMoneyNumber(row.realized_pnl, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * The full round-trip list behind its control (L-16). Exported so a test can
 * render the expanded state; the shipped component below always starts
 * collapsed, for every segment and every data state (F11-R-8).
 */
export function RoundTripFullListView({
  expanded,
  onToggle,
  panelId,
  rows,
  labels,
  segmentLabels,
  currency,
}: {
  expanded: boolean;
  onToggle: () => void;
  panelId: string;
  rows: readonly RoundTripRow[];
  labels: RoundTripDetailLabels;
  segmentLabels: SegmentRoundTripLabels;
  currency: string;
}) {
  return (
    <div className="mt-4">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        aria-label={expanded ? segmentLabels.collapse_control_aria : segmentLabels.expand_control_aria}
        onClick={onToggle}
        className="min-h-11 rounded-md border border-neutral-700 bg-neutral-900 px-4 text-sm text-neutral-100 hover:bg-neutral-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400 active:bg-neutral-700"
      >
        {expanded ? segmentLabels.collapse_control : segmentLabels.expand_control}
      </button>
      <div id={panelId} hidden={!expanded}>
        <RoundTripRowsTable rows={rows} labels={labels} currency={currency} />
      </div>
    </div>
  );
}

function RoundTripFullList(props: Omit<Parameters<typeof RoundTripFullListView>[0], "expanded" | "onToggle" | "panelId">) {
  const [expanded, setExpanded] = useState(false);
  const panelId = useId();
  return (
    <RoundTripFullListView
      {...props}
      expanded={expanded}
      onToggle={() => setExpanded((current) => !current)}
      panelId={panelId}
    />
  );
}

/**
 * One segment's round-trip detail sub-block (PRD B2 item 5). Order: title
 * (L-01) -> opening sentence (L-13) -> source and as-of line -> cost sentence
 * (L-12) -> exclusion disclosure (L-11h/a/b/n) -> the lowest returns (L-03) ->
 * the full list behind its control. Everything up to and including the
 * exclusion disclosure is outside the collapsible part and outside every
 * scroll container (F11-W-8, W-26). Whether there is a list at all is the
 * backend's `empty_state` code, never a count (F11-A-23, A-54).
 */
function RoundTripDetailBlock({
  detail,
  segmentLabels,
  labels,
  data,
  currency,
}: {
  detail: SegmentRoundTripDetail;
  segmentLabels: SegmentRoundTripLabels;
  labels: RoundTripDetailLabels;
  data: DataMeta;
  currency: string;
}) {
  const emptyStateText = {
    no_position: labels.empty_state_no_position,
    excluded_only: labels.empty_state_excluded_only,
  };
  return (
    <section className="mt-6">
      <h3 className="text-sm font-semibold text-neutral-200">{segmentLabels.detail_title}</h3>
      <p className="mt-2 text-sm text-neutral-300">{labels.detail_opening}</p>
      {/* 風控 F11-W-34: the same source line, badge and standing reason as the report header. */}
      <SourceLine data={data} marginTop="mt-2" />
      <p className="mt-2 text-sm text-neutral-300">{labels.cost_and_settings_note}</p>
      <div className="mt-3">
        <h4 className="text-sm font-semibold text-neutral-200">{labels.excluded_heading}</h4>
        <dl className="mt-1 space-y-1 text-sm">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <dt className="text-neutral-300">{labels.excluded_closed_trips}</dt>
            <dd className="font-medium text-neutral-100">{formatExactCount(detail.excluded_boundary_trips)}</dd>
          </div>
          <div className="flex flex-wrap items-baseline gap-x-3">
            <dt className="text-neutral-300">{labels.excluded_open_trips}</dt>
            <dd className="font-medium text-neutral-100">{formatExactCount(detail.open_trip_at_end)}</dd>
          </div>
        </dl>
        <p className="mt-2 text-sm text-neutral-300">{labels.excluded_note}</p>
      </div>
      {detail.empty_state === null ? (
        <>
          <div className="mt-4">
            <h4 className="text-sm font-semibold text-neutral-200">{segmentLabels.lowest_returns_heading}</h4>
            <p className="mt-1 text-sm text-neutral-300">{labels.columns_note}</p>
            <RoundTripRowsTable rows={detail.lowest_return_round_trips} labels={labels} currency={currency} />
          </div>
          <RoundTripFullList
            rows={detail.round_trips}
            labels={labels}
            segmentLabels={segmentLabels}
            currency={currency}
          />
        </>
      ) : (
        <p className="mt-4 text-sm text-neutral-300">{emptyStateText[detail.empty_state]}</p>
      )}
    </section>
  );
}

export function BacktestReportView({ report }: { report: BacktestResponse }) {
  const currency = marketCurrency(report.market as Market);

  if (report.status === "insufficient_data" || report.report === null) {
    return (
      <section className="mt-6 rounded-lg border border-amber-800 bg-amber-950/30 p-5">
        <h2 className="text-lg font-semibold text-neutral-100">
          {report.symbol}（{report.market}）回測資料不足
        </h2>
        <p className="mt-2 text-sm text-amber-300">{report.reason ?? "資料不足，無法計算。"}</p>
        {/* 風控 2026-09-12 R-2: the demo warning stands on this branch too. */}
        {report.data_warning && (
          <p role="alert" className="mt-2 text-sm text-amber-300">
            {report.data_warning}
          </p>
        )}
      </section>
    );
  }

  // `round_trip_detail` is null exactly when `report` is (F11-A-16). A report
  // without it is a broken API contract, and rendering the table without the
  // payoff ratio's definitions or the exclusion disclosure would be a quiet
  // downgrade of what F11-R-1 requires to ship together: fail loudly instead.
  // `== null` also catches a response that omits the key (undefined), not just an explicit null.
  const detail: RoundTripDetail | null | undefined = report.round_trip_detail;
  if (detail == null) {
    throw new Error("BacktestReportView: a successful report arrived without round_trip_detail");
  }

  return (
    <section className="mt-6 rounded-lg border border-neutral-800 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">
          {report.symbol}（{report.market}）回測報告
        </h2>
        <span className="text-xs text-neutral-500">產出時間：{formatDateTime(report.as_of)}</span>
      </div>
      {/* 風控 2026-09-12 REQ-W10: the report names its own bars' source and freshness (S-2: body size, like the event-study section's line). */}
      <SourceLine data={report.data} marginTop="mt-1" />

      {/*
        風控 2026-09-12 複審 R-2 (required): "every number on this page is
        synthetic" outranks the fee alert, so the backend's demo sentence is a
        standing alert at the same level as `rates_verified`, placed before it,
        never a bullet inside `notes`. Wording is the backend's, verbatim.
      */}
      {report.data_warning && (
        <p
          role="alert"
          className="mt-3 rounded-md border border-amber-800 bg-amber-950/40 px-4 py-2 text-sm text-amber-300"
        >
          {report.data_warning}
        </p>
      )}

      {/*
        D2 item 4 (限制清單 #10 / 機會清單 D2): a standing disclosure, not
        behind any toggle. Wording reuses (subject swapped in, clause kept
        verbatim) the already-shipped, same-purpose sentence in
        `TechnicalIndicatorsPanel.tsx`'s max-drawdown card ("...屬歷史統計
        描述，不代表未來會重演。"), rather than drafting a new claim — listed
        in this batch's report for risk-compliance-officer to confirm the
        reuse is appropriate at report level, not just per-metric.

        D3 fix (波次1文案裁決.md「D 批」，2026-08-10 required×2): promoted from
        `text-xs` to `text-sm` in a bordered box so it is not visually lower
        priority than the `rates_verified` fee alert below — the wording
        itself was already approved, only the presentation level was vetoed.
      */}
      <p className="mt-2 rounded-md border border-neutral-700 bg-neutral-900/60 px-4 py-2 text-sm text-neutral-300">
        本回測報告呈現的所有數字皆屬歷史統計描述，不代表未來會重演。
      </p>

      {!report.rates_verified && (
        <p
          role="alert"
          className="mt-3 rounded-md border border-amber-800 bg-amber-950/40 px-4 py-2 text-sm text-amber-300"
        >
          費率未查證：本次回測使用的手續費／交易稅／滑價率尚未對照主要來源查證（verified_on 為
          null），報告數字應視為待查證狀態。
        </p>
      )}

      {/*
        D3 fix (波次1文案裁決.md「D 批」，2026-08-10 required×2): `notes`
        carries the 除權息還原揭露句 (`DIVIDEND_ADJUSTED_NOTE` /
        `DIVIDEND_NOT_SYNCED_NOTE` / etc., app/api/backtest.py) alongside the
        buy-and-hold/rates notes; promoted the whole list from a bare `text-xs`
        bullet list to the same bordered `text-sm` treatment as the disclaimer
        above, so the dividend disclosure is not visually demoted relative to
        the `rates_verified` fee alert. `last_synced_at` (backend already
        returns it on `dividend_adjustment`, previously never rendered) is
        shown right beside this box rather than folded into the bullet text,
        because it is metadata about the dividend note, not a note itself.
      */}
      {report.notes.length > 0 && (
        <div className="mt-2 rounded-md border border-neutral-700 bg-neutral-900/60 px-4 py-2 text-sm text-neutral-300">
          <ul className="list-disc space-y-1 pl-5">
            {report.notes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
          {/*
            D3 suggested (波次1文案裁決.md 複審): `last_synced_at` is null in
            exactly one case — the store has no rows at all, i.e. never synced
            (`DividendStore.last_synced_at`). Passing that null to
            `formatDateTime` printed 「時間不明」, which claims the timestamp
            is unknown when it is in fact known to not exist; say so instead.
          */}
          <p className="mt-2 text-xs text-neutral-500">
            除權息資料最近同步時間：
            {report.dividend_adjustment.last_synced_at
              ? formatDateTime(report.dividend_adjustment.last_synced_at)
              : "尚未同步過"}
          </p>
        </div>
      )}

      {/*
        CEO 2026-09-09「像曲線圖那樣的」(creative-lead 方案 A.6, amended by 風控
        REQ-1): the equity curve comes after every standing disclosure — the
        report-level disclaimer, the unverified-rates alert and the dividend /
        Buy & Hold notes — and before the cost grid and the tables. The chart is
        the report's strongest comparison claim, so the sentences that bound
        that claim (an unadjusted series understates Buy & Hold, i.e. the
        control group) must be read first. `report.curves` is null exactly when
        `report.report` is; the component renders the empty statement itself.
      */}
      <EquityCurveChart curves={report.curves} />

      <div className="mt-3 grid grid-cols-1 gap-2 text-xs text-neutral-500 sm:grid-cols-3">
        <p>台股手續費率：{formatPercent(report.cost_model.tw_broker_fee_rate)}</p>
        <p>台股股票交易稅：{formatPercent(report.cost_model.tw_tax_rate_stock)}</p>
        <p>台股 ETF 交易稅：{formatPercent(report.cost_model.tw_tax_rate_etf)}</p>
        <p>美股手續費率：{formatPercent(report.cost_model.us_broker_fee_rate)}</p>
        <p>美股賣出監管費率：{formatPercent(report.cost_model.us_sell_regulatory_fee_rate)}</p>
        <p>滑價：{report.cost_model.slippage_bps} bps</p>
      </div>

      <p className="mt-2 text-xs text-neutral-500">
        Walk-forward 折數：{report.folds.length}（樣本內取第一折的訓練窗，樣本外為所有折測試窗銜接）
      </p>

      {/* L-18a / L-18b: the run's single tail disclosure, text-sm, outside every scroll container (F11-W-14). */}
      <p className="mt-2 text-sm text-neutral-300">{detail.labels.unattributed_tail}</p>

      {/*
        C8-3(a)/C8-6: both tables take their two risk-approved row labels from
        the same response, so the two segments can never disagree with each
        other or with the backend constant they came from.
      */}
      <SegmentTable
        title="樣本內（in-sample）"
        segment={report.report.in_sample}
        detail={detail.in_sample}
        detailLabels={detail.labels}
        segmentLabels={detail.labels.in_sample}
        currency={currency}
        labels={report.metric_labels}
      />
      <SegmentTable
        title="樣本外（out-of-sample，未參與任何參數選擇）"
        segment={report.report.out_of_sample}
        detail={detail.out_of_sample}
        detailLabels={detail.labels}
        segmentLabels={detail.labels.out_of_sample}
        currency={currency}
        labels={report.metric_labels}
      />
      <RoundTripDetailBlock
        detail={detail.in_sample}
        segmentLabels={detail.labels.in_sample}
        labels={detail.labels}
        data={report.data}
        currency={currency}
      />
      <RoundTripDetailBlock
        detail={detail.out_of_sample}
        segmentLabels={detail.labels.out_of_sample}
        labels={detail.labels}
        data={report.data}
        currency={currency}
      />
    </section>
  );
}
