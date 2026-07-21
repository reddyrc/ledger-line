import {
  RANGE_PRESETS,
  type DateBounds,
  type RangePreset,
  startForPreset,
  todayISO,
} from "../api/hooks";

type Props = {
  mode: "preset" | "custom";
  preset: RangePreset;
  custom: DateBounds;
  onPreset: (preset: RangePreset) => void;
  onCustomChange: (next: DateBounds) => void;
  onModeCustom: () => void;
};

export function DateRangeControls({
  mode,
  preset,
  custom,
  onPreset,
  onCustomChange,
  onModeCustom,
}: Props) {
  const customStart = custom.start ?? startForPreset("5Y") ?? "";
  const customEnd = custom.end ?? todayISO();

  return (
    <div className="date-range-controls">
      <div className="segmented" role="group" aria-label="Historic period">
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
          onClick={onModeCustom}
        >
          Custom
        </button>
      </div>

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
