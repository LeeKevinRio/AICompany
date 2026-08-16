import { US_MARKET_OPTION_CAVEAT } from "../lib/format";

/**
 * Data-source configuration, not a live status feed: no endpoint in this
 * backend reports per-provider health, so a "live" indicator here would be
 * either fabricated or a duplicate business-logic guess. The rows below are
 * the actual wiring read from `backend/app/api/deps.py` (`_default_resolver`,
 * verified source) — the real chain each market falls back through per the
 * four-layer degradation ladder (`app/data/interface.py` `DataStatus`,
 * verified). Per-symbol freshness is visible on the `/` overview's position
 * table via `DataStatusBadge`, which does reflect the real, live status.
 *
 * D5④ (2026-08-13 衝刺覆核列管,**字面待風控覆核**): the TW backups cell used
 * to stop at 「本地快取」, hiding the ladder's real terminal state — the TW
 * chain too ends at "any usable cached rows regardless of TTL, else
 * unavailable" (`app/data/service.py` steps 3–4, identical to US). The cell
 * now names both final layers with the exact wording the risk-approved US
 * row already uses (「任何可用快取 → 資料不足」), so the two rows describe
 * the shared ladder in one format. TW keeps no layer-0 entry because
 * `cache_first` is off for TW by ADR-0005 (deps.py, verified).
 *
 * D5⑤ (2026-08-13 衝刺覆核列管,**字面待風控覆核**): the US primary cell's
 * parenthetical used to carry only the affirmative half of the D4 disclosure
 * (「已完成接線，並以測試替身通過自動化測試」) while the S7 market-option
 * caveat next to the very same word 「美股（US）」 elsewhere carries the
 * cautionary half — an asymmetric tone for the same fact. The cell now
 * reuses the S7-approved caveat verbatim (`format.ts`
 * `US_MARKET_OPTION_CAVEAT`,「資料來源未經真實環境驗證」); the affirmative
 * facts are not lost — they remain, verbatim and risk-approved, in the D4
 * disclosure paragraph rendered directly below this table
 * (`US_DATA_SOURCE_DISCLOSURE_STATEMENT`, untouched).
 *
 * Exported so `__tests__/componentWordingScan.test.ts` can pin both rows
 * verbatim for the risk re-review, the same way it pins the D4 statement.
 */
export const CONFIGURED_SOURCES = [
  {
    market: "TW",
    primary: "TWSE（證交所）",
    backups: "TPEx（櫃買中心）→ FinMind → 任何可用快取 → 資料不足",
  },
  {
    market: "US",
    primary: `Alpha Vantage${US_MARKET_OPTION_CAVEAT}`,
    backups:
      "TTL 內本地快取（優先於主要來源）→ Alpha Vantage → yfinance → 任何可用快取 → 資料不足",
  },
];

/**
 * D4 定稿 (`work/stock-desk-D4-資料來源措辭.md`「一之 2」，含 R-D4-1 補寫，
 * risk-compliance-officer APPROVE)：美股（US）揭露句，逐字保留，禁止改寫。
 *
 * 拆成三段 + 兩個環境變數名常數，是為了讓 JSX 能把
 * `ALPHA_VANTAGE_API_KEY` / `ALPHA_VANTAGE_DAILY_LIMIT` 包進 `<code>`
 * 標記（呈現規格「一之 3」要求），同時保留單一組字面來源：
 * `US_DATA_SOURCE_DISCLOSURE_STATEMENT` 由這五個片段串接而成，不是另外
 * 手動輸入的第二份文字，所以 JSX 呈現與掃描用的常數不會彼此漂移。
 *
 * `US_DATA_SOURCE_DISCLOSURE_STATEMENT` 供
 * `__tests__/componentWordingScan.test.ts` 納入措辭掃描（比照
 * `adviceWording.ts` 的 `AS_OF_DATE_UNKNOWN_STATEMENT` 進掃描面的作法）。
 */
export const US_DATA_SOURCE_DISCLOSURE_PART_1 =
  "美股（US）已完成接線，並以測試替身通過自動化測試；尚未以真實 API key 對外部服務實際發送過請求。需設定環境變數 ";
export const ALPHA_VANTAGE_API_KEY_ENV_VAR = "ALPHA_VANTAGE_API_KEY";
export const US_DATA_SOURCE_DISCLOSURE_PART_2 = "；未設定時此層直接跳過，不嘗試發送請求。另需設定環境變數 ";
export const ALPHA_VANTAGE_DAILY_LIMIT_ENV_VAR = "ALPHA_VANTAGE_DAILY_LIMIT";
export const US_DATA_SOURCE_DISCLOSURE_PART_3 =
  "（每日額度上限）；此設定未完成時，主要來源同樣直接跳過，不會發出任何請求。實際覆蓋率、速率限制與資料品質目前未知，應視為待查證狀態。";

export const US_DATA_SOURCE_DISCLOSURE_STATEMENT =
  `${US_DATA_SOURCE_DISCLOSURE_PART_1}${ALPHA_VANTAGE_API_KEY_ENV_VAR}${US_DATA_SOURCE_DISCLOSURE_PART_2}` +
  `${ALPHA_VANTAGE_DAILY_LIMIT_ENV_VAR}${US_DATA_SOURCE_DISCLOSURE_PART_3}`;

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
      {/*
        D4 揭露句(含 R-D4-1)：與 US 列同一個 <section> 內常駐渲染，不摺疊、
        不需互動；字級 text-sm（不低於表格內文）、色階 text-neutral-300
        （高於下限 text-neutral-400），不沿用第 28 行頁首說明的
        text-xs text-neutral-500。
      */}
      <p className="mt-2 text-sm text-neutral-300">
        {US_DATA_SOURCE_DISCLOSURE_PART_1}
        <code>{ALPHA_VANTAGE_API_KEY_ENV_VAR}</code>
        {US_DATA_SOURCE_DISCLOSURE_PART_2}
        <code>{ALPHA_VANTAGE_DAILY_LIMIT_ENV_VAR}</code>
        {US_DATA_SOURCE_DISCLOSURE_PART_3}
      </p>
    </section>
  );
}
