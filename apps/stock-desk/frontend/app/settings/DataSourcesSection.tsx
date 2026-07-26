/**
 * Data-source configuration, not a live status feed: no endpoint in this
 * backend reports per-provider health, so a "live" indicator here would be
 * either fabricated or a duplicate business-logic guess. The rows below are
 * the actual wiring read from `backend/app/api/deps.py` (`_default_resolver`,
 * verified source) — the real chain each market falls back through per the
 * four-layer degradation ladder (`app/data/interface.py` `DataStatus`,
 * verified). Per-symbol freshness is visible on the `/` overview's position
 * table via `DataStatusBadge`, which does reflect the real, live status.
 */
const CONFIGURED_SOURCES = [
  {
    market: "TW",
    primary: "TWSE（證交所）",
    backups: "TPEx（櫃買中心）→ FinMind → 本地快取",
  },
  {
    market: "US",
    primary: "（尚未設定）",
    backups: "目前沒有美股行情來源，美股部位一律回報資料不足。",
  },
];

export function DataSourcesSection() {
  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-semibold text-neutral-100">資料來源設定</h2>
      <p className="mt-1 text-xs text-neutral-500">
        以下為系統設定的來源鏈，非即時健康狀態；每筆持倉實際使用哪一層來源，顯示在總覽頁的資料狀態徽章上。
      </p>
      <div className="mt-3 overflow-x-auto rounded-md border border-neutral-800">
        <table className="min-w-[480px] text-left text-sm">
          <thead className="bg-neutral-900 text-neutral-400">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">
                市場
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                主要來源
              </th>
              <th scope="col" className="px-3 py-2 font-medium">
                備援鏈
              </th>
            </tr>
          </thead>
          <tbody>
            {CONFIGURED_SOURCES.map((source) => (
              <tr key={source.market} className="border-t border-neutral-800">
                <td className="px-3 py-2 font-medium text-neutral-100">{source.market}</td>
                <td className="px-3 py-2 text-neutral-300">{source.primary}</td>
                <td className="px-3 py-2 text-neutral-300">{source.backups}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
