/**
 * Data-age judgement backing AC-C8.2's "resource is more than one trading day
 * old" prominent notice (`operationSummary.ts`).
 *
 * History, because the direction of the fixes matters more than the code:
 *
 * * **R4** (risk-final-review.md): the notice used to fire off `data.status
 *   === "cached_stale"`, a *source-degradation* signal, not a data-age one.
 *   `cached_stale` is still surfaced on its own by `DataMetaStatusBadge`,
 *   unrelated to this notice.
 * * **B1** (risk-fix-review.md): the R4 replacement modelled trading days in
 *   the browser by enumerating weekends plus two fixed-date holidays. 農曆年
 *   and every other movable/ad-hoc TWSE closure was counted as a session that
 *   happened, so the first trading day back from a long closure produced
 *   exactly the false "資料過舊" alarm R4 existed to remove — every year.
 * * The B1 stop-gap dropped trading-day modelling entirely and counted plain
 *   calendar days against a >10 buffer, wide enough to swallow 農曆年. Its own
 *   header said what to do instead: *"If the backend ever exposes an actual
 *   trading-calendar / previous-trading-day field on the as-of response,
 *   prefer that over this heuristic."*
 *
 * **C4 (2026-08-13) does exactly that.** The backend now publishes
 * `data.trading_days_behind` — how many sessions the market was *observed* to
 * have had since `last_bar_date`, read from the bar cache across every symbol
 * (`backend/app/services/market.py::trading_days_behind_market`). So this
 * module no longer computes anything: there is no clock reading, no timezone
 * conversion (the N1 hazard is gone with them), and no holiday table to keep
 * up to date. It only applies the threshold the risk review asked for.
 *
 * The fail-safe direction is unchanged and is enforced on the backend side: a
 * closure nobody modelled produces no bars, so no session is counted, so the
 * gap reads 0 and nothing fires. `null` means "no calendar could be consulted"
 * and must never be read as "fresh" — it, too, does not fire.
 */

/**
 * 風控複審 2026-08-09 asked for "超過一個交易日未更新"; the B1 stop-gap could
 * not honour it and substituted a 10-calendar-day buffer (QA logged the 10 as
 * an unsourced estimate). With a real calendar the threshold goes back to what
 * was asked for: one missed session is one too many.
 */
export const STALE_TRADING_DAY_THRESHOLD = 1;

/**
 * Whether the backing data is stale enough to warrant AC-C8.2's prominent
 * notice.
 *
 * `null` — the backend could not consult a trading calendar — is *not* stale:
 * an unknown gap is never presented to the reader as an old one (nor as a
 * fresh one; nothing is claimed at all).
 */
export function isDataStaleByTradingDays(tradingDaysBehind: number | null): boolean {
  if (tradingDaysBehind === null) return false;
  return tradingDaysBehind >= STALE_TRADING_DAY_THRESHOLD;
}
