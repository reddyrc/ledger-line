import {
  RANGE_PRESETS,
  type DateBounds,
  type RangePreset,
  type RangeSelection,
  startForPreset,
  todayISO,
} from "../api/hooks";

type Props = {
  selection: RangeSelection;
  isOverridden: boolean;
  onPreset: (preset: RangePreset) => void;
  onCustomMode: () => void;
  onCustomChange: (next: DateBounds) => void;
  onFollowGlobal: () => void;
  label: string;
};

/** Compact per-chart range picker that can diverge from the page range. */
export function SectionRangeControls({
  selection,
  isOverridden,
  onPreset,
  onCustomMode,
  onCustomChange,
  onFollowGlobal,
  label,
}: Props) {
  const { mode, preset, custom } = selection;
  const customStart = custom.start ?? startForPreset("5Y") ?? "";
  const customEnd = custom.end ?? todayISO();

  return (
    <div className="section-range">
      <div
        className="segmented segmented-sm"
        role="group"
        aria-label={`${label} period`}
      >
        {RANGE_PRESETS.map((r) => (
          <button
            key={r.key}
            type="button"
            className={mode === "preset" && preset === r.key ? "active" : ""}
            onClick={() => onPreset(r.key)}
          >
            {r.label}
          </button>
        ))}
        <button
          type="button"
          className={mode === "custom" ? "active" : ""}
          onClick={onCustomMode}
        >
          Custom
        </button>
      </div>
      {isOverridden && (
        <button
          type="button"
          className="btn-text"
          title="Follow the page-level date range again"
          onClick={onFollowGlobal}
        >
          Sync to page
        </button>
      )}
      {mode === "custom" && (
        <div className="custom-dates">
          <label className="date-field">
            <span>From</span>
            <input
              type="date"
              className="mono"
              value={customStart}
              max={customEnd || undefined}
              onChange={(e) =>
                onCustomChange({ ...custom, start: e.target.value || undefined })
              }
            />
          </label>
          <label className="date-field">
            <span>To</span>
            <input
              type="date"
              className="mono"
              value={customEnd}
              min={customStart || undefined}
              max={todayISO()}
              onChange={(e) =>
                onCustomChange({ ...custom, end: e.target.value || undefined })
              }
            />
          </label>
        </div>
      )}
    </div>
  );
}
