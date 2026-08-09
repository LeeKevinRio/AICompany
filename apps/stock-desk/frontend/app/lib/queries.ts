"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ackAlertEvent,
  createAlert,
  createPosition,
  deleteAlert,
  deletePosition,
  evaluateAlertsNow,
  getAdvice,
  getAlertEvents,
  getAlerts,
  getBars,
  getHealth,
  getLeverageChapter,
  getPortfolioLimits,
  getPortfolioSummary,
  getPositions,
  getSectors,
  getSettings,
  getSignals,
  importPositionsCsv,
  patchAlert,
  resolveDirectorySymbol,
  runBacktest,
  searchDirectory,
  updatePosition,
  updateSettings,
} from "./api";
import type {
  AlertRuleInput,
  AlertRulePatch,
  AppSettingsPatch,
  BacktestRequest,
  CreatePositionInput,
  Market,
  UpdatePositionInput,
} from "./types";

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
    staleTime: 0,
  });
}

export function usePortfolioSummary(enabled: boolean) {
  return useQuery({
    queryKey: ["portfolio-summary"],
    queryFn: getPortfolioSummary,
    enabled,
    retry: 1,
  });
}

/** FR-8: `GET /api/portfolio/limits` — the five risk caps judged over the whole book. */
export function usePortfolioLimits(enabled: boolean) {
  return useQuery({
    queryKey: ["portfolio-limits"],
    queryFn: getPortfolioLimits,
    enabled,
    retry: 1,
  });
}

export function usePositions(enabled: boolean) {
  return useQuery({
    queryKey: ["positions"],
    queryFn: getPositions,
    enabled,
    retry: 1,
  });
}

export function useCreatePosition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreatePositionInput) => createPosition(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["positions"] });
      void queryClient.invalidateQueries({ queryKey: ["portfolio-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["portfolio-limits"] });
    },
  });
}

export function useUpdatePosition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: UpdatePositionInput }) =>
      updatePosition(id, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["positions"] });
      void queryClient.invalidateQueries({ queryKey: ["portfolio-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["portfolio-limits"] });
    },
  });
}

export function useDeletePosition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deletePosition(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["positions"] });
      void queryClient.invalidateQueries({ queryKey: ["portfolio-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["portfolio-limits"] });
    },
  });
}

/** `GET /api/positions/sectors` (FR-12) — a closed enumeration, so a longer `staleTime` is safe. */
export function useSectors(enabled: boolean) {
  return useQuery({
    queryKey: ["sectors"],
    queryFn: getSectors,
    enabled,
    retry: 1,
    staleTime: 5 * 60 * 1000,
  });
}

export function useImportPositionsCsv() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => importPositionsCsv(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["positions"] });
      void queryClient.invalidateQueries({ queryKey: ["portfolio-summary"] });
      void queryClient.invalidateQueries({ queryKey: ["portfolio-limits"] });
    },
  });
}

/* --- M7: signals / advice / leverage / backtest / settings / alerts ----- */

export function useSignals(symbol: string, market: Market, enabled: boolean) {
  return useQuery({
    queryKey: ["signals", symbol, market],
    queryFn: () => getSignals(symbol, market),
    enabled: enabled && symbol.length > 0,
    retry: 1,
  });
}

export function useBars(symbol: string, market: Market, enabled: boolean) {
  return useQuery({
    queryKey: ["bars", symbol, market],
    queryFn: () => getBars(symbol, market),
    enabled: enabled && symbol.length > 0,
    retry: 1,
  });
}

export function useAdvice(symbol: string, market: Market, enabled: boolean) {
  return useQuery({
    queryKey: ["advice", symbol, market],
    queryFn: () => getAdvice(symbol, market),
    enabled: enabled && symbol.length > 0,
    retry: 1,
  });
}

