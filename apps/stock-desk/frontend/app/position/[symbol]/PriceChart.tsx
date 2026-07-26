"use client";

import { useEffect, useRef } from "react";
import type { IChartApi, ISeriesApi, Time } from "lightweight-charts";
import { CandlestickSeries, LineSeries, createChart } from "lightweight-charts";
import type { Bar, IndicatorResult } from "../../lib/types";

const MA_LINE_COLORS: Record<string, string> = {
  ma_5: "#38bdf8", // sky-400
  ma_20: "#f59e0b", // amber-500
  ma_60: "#a855f7", // purple-500
};

const MA_LABELS: Record<string, string> = {
  ma_5: "MA5",
  ma_20: "MA20",
  ma_60: "MA60",
};

function toNumber(value: string): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * Daily candlestick chart with MA5/20/60 overlays, built on lightweight-charts
 * 5.2.0's `addSeries(SeriesDefinition, options)` API (verified against the
 * installed package's typings — the older `addCandlestickSeries()` helper is
 * deprecated in this version).
 *
 * `bars` come from `GET /api/bars/{symbol}` (app/api/bars.py, verified) and
 * `movingAverages` from `GET /api/signals/{symbol}`'s `technical.moving_averages`
 * (app/signals/service.py, verified); both endpoints share the same default
 * lookback (540 days) and loader, so their x-axes line up bar-for-bar. Empty
 * `bars` (the `insufficient_data` case) renders no chart — the caller decides
 * what empty-state message to show instead, so this component never draws a
 * candle from data that was not there.
 */
export function PriceChart({
  bars,
  movingAverages,
}: {
  bars: Bar[];
  movingAverages: IndicatorResult | undefined;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || bars.length === 0) return;

    const chart = createChart(container, {
      layout: {
        background: { color: "transparent" },
        textColor: "#a3a3a3",
      },
      grid: {
        vertLines: { color: "#262626" },
        horzLines: { color: "#262626" },
      },
      rightPriceScale: { borderColor: "#404040" },
      timeScale: { borderColor: "#404040" },
      autoSize: true,
    });
    chartRef.current = chart;

    const candles: ISeriesApi<"Candlestick"> = chart.addSeries(CandlestickSeries, {
      upColor: "#f43f5e",
      downColor: "#10b981",
      borderVisible: false,
      wickUpColor: "#f43f5e",
      wickDownColor: "#10b981",
    });
    candles.setData(
      bars
        .map((bar) => {
          const open = toNumber(bar.open);
          const high = toNumber(bar.high);
          const low = toNumber(bar.low);
          const close = toNumber(bar.close);
          if (open === null || high === null || low === null || close === null) return null;
          return { time: bar.date as Time, open, high, low, close };
        })
        .filter((d): d is NonNullable<typeof d> => d !== null),
    );

    const lineSeries: ISeriesApi<"Line">[] = [];
    if (movingAverages && movingAverages.status === "ok") {
      for (const key of ["ma_5", "ma_20", "ma_60"]) {
        const series = movingAverages.series[key];
        if (!series) continue;
        const line = chart.addSeries(LineSeries, {
          color: MA_LINE_COLORS[key] ?? "#e5e5e5",
          lineWidth: 1,
          title: MA_LABELS[key] ?? key,
        });
        const data = movingAverages.dates
          .map((date, i) => {
            const value = series[i];
            return value === undefined || value === null ? null : { time: date as Time, value };
          })
          .filter((d): d is { time: Time; value: number } => d !== null);
        line.setData(data);
        lineSeries.push(line);
      }
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, movingAverages]);

  if (bars.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-neutral-800 p-8 text-center text-sm text-neutral-500">
        無 K 線資料可繪製。
      </p>
    );
  }

  return (
    <div>
      <div ref={containerRef} className="h-[360px] w-full" role="img" aria-label="日K線與均線圖" />
      {(!movingAverages || movingAverages.status !== "ok") && (
        <p className="mt-2 text-xs text-amber-300">均線資料不足，未繪製 MA5/20/60 疊圖。</p>
      )}
    </div>
  );
}
