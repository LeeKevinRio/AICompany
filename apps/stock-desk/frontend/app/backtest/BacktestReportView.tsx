import type { BacktestResponse, PerformanceMetrics, SegmentReport } from "../lib/types";
import { formatDateTime, formatMoneyNumber, formatNumber, formatPercent, marketCurrency } from "../lib/format";
import type { Market } from "../lib/types";

interface MetricRow {
  label: string;
  render: (m: PerformanceMetrics, currency: string) => string;
}

const METRIC_ROWS: MetricRow[] = [
  { label: "期間", render: (m) => `${m.start_date ?? "—"} ~ ${m.end_date ?? "—"}` },
  { label: "觀測筆數", render: (m) => m.observations.toLocaleString("zh-Hant-TW") },
  { label: "起始權益", render: (m, c) => formatMoneyNumber(m.start_equity, c, 0) },
  { label: "結束權益", render: (m, c) => formatMoneyNumber(m.end_equity, c, 0) },
  { label: "總報酬率", render: (m) => formatPercent(m.total_return) },
  { label: "CAGR", render: (m) => formatPercent(m.cagr) },
  { label: "年化波動度", render: (m) => formatPercent(m.annualized_volatility) },
  { label: "Sharpe", render: (m) => formatNumber(m.sharpe) },
  { label: "Sortino", render: (m) => formatNumber(m.sortino) },
  {
    label: "最大回撤",
    render: (m) =>
      `${formatPercent(m.max_drawdown)}${
        m.max_drawdown_peak_date ? `（${m.max_drawdown_peak_date} → ${m.max_drawdown_trough_date}）` : ""
      }`,
  },
  { label: "勝率", render: (m) => formatPercent(m.win_rate) },
  { label: "獲利因子", render: (m) => formatNumber(m.profit_factor) },
  { label: "交易次數", render: (m) => `${m.num_trades}（結算 ${m.num_closing_trades}）` },
  { label: "週轉率", render: (m) => formatPercent(m.turnover) },
];

function SegmentTable({
  title,
  segment,
  currency,
}: {
  title: string;
  segment: SegmentReport;
  currency: string;
}) {
  return (
    <div className="mt-4">
      <h3 className="text-sm font-semibold text-neutral-200">{title}</h3>
      <div className="mt-2 overflow-x-auto rounded-md border border-neutral-800">
        <table className="min-w-[520px] text-left text-sm">
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
            {METRIC_ROWS.map((row) => (
              <tr key={row.label} className="border-t border-neutral-800">
                <td className="px-3 py-2 text-neutral-500">{row.label}</td>
                <td className="px-3 py-2 text-neutral-100">{row.render(segment.strategy, currency)}</td>
                <td className="px-3 py-2 text-neutral-300">
                  {row.render(segment.buy_and_hold, currency)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-xs text-neutral-500">
        Buy &amp; Hold 為同期間、未計交易成本的被動持有基準（見後端 `app/backtest/report.py` 文件說明）。
      </p>
    </div>
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
      </section>
    );
  }

  return (
    <section className="mt-6 rounded-lg border border-neutral-800 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-neutral-100">
          {report.symbol}（{report.market}）回測報告
        </h2>
        <span className="text-xs text-neutral-500">產出時間：{formatDateTime(report.as_of)}</span>
      </div>

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
            `formatDateTime` printed 「資料時間不明」, which claims the timestamp
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

      <SegmentTable title="樣本內（in-sample）" segment={report.report.in_sample} currency={currency} />
      <SegmentTable
        title="樣本外（out-of-sample，未參與任何參數選擇）"
        segment={report.report.out_of_sample}
        currency={currency}
      />
    </section>
  );
}
