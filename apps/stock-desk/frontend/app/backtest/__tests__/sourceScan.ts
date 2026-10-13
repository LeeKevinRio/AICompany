import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { BacktestResponse, RoundTripDetail } from "../../lib/types";

/** Drops block comments and whole-line `//` comments; enough for this component's source. */
export function stripComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .filter((line) => !/^\s*\/\//.test(line))
    .join("\n");
}

export const REPORT_VIEW_PATH = fileURLToPath(new URL("../BacktestReportView.tsx", import.meta.url));

export function readReportViewSource(): string {
  return readFileSync(REPORT_VIEW_PATH, "utf-8");
}

export function requireDetail(report: BacktestResponse): RoundTripDetail {
  if (report.round_trip_detail === null) throw new Error("fixture must carry a round_trip_detail");
  return report.round_trip_detail;
}
