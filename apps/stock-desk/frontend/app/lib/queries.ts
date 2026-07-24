"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPosition,
  getHealth,
  getPortfolioSummary,
  getPositions,
  importPositionsCsv,
} from "./api";
import type { CreatePositionInput } from "./types";

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
