"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ISeriesApi, MouseEventParams, Time } from "lightweight-charts";
import { BaselineSeries, LineSeries, LineStyle, createChart } from "lightweight-charts";
import {
  buildEquityCurveSeries,
  isEquityCurveEmpty,
  type IndexedPoint,
  type SegmentIndexedSeries,
} from "../lib/backtestCurves";
import {
  DRAWDOWN_CHART_NOTE,
  DRAWDOWN_CHART_TITLE,
  EQUITY_CURVE_ARIA_LABEL,
  EQUITY_CURVE_ARIA_LABEL_SINGLE_SEGMENT,
  EQUITY_CURVE_AXIS_NOTE,
  EQUITY_CURVE_EMPTY_STATEMENT,
  EQUITY_CURVE_GUIDANCE,
  EQUITY_CURVE_LEGEND_BUY_AND_HOLD,
  EQUITY_CURVE_LEGEND_STRATEGY,
  EQUITY_CURVE_SEGMENT_IN_SAMPLE,
  EQUITY_CURVE_SEGMENT_OUT_OF_SAMPLE,
  EQUITY_CURVE_SPLIT_NOTE,
  EQUITY_CURVE_TITLE,
  EQUITY_CURVE_TOOLTIP_BUY_AND_HOLD,
  EQUITY_CURVE_TOOLTIP_DATE,
  EQUITY_CURVE_TOOLTIP_DRAWDOWN,
  EQUITY_CURVE_TOOLTIP_STRATEGY,
  buildSegmentInsufficientNote,
  buildSingleSegmentNote,
  buildTradeCountNote,
} from "../lib/backtestCurveWording";
import type { WalkForwardCurves } from "../lib/types";

/**
 * Strategy vs Buy & Hold equity curve with the strategy's drawdown underneath
 * (CEO 2026-09-09「像曲線圖那樣的」; creative-lead 方案 A.1-A.9; 風控 REQ-1～5).
 *
 * Encoding (dataviz skill, S1 色彩不承載價值判斷):
 * - Two categorical hues validated with `validate_palette.js` on the app's
 *   `#0a0a0a` surface (sky/grey failed the normal-vision floor): strategy
 *   slot 1 blue `#3987e5` solid, Buy & Hold slot 4 yellow `#c98500` dashed.
 *   Line style + legend + axis end-label are the non-colour channels. The
 *   yellow is a category colour only and must never be re-used for a
 *   judgement, warning or advice (風控 REQ-9).
 * - Drawdown reuses the strategy hue (same entity) as a 10% wash under a 2px
 *   line, in its own pane on a shared time axis. Buy & Hold is not drawn there.
 * - Each segment is its own pair of series (same colours) so the per-segment
 *   re-base to 100 (`backtestCurves.ts`) never draws a vertical connector.
 *   A segment is drawn only when both of its series are `drawable` (REQ-2);
 *   an undrawn segment is named on screen, never silently dropped (REQ-8).
 * - The in/out-of-sample split is a hairline overlay with a text label on each
 *   side. Pan/zoom are disabled and the overlay is clipped, so the split can
 *   never leave the frame while the note describing it stays (REQ-3); the
 *   note, labels and wash all hang off the same "line is visible" state.
 * - Hover: crosshair + an HTML tooltip; the tables below are the table view.
 * - Text wears text tokens only; the swatch beside it carries the identity.
 */

const STRATEGY_COLOR = "#3987e5";
const BUY_AND_HOLD_COLOR = "#c98500";
const DRAWDOWN_FILL = "rgba(57, 135, 229, 0.10)";
const GRID_COLOR = "#262626";
const AXIS_COLOR = "#404040";
const DRAWDOWN_PANE_HEIGHT = 88;

