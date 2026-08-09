"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  getPortfolioSummary,
  getPositions,
  getSectors,
  getSettings,
  getSignals,
  importPositionsCsv,
  runBacktest,
  updatePosition,
  updateSettings,
} from "./api";
import type {
  AlertRuleInput,
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
