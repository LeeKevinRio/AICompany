"use client";

import { useEffect, useRef, useState } from "react";
import { SkeletonBlock } from "../../components/SkeletonBlock";
import { toScriptSafeJson } from "../../lib/scriptSafeJson";
import { toTradingViewSymbol } from "../../lib/tradingViewSymbol";
import type { Market } from "../../lib/types";

/**
 * Official TradingView "Advanced Chart Widget" embed
 * (https://www.tradingview.com/widget/advanced-chart/) — the standard
 * `s3.tradingview.com` embed script, loaded client-side only. Only the
 * config keys documented by that widget generator are set below (no
 * trading/order params — CEO 派工單 2026-08-16 第 5 點); nothing here talks to
 * any internal/undocumented TradingView API.
 */
const EMBED_SCRIPT_SRC = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";

/**
 * How long to wait for the widget's own iframe to appear before treating the
 * embed as failed. Generous on purpose: this is a third-party network load,
 * not a call into this system's own verified data chain, so a slow-but-
 * eventually-successful load should not be flagged as an error prematurely.
 */
const WIDGET_MOUNT_TIMEOUT_MS = 12_000;

/**
 * 揭露句 — **risk-compliance-officer 逐字定稿（2026-08-16，二輪 CONFIRMED）**。
 * 歷程：初稿（frontend-engineer 自擬）遭 VETO（R1-R4）→ creative-lead 改寫 →
 * 逐字核可（work/stock-desk-D4-資料來源措辭.md 第七節）。字面（含標點）不得再
 * 改動，任何變更視為漂移須重送風控；`componentWordingScan.test.ts` 逐字釘住。
 * 落地條件（風控 required）：字級 ≥ text-sm、對比 ≥ text-neutral-400、常駐不
 * 摺疊——以 text-xs/text-neutral-500 承載視同未通過。
 */
export const TRADINGVIEW_CHART_DISCLOSURE_STATEMENT =
  "此互動圖表由 TradingView 提供；其資料來源與本系統自有的行情資料鏈是各自獨立的兩條路徑，" +
  "本系統未查證此圖表資料的正確性、完整性或時效性，亦不為其負責；" +
  "本系統無法標示其資料時間與延遲狀態；" +
  "圖表內容僅供檢視、不參與本系統任何計算或建議產出，載入需要網路連線。";

/**
 * Fallback shown when the embed script fails to load or its iframe does not
 * appear within `WIDGET_MOUNT_TIMEOUT_MS` — states the honest, plausible
 * causes (network / browser extension / third-party service) instead of
 * leaving a blank pane. **risk-compliance-officer 逐字定稿（2026-08-16，
 * 三輪：尾句「該頁籤會標示…」依風控預核之刪除案移除後單句 CONFIRMED，
 * work/stock-desk-D4-資料來源措辭.md 七之二）**。字面不得再動，漂移須重送。
 */
export const TRADINGVIEW_CHART_FALLBACK_MESSAGE =
  "互動圖表目前未能載入，可能原因是網路連線不穩、瀏覽器擴充套件（例如廣告攔截）攔截了外部資源，" +
  "或 TradingView 服務本身暫時無法連線；可重新整理頁面再試一次，或可改用「本地圖表」頁籤。";

/**
 * Security fix (qa-reviewer NEEDS_CHANGES on 4938eb5): shown in place of the
 * embed whenever `toTradingViewSymbol` rejects the resolved symbol (see its
 * doc comment) — a neutral state, never the rejected value itself, and never
 * a silent fallback to some other renderable symbol. Independent of, and
 * worded distinctly from, the two 待風控覆核 sentences above (not part of
 * this fix).
 */
export const TRADINGVIEW_CHART_INVALID_SYMBOL_MESSAGE =
  "此標的代號格式無法辨識，互動圖表未載入；請確認網址中的代號是否正確。";

type WidgetStatus = "loading" | "ready" | "error";

/**
 * TradingView Advanced Chart embed for a position's symbol. Client-only
 * (script tag injects a third-party iframe): dark theme, `zh_TW` locale, no
 * trading/order params, `allow_symbol_change: false` so this reader always
 * stays on the symbol this page is about.
 *
 * Data-honesty note: this widget's price/volume feed is TradingView's own,
 * entirely separate from the verified `GET /api/bars` chain the 本地圖表 tab
 * (`PriceChart.tsx`) renders — see `TRADINGVIEW_CHART_DISCLOSURE_STATEMENT`.
 * Nothing rendered here is read by this component's caller or fed into any
 * calculation.
 */
