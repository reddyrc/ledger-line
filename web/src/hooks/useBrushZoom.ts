import { useCallback, useEffect, useMemo, useState } from "react";

export type BrushRange = {
  startIndex: number;
  endIndex: number;
};

/**
 * Manage Recharts Brush zoom: slice data to the selected index window,
 * reset when the underlying series identity changes.
 */
export function useBrushZoom<T>(
  data: T[],
  seriesKey: string,
): {
  viewData: T[];
  brush: BrushRange | null;
  onBrushChange: (range: BrushRange) => void;
  resetZoom: () => void;
  isZoomed: boolean;
  rangeLabel: string | null;
  getDate: (row: T) => string;
} {
  const [brush, setBrush] = useState<BrushRange | null>(null);

  useEffect(() => {
    setBrush(null);
  }, [seriesKey]);

  const onBrushChange = useCallback((range: BrushRange) => {
    if (
      range == null ||
      range.startIndex == null ||
      range.endIndex == null ||
      Number.isNaN(range.startIndex) ||
      Number.isNaN(range.endIndex)
    ) {
      return;
    }
    const startIndex = Math.min(range.startIndex, range.endIndex);
    const endIndex = Math.max(range.startIndex, range.endIndex);
    if (startIndex === 0 && endIndex >= data.length - 1) {
      setBrush(null);
      return;
    }
    setBrush({ startIndex, endIndex });
  }, [data.length]);

  const resetZoom = useCallback(() => setBrush(null), []);

  const viewData = useMemo(() => {
    if (!brush || data.length === 0) return data;
    const start = Math.max(0, brush.startIndex);
    const end = Math.min(data.length - 1, brush.endIndex);
    return data.slice(start, end + 1);
  }, [data, brush]);

  const getDate = useCallback((row: T) => {
    const r = row as { date?: string };
    return r.date ?? "";
  }, []);

  const isZoomed = brush != null && viewData.length < data.length;

  const rangeLabel = useMemo(() => {
    if (!viewData.length) return null;
    const first = getDate(viewData[0]);
    const last = getDate(viewData[viewData.length - 1]);
    if (!first || !last) return null;
    return `${first} → ${last}`;
  }, [viewData, getDate]);

  return {
    viewData,
    brush,
    onBrushChange,
    resetZoom,
    isZoomed,
    rangeLabel,
    getDate,
  };
}

export const brushProps = {
  height: 30,
  travellerWidth: 10,
  stroke: "var(--accent)",
  fill: "color-mix(in srgb, var(--accent) 12%, transparent)",
} as const;