function fmtIndex(v: number | undefined): string {
  return v === undefined ? "—" : v.toLocaleString("zh-Hant-TW", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function fmtPct(v: number | undefined): string {
  return v === undefined ? "—" : `${v.toLocaleString("zh-Hant-TW", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

function toLine(points: IndexedPoint[]): { time: Time; value: number }[] {
  return points.map((p) => ({ time: p.time as Time, value: p.value }));
}

interface Hover {
  date: string;
  strategy: number | undefined;
  buyAndHold: number | undefined;
  drawdown: number | undefined;
  x: number;
  y: number;
}

/** The sentence(s) explaining any segment that is not on the chart (REQ-2 / REQ-8). */
function segmentNotes(inSample: SegmentIndexedSeries, outOfSample: SegmentIndexedSeries): string[] {
  const pairs = [
    [EQUITY_CURVE_SEGMENT_IN_SAMPLE, inSample, EQUITY_CURVE_SEGMENT_OUT_OF_SAMPLE],
    [EQUITY_CURVE_SEGMENT_OUT_OF_SAMPLE, outOfSample, EQUITY_CURVE_SEGMENT_IN_SAMPLE],
  ] as const;
  const notes: string[] = [];
  for (const [label, seg, otherLabel] of pairs) {
    if (seg.drawable) continue;
    // "Not in this run" (no bars at all) and "too few bars" are different facts and get different sentences.
    notes.push(seg.absent ? buildSingleSegmentNote(otherLabel) : buildSegmentInsufficientNote(label));
  }
  return notes;
}

export function EquityCurveChart({ curves }: { curves: WalkForwardCurves | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<Hover | null>(null);
  const [splitX, setSplitX] = useState<number | null>(null);

  const series = useMemo(() => (curves ? buildEquityCurveSeries(curves) : null), [curves]);
  const empty = series === null || isEquityCurveEmpty(series);
  const bothDrawn = series !== null && series.inSample.drawable && series.outOfSample.drawable;

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !series || empty) return;

    const chart = createChart(container, {
      layout: {
        background: { color: "transparent" },
        textColor: "#a3a3a3",
        panes: { separatorColor: GRID_COLOR, separatorHoverColor: GRID_COLOR, enableResize: false },
      },
      grid: { vertLines: { color: GRID_COLOR }, horzLines: { color: GRID_COLOR } },
      rightPriceScale: { borderColor: AXIS_COLOR },
      timeScale: { borderColor: AXIS_COLOR },
      crosshair: { horzLine: { visible: false } },
      localization: { locale: "zh-TW" },
      // REQ-3: the whole run stays in frame; the split line can never be panned or zoomed away.
      handleScroll: false,
      handleScale: false,
      autoSize: true,
    });

    const lineOpts = (color: string, dashed: boolean, title: string | null) => ({
      color,
      lineWidth: 2 as const,
      lineStyle: dashed ? LineStyle.Dashed : LineStyle.Solid,
      title: title ?? "",
      lastValueVisible: title !== null,
      priceLineVisible: false,
      crosshairMarkerRadius: 4,
    });
    const ddOpts = {
      baseValue: { type: "price" as const, price: 0 },
      topLineColor: STRATEGY_COLOR,
      topFillColor1: "transparent",
      topFillColor2: "transparent",
      bottomLineColor: STRATEGY_COLOR,
      bottomFillColor1: DRAWDOWN_FILL,
      bottomFillColor2: DRAWDOWN_FILL,
      lineWidth: 2 as const,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerRadius: 4,
    };

    const drawn = [series.inSample, series.outOfSample].filter((seg) => seg.drawable);
    const lines: { strategy: ISeriesApi<"Line">; buyAndHold: ISeriesApi<"Line">; drawdown: ISeriesApi<"Baseline"> }[] = [];
    drawn.forEach((seg, i) => {
      // Only the last drawn segment carries the axis end-label, so each name shows once.
      const last = i === drawn.length - 1;
      const strategy = chart.addSeries(LineSeries, lineOpts(STRATEGY_COLOR, false, last ? EQUITY_CURVE_LEGEND_STRATEGY : null), 0);
      const buyAndHold = chart.addSeries(
        LineSeries,
        lineOpts(BUY_AND_HOLD_COLOR, true, last ? EQUITY_CURVE_LEGEND_BUY_AND_HOLD : null),
        0,
      );
      const drawdown = chart.addSeries(BaselineSeries, ddOpts, 1);
      strategy.setData(toLine(seg.strategy));
      buyAndHold.setData(toLine(seg.buyAndHold));
      drawdown.setData(toLine(seg.drawdown));
      lines.push({ strategy, buyAndHold, drawdown });
    });
    chart.panes()[1]?.setHeight(DRAWDOWN_PANE_HEIGHT);
    chart.timeScale().fitContent();

    const splitDate = series.inSample.drawable && series.outOfSample.drawable ? series.splitDate : null;
    const placeSplit = () => {
      if (!splitDate) {
        setSplitX(null);
        return;
      }
      const x = chart.timeScale().timeToCoordinate(splitDate as Time);
      // Clamp inside the plot so the labels can never land on neighbouring content.
      setSplitX(x === null ? null : Math.min(Math.max(Number(x), 0), container.clientWidth));
    };
    placeSplit();
    chart.timeScale().subscribeVisibleLogicalRangeChange(placeSplit);
    const resize = new ResizeObserver(placeSplit);
    resize.observe(container);

    const onMove = (param: MouseEventParams<Time>) => {
      if (!param.time || !param.point) {
        setHover(null);
        return;
      }
      const read = (s: ISeriesApi<"Line"> | ISeriesApi<"Baseline">): number | undefined =>
        (param.seriesData.get(s) as { value?: number } | undefined)?.value;
      const pick = (key: "strategy" | "buyAndHold" | "drawdown") =>
        lines.map((l) => read(l[key])).find((v) => v !== undefined);
      setHover({
        date: String(param.time),
        strategy: pick("strategy"),
        buyAndHold: pick("buyAndHold"),
        drawdown: pick("drawdown"),
        x: param.point.x,
        y: param.point.y,
      });
    };
    chart.subscribeCrosshairMove(onMove);

    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(placeSplit);
      resize.disconnect();
      chart.remove();
      setHover(null);
      setSplitX(null);
    };
  }, [series, empty]);

  if (!series || empty) {
    return (
      <p className="mt-4 rounded-md border border-dashed border-neutral-800 p-6 text-center text-sm text-neutral-400">
        {EQUITY_CURVE_EMPTY_STATEMENT}
      </p>
    );
  }

  const notes = segmentNotes(series.inSample, series.outOfSample);
  const splitShown = bothDrawn && splitX !== null;
  const tooltipLeft = hover ? Math.min(hover.x + 12, Math.max(0, (containerRef.current?.clientWidth ?? 320) - 224)) : 0;
  const tooltipTop = hover ? Math.max(0, hover.y - 8) : 0;

  return (
    <div className="mt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-sm font-semibold text-neutral-200">{EQUITY_CURVE_TITLE}</h3>
        <p className="text-xs text-neutral-400">{EQUITY_CURVE_AXIS_NOTE}</p>
      </div>

      {/* Legend: always present for two series (dataviz rule); swatch carries identity, text stays a text token. */}
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-neutral-300" aria-label="圖例">
        <li className="flex items-center gap-2">
          <svg aria-hidden="true" width="28" height="8" viewBox="0 0 28 8">
            <line x1="0" y1="4" x2="28" y2="4" stroke={STRATEGY_COLOR} strokeWidth="2" strokeLinecap="round" />
          </svg>
          {EQUITY_CURVE_LEGEND_STRATEGY}
        </li>
        <li className="flex items-center gap-2">
          <svg aria-hidden="true" width="28" height="8" viewBox="0 0 28 8">
            <line
              x1="0"
              y1="4"
              x2="28"
              y2="4"
              stroke={BUY_AND_HOLD_COLOR}
              strokeWidth="2"
              strokeLinecap="round"
              strokeDasharray="5 4"
            />
          </svg>
          {EQUITY_CURVE_LEGEND_BUY_AND_HOLD}
        </li>
      </ul>

      {/* REQ-2 / REQ-8: any segment not on the chart is named here, above the plot, before the reader looks at it. */}
      {notes.map((note) => (
        <p key={note} className="mt-2 text-sm text-neutral-300">
          {note}
        </p>
      ))}

      <div className="relative mt-2 overflow-hidden">
        <div
          ref={containerRef}
          className="h-[340px] w-full sm:h-[420px]"
          role="img"
          aria-label={splitShown ? EQUITY_CURVE_ARIA_LABEL : EQUITY_CURVE_ARIA_LABEL_SINGLE_SEGMENT}
        />

        {/* Split overlay: hairline + segment labels; out-of-sample side gets a faint neutral wash. Pointer-events off so the crosshair still works. */}
        {splitShown && (
          <div className="pointer-events-none absolute inset-y-0 left-0 right-0" aria-hidden="true">
            <div className="absolute inset-y-0 bg-neutral-100/5" style={{ left: splitX, right: 0 }} />
            <div className="absolute inset-y-0 w-px bg-neutral-500" style={{ left: splitX }} />
            <span
              className="absolute top-1 rounded bg-neutral-950/80 px-1.5 py-0.5 text-xs text-neutral-300"
              style={{ right: `calc(100% - ${splitX}px + 6px)` }}
            >
              {EQUITY_CURVE_SEGMENT_IN_SAMPLE}
            </span>
            <span
              className="absolute top-1 rounded bg-neutral-950/80 px-1.5 py-0.5 text-xs text-neutral-300"
              style={{ left: splitX + 6 }}
            >
              {EQUITY_CURVE_SEGMENT_OUT_OF_SAMPLE}
            </span>
          </div>
        )}

        {hover && (
          <div
            className="pointer-events-none absolute z-10 w-[214px] rounded-md border border-neutral-700 bg-neutral-950/95 px-3 py-2 text-xs text-neutral-300 shadow"
            style={{ left: tooltipLeft, top: tooltipTop }}
          >
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
              <dt className="whitespace-nowrap text-neutral-500">{EQUITY_CURVE_TOOLTIP_DATE}</dt>
              <dd className="whitespace-nowrap text-right font-mono tabular-nums">{hover.date}</dd>
              <dt className="whitespace-nowrap text-neutral-500">{EQUITY_CURVE_TOOLTIP_STRATEGY}</dt>
              <dd className="whitespace-nowrap text-right font-mono tabular-nums">{fmtIndex(hover.strategy)}</dd>
              <dt className="whitespace-nowrap text-neutral-500">{EQUITY_CURVE_TOOLTIP_BUY_AND_HOLD}</dt>
              <dd className="whitespace-nowrap text-right font-mono tabular-nums">{fmtIndex(hover.buyAndHold)}</dd>
              <dt className="whitespace-nowrap text-neutral-500">{EQUITY_CURVE_TOOLTIP_DRAWDOWN}</dt>
              <dd className="whitespace-nowrap text-right font-mono tabular-nums">{fmtPct(hover.drawdown)}</dd>
            </dl>
          </div>
        )}
      </div>

      <div className="mt-1 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs text-neutral-400">
        <p>
          <span className="text-neutral-300">{DRAWDOWN_CHART_TITLE}</span>
          <span className="ml-2">{DRAWDOWN_CHART_NOTE}</span>
        </p>
        <p>{buildTradeCountNote(series.tradeCount)}</p>
      </div>
      {/* REQ-3: this sentence and the line it describes share one condition. */}
      {splitShown && <p className="mt-1 text-xs text-neutral-400">{EQUITY_CURVE_SPLIT_NOTE}</p>}
      <p className="mt-2 text-sm text-neutral-300">{EQUITY_CURVE_GUIDANCE}</p>
    </div>
  );
}