export function TradingViewChartPanel({ symbol, market }: { symbol: string; market: Market }) {
  const widgetHostRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<WidgetStatus>("loading");
  // Shared between the mount-detection effect below and `handleScriptLoadError`
  // (a plain event handler, not itself inside the effect) so an early script
  // load failure and the effect's own timeout/observer never both fire.
  const settledRef = useRef(false);
  const tvSymbol = toTradingViewSymbol(symbol, market);

  useEffect(() => {
    const host = widgetHostRef.current;
    // Security fix (qa-reviewer NEEDS_CHANGES on 4938eb5): `tvSymbol` is
    // `null` whenever `toTradingViewSymbol` rejected the resolved symbol —
    // nothing is mounted into `host` in that case (see the early return in
    // the render below), so there is nothing here to observe either.
    if (!host || tvSymbol === null) return;
    setStatus("loading");
    settledRef.current = false;

    // The embed script mounts its iframe asynchronously into this host with
    // no completion callback of its own — observing for that iframe's
    // arrival (or its absence past the timeout below) is the only honest
    // signal available without touching any TradingView-internal API.
    const observer = new MutationObserver(() => {
      if (!settledRef.current && host.querySelector("iframe")) {
        settledRef.current = true;
        setStatus("ready");
        observer.disconnect();
      }
    });
    observer.observe(host, { childList: true, subtree: true });

    const timeoutId = window.setTimeout(() => {
      if (!settledRef.current) {
        settledRef.current = true;
        observer.disconnect();
        setStatus("error");
      }
    }, WIDGET_MOUNT_TIMEOUT_MS);

    return () => {
      window.clearTimeout(timeoutId);
      observer.disconnect();
    };
  }, [tvSymbol]);

  // Low finding (qa-reviewer on 4938eb5): fires immediately if the embed
  // `<script>` tag itself fails to load (network error, ad blocker returning
  // a blocked response, …) instead of waiting out the full
  // `WIDGET_MOUNT_TIMEOUT_MS` for a load that already failed.
  const handleScriptLoadError = () => {
    if (settledRef.current) return;
    settledRef.current = true;
    setStatus("error");
  };

  // Security fix (qa-reviewer NEEDS_CHANGES on 4938eb5): a rejected symbol
  // never reaches the widget config / dangerous sink below — this is the
  // caller-side half of the whitelist defense in `toTradingViewSymbol`, a
  // neutral state rendered instead of the invalid value itself.
  if (tvSymbol === null) {
    return (
      <div>
        <p className="mb-2 text-sm text-neutral-300">{TRADINGVIEW_CHART_DISCLOSURE_STATEMENT}</p>
        <p
          role="alert"
          className="rounded-md border border-dashed border-amber-700 bg-amber-950/20 p-3 text-sm text-amber-300"
        >
          {TRADINGVIEW_CHART_INVALID_SYMBOL_MESSAGE}
        </p>
      </div>
    );
  }

  const config = {
    autosize: true,
    symbol: tvSymbol,
    interval: "D",
    timezone: "Asia/Taipei",
    theme: "dark",
    style: "1",
    locale: "zh_TW",
    allow_symbol_change: false,
    calendar: false,
    support_host: "https://www.tradingview.com",
  };

  return (
    <div>
      <p className="mb-2 text-sm text-neutral-300">{TRADINGVIEW_CHART_DISCLOSURE_STATEMENT}</p>
      {status === "error" && (
        <p
          role="alert"
          className="mb-2 rounded-md border border-dashed border-amber-700 bg-amber-950/20 p-3 text-sm text-amber-300"
        >
          {TRADINGVIEW_CHART_FALLBACK_MESSAGE}
        </p>
      )}
      <div className="relative h-[480px] w-full">
        {status === "loading" && <SkeletonBlock className="absolute inset-0" />}
        {/*
          Structure below mirrors TradingView's own widget-generator output
          verbatim (container / __widget mount point / required copyright
          link / config script, all siblings under one container div) — the
          embed script locates its mount point relative to its own parent, so
          this shape is not cosmetic.
        */}
        <div
          ref={widgetHostRef}
          aria-label="TradingView 互動圖表"
          className="tradingview-widget-container h-full w-full"
        >
          <div className="tradingview-widget-container__widget h-full w-full" />
          {/*
            Required attribution link per TradingView's embed licence terms —
            part of the official embed snippet; must not be removed or
            reworded (CEO 派工單 2026-08-16 第 2 點).
          */}
          <div className="tradingview-widget-copyright mt-1 text-xs text-neutral-600">
            <a href="https://www.tradingview.com/" rel="noopener nofollow" target="_blank">
              <span className="text-sky-500">Track all markets on TradingView</span>
            </a>
          </div>
          {/*
            Remount on symbol change now happens one level up, in `page.tsx`,
            via `key={`${market}:${symbol}`}` on this whole component — the
            entire host (this container + the copyright link, not just this
            `<script>`) is torn down and rebuilt, closing the stale-iframe
            overlap gap an inner-only `key={tvSymbol}` on just the script tag
            left open (qa-reviewer on 4938eb5, Medium finding).

            Security fix (qa-reviewer NEEDS_CHANGES on 4938eb5, critical
            reflected XSS, second of two independent layers — the first is
            the whitelist in `toTradingViewSymbol`): `toScriptSafeJson`
            escapes `<`/`>`/`&` to their `\uXXXX` form so nothing here can
            close this `<script>` tag early, even if the whitelist upstream
            were ever bypassed. See `scriptSafeJson.ts`.
          */}
          <script
            type="text/javascript"
            src={EMBED_SCRIPT_SRC}
            async
            onError={handleScriptLoadError}
            dangerouslySetInnerHTML={{ __html: toScriptSafeJson(config) }}
          />
        </div>
      </div>
    </div>
  );
}
