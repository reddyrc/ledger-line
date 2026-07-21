import { useEffect, useMemo, useState } from "react";

import {
  type DateBounds,
  type RangePreset,
  type RangeSelection,
  selectionBounds,
  startForPreset,
  todayISO,
} from "../api/hooks";

/**
 * Per-section date range that follows a global selection until the user
 * overrides it locally. Changing the global selection re-syncs the section.
 */
export function useSectionRange(global: RangeSelection): {
  selection: RangeSelection;
  bounds: DateBounds;
  isOverridden: boolean;
  selectPreset: (preset: RangePreset) => void;
  selectCustomMode: () => void;
  setCustom: (custom: DateBounds) => void;
  followGlobal: () => void;
} {
  const [override, setOverride] = useState<RangeSelection | null>(null);

  const globalKey = `${global.mode}:${global.preset}:${global.custom.start ?? ""}:${global.custom.end ?? ""}`;
  useEffect(() => {
    setOverride(null);
  }, [globalKey]);

  const selection = override ?? global;
  const bounds = useMemo(() => selectionBounds(selection), [selection]);

  const selectPreset = (preset: RangePreset) =>
    setOverride({
      mode: "preset",
      preset,
      custom: { start: startForPreset(preset), end: todayISO() },
    });

  const selectCustomMode = () =>
    setOverride({
      mode: "custom",
      preset: selection.preset,
      custom: {
        start:
          selection.custom.start ??
          startForPreset(selection.preset) ??
          startForPreset("5Y"),
        end: selection.custom.end ?? todayISO(),
      },
    });

  const setCustom = (custom: DateBounds) =>
    setOverride({ mode: "custom", preset: selection.preset, custom });

  return {
    selection,
    bounds,
    isOverridden: override != null,
    selectPreset,
    selectCustomMode,
    setCustom,
    followGlobal: () => setOverride(null),
  };
}
