import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  bootstrapMacro,
  fetchFundamentals,
  fetchHistory,
  fetchMacroList,
  fetchMacroSeries,
  fetchMetrics,
  fetchScreen,
  fetchScreenSectors,
  fetchTechnicals,
  fetchValuationHistory,
  refreshScreen,
  type ScreenQuery,
} from "./client";

/** Preset historic windows (plus custom via DateBounds). */
export type RangePreset = "1Y" | "2Y" | "3Y" | "5Y" | "10Y" | "ALL";

export type DateBounds = {
  start?: string;
  end?: string;
};

export const RANGE_PRESETS: Array<{ key: RangePreset; label: string }> = [
  { key: "1Y", label: "1Y" },
  { key: "2Y", label: "2Y" },
  { key: "3Y", label: "3Y" },
  { key: "5Y", label: "5Y" },
  { key: "10Y", label: "10Y" },
  { key: "ALL", label: "All" },
];

const PRESET_YEARS: Record<Exclude<RangePreset, "ALL">, number> = {
  "1Y": 1,
  "2Y": 2,
  "3Y": 3,
  "5Y": 5,
  "10Y": 10,
};

/** @deprecated Use RangePreset; kept for any older imports. */
export type RangeKey = RangePreset;

export function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

export function startForPreset(preset: RangePreset): string | undefined {
  if (preset === "ALL") return undefined;
  const d = new Date();
  d.setFullYear(d.getFullYear() - PRESET_YEARS[preset]);
  return d.toISOString().slice(0, 10);
}

/** A full range selection: which preset is active, or a custom from/to. */
export type RangeSelection = {
  mode: "preset" | "custom";
  preset: RangePreset;
  custom: DateBounds;
};

export function defaultSelection(preset: RangePreset = "5Y"): RangeSelection {
  return {
    mode: "preset",
    preset,
    custom: { start: startForPreset(preset), end: todayISO() },
  };
}

/** Resolve API start/end from a preset or an explicit custom range. */
export function boundsForSelection(
  mode: "preset" | "custom",
  preset: RangePreset,
  custom: DateBounds,
): DateBounds {
  if (mode === "custom") {
    const start = custom.start || undefined;
    const end = custom.end || undefined;
    if (start && end && start > end) {
      return { start: end, end: start };
    }
    return { start, end };
  }
  return { start: startForPreset(preset), end: undefined };
}

export function selectionBounds(sel: RangeSelection): DateBounds {
  return boundsForSelection(sel.mode, sel.preset, sel.custom);
}

/** @deprecated Use startForPreset */
export function startForRange(range: RangePreset): string | undefined {
  return startForPreset(range);
}

export function useHistory(symbol: string, bounds: DateBounds) {
  return useQuery({
    queryKey: ["history", symbol, bounds.start ?? null, bounds.end ?? null],
    queryFn: ({ signal }) =>
      fetchHistory(
        symbol,
        { start: bounds.start, end: bounds.end },
        signal,
      ),
    enabled: Boolean(symbol),
  });
}

export function useMetrics(
  symbol: string,
  bounds: DateBounds,
  benchmark: string,
) {
  return useQuery({
    queryKey: [
      "metrics",
      symbol,
      bounds.start ?? null,
      bounds.end ?? null,
      benchmark,
    ],
    queryFn: ({ signal }) =>
      fetchMetrics(
        symbol,
        { start: bounds.start, end: bounds.end, benchmark },
        signal,
      ),
    enabled: Boolean(symbol),
  });
}

export function useTechnicals(symbol: string, bounds: DateBounds) {
  return useQuery({
    queryKey: ["technicals", symbol, bounds.start ?? null, bounds.end ?? null],
    queryFn: ({ signal }) =>
      fetchTechnicals(
        symbol,
        { start: bounds.start, end: bounds.end },
        signal,
      ),
    enabled: Boolean(symbol),
  });
}

export function useFundamentals(symbol: string) {
  return useQuery({
    queryKey: ["fundamentals", symbol],
    queryFn: ({ signal }) => fetchFundamentals(symbol, {}, signal),
    enabled: Boolean(symbol),
  });
}

export function useValuationHistory(symbol: string, bounds: DateBounds) {
  return useQuery({
    queryKey: [
      "valuation-history",
      symbol,
      bounds.start ?? null,
      bounds.end ?? null,
    ],
    queryFn: ({ signal }) =>
      fetchValuationHistory(
        symbol,
        { start: bounds.start, end: bounds.end },
        signal,
      ),
    enabled: Boolean(symbol),
  });
}

export function useScreen(query: ScreenQuery) {
  return useQuery({
    queryKey: ["screen", query],
    queryFn: ({ signal }) => fetchScreen(query, signal),
  });
}

export function useScreenSectors() {
  return useQuery({
    queryKey: ["screen-sectors"],
    queryFn: ({ signal }) => fetchScreenSectors(signal),
  });
}

export function useRefreshScreen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: refreshScreen,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["screen"] });
      void qc.invalidateQueries({ queryKey: ["screen-sectors"] });
    },
  });
}

export function useMacroList() {
  return useQuery({
    queryKey: ["macro-list"],
    queryFn: ({ signal }) => fetchMacroList(signal),
  });
}

export function useMacroSeries(seriesId: string) {
  return useQuery({
    queryKey: ["macro", seriesId],
    queryFn: ({ signal }) => fetchMacroSeries(seriesId, {}, signal),
    enabled: Boolean(seriesId),
  });
}

export function useBootstrapMacro() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: bootstrapMacro,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["macro"] });
      void qc.invalidateQueries({ queryKey: ["macro-list"] });
    },
  });
}