export function useLeverageChapter(symbol: string, market: Market, enabled: boolean) {
  return useQuery({
    queryKey: ["leverage", symbol, market],
    queryFn: () => getLeverageChapter(symbol, market),
    enabled: enabled && symbol.length > 0,
    retry: false, // a symbol with no matching position is an expected 404, not a transient fault
  });
}

export function useRunBacktest() {
  return useMutation({
    mutationFn: (input: BacktestRequest) => runBacktest(input),
  });
}

export function useSettings(enabled: boolean) {
  return useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
    enabled,
    retry: 1,
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AppSettingsPatch) => updateSettings(input),
    onSuccess: (data) => {
      queryClient.setQueryData(["settings"], data);
    },
  });
}

export function useAlerts(enabled: boolean) {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: () => getAlerts(),
    enabled,
    retry: 1,
  });
}

export function useEvaluateAlertsNow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: evaluateAlertsNow,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alert-events"] });
    },
  });
}

export function useCreateAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AlertRuleInput) => createAlert(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useUpdateAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: AlertRulePatch }) => patchAlert(id, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useDeleteAlert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteAlert(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useAlertEvents(unacknowledged: boolean | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["alert-events", unacknowledged ?? "all"],
    queryFn: () => getAlertEvents(unacknowledged),
    enabled,
    retry: 1,
  });
}

export function useAckAlertEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => ackAlertEvent(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alert-events"] });
    },
  });
}

/* --- Security directory (FR-3/4/6/7) ------------------------------------ */

/**
 * NavBar combobox candidates (FR-4). `q` is the already-debounced query —
 * the debounce itself lives in `directorySearch.ts`'s `createDebouncer`, not
 * here, so this hook stays a thin, ordinary query. `retry: false` because a
 * failed search should fall back to the plain symbol-direct path (FR-7)
 * immediately, not spin retrying while the user keeps typing.
 */
export function useDirectorySearch(q: string, enabled: boolean) {
  return useQuery({
    queryKey: ["directory-search", q],
    queryFn: () => searchDirectory(q),
    enabled: enabled && q.length > 0,
    retry: false,
  });
}

/**
 * One symbol's directory entry (FR-2/FR-6), used by both the individual
 * position page's title and — fanned out via `useDirectoryNames` below —
 * the positions table. Shares the `["directory-resolve", symbol]` cache key
 * with that hook so the two surfaces never issue duplicate requests for the
 * same symbol. `data` is `null` (not an error) on a directory miss —
 * `resolveDirectorySymbol` already turns the backend's 404 into that.
 */
export function useDirectoryResolve(symbol: string, enabled: boolean) {
  return useQuery({
    queryKey: ["directory-resolve", symbol],
    queryFn: () => resolveDirectorySymbol(symbol),
    enabled: enabled && symbol.length > 0,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Batches per-row company-name lookups for `PositionsTable` (FR-6/AC-14).
 * The backend contract (`app/api/directory.py`) only exposes a single-symbol
 * `resolve` endpoint, no batch form — rather than add an unverified batch
 * endpoint, this fans out one `resolve` per *unique* symbol via
 * `useQueries`, relying on react-query's cache (shared key with
 * `useDirectoryResolve`) to dedupe against the individual position page and
 * across re-renders. Returns only confirmed hits; a miss or a still-loading
 * row is simply absent from the map, so callers render "symbol only" for
 * both without needing to distinguish them (FR-7 fallback is the same
 * either way).
 */
export function useDirectoryNames(symbols: string[]): Record<string, string> {
  const uniqueSymbols = Array.from(new Set(symbols));
  const results = useQueries({
    queries: uniqueSymbols.map((symbol) => ({
      queryKey: ["directory-resolve", symbol],
      queryFn: () => resolveDirectorySymbol(symbol),
      retry: false,
      staleTime: 5 * 60 * 1000,
    })),
  });
  const names: Record<string, string> = {};
  uniqueSymbols.forEach((symbol, index) => {
    const entry = results[index]?.data;
    if (entry) names[symbol] = entry.name;
  });
  return names;
}
