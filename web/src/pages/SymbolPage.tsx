import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import {
  fetchFundamentals,
  fetchHistory,
  fetchMetrics,
  fetchPeers,
  fetchShortInterest,
  fetchTechnicals,
  fetchValuationHistory,
} from "../api/client";
import {
  type DateBounds,
  type RangePreset,
  type RangeSelection,
  boundsForSelection,
  startForPreset,
  todayISO,
  useFundamentals,
  useHistory,
  useMetrics,
  usePeers,
  useShortInterest,
  useTechnicals,
  useValuationHistory,
} from "../api/hooks";
import { DateRangeControls } from "../components/DateRangeControls";
import { FundamentalsPanel } from "../components/FundamentalsPanel";
import { MetricStrip } from "../components/MetricStrip";
import { OptionsSummaryPanel } from "../components/OptionsSummaryPanel";
import { PeerComparisonPanel } from "../components/PeerComparisonPanel";
import { PriceChart } from "../components/PriceChart";
import { SectionRangeControls } from "../components/SectionRangeControls";
import { ShortInterestPanel } from "../components/ShortInterestPanel";
import { TechnicalsPanel } from "../components/TechnicalsPanel";
import { ValuationHistoryPanel } from "../components/ValuationHistoryPanel";
import { useSectionRange } from "../hooks/useSectionRange";
import { normalizeTicker } from "../lib/format";

export function SymbolPage() {
  const { symbol: raw } = useParams();
  const symbol = normalizeTicker(raw ?? "");
  const [mode, setMode] = useState<"preset" | "custom">("preset");
  const [preset, setPreset] = useState<RangePreset>("5Y");
  const [custom, setCustom] = useState<DateBounds>(() => ({
    start: startForPreset("5Y"),
    end: todayISO(),
  }));
  const [benchmark, setBenchmark] = useState("SPY");
  const [benchDraft, setBenchDraft] = useState("SPY");
  const [customPeers, setCustomPeers] = useState<string[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const qc = useQueryClient();

  const globalSelection: RangeSelection = useMemo(
    () => ({ mode, preset, custom }),
    [mode, preset, custom],
  );
  const bounds = useMemo(
    () => boundsForSelection(mode, preset, custom),
    [mode, preset, custom],
  );

  const priceRange = useSectionRange(globalSelection);
  const valuationRange = useSectionRange(globalSelection);
  const shortInterestRange = useSectionRange(globalSelection);
  const technicalsRange = useSectionRange(globalSelection);

  const history = useHistory(symbol, priceRange.bounds);
  const metrics = useMetrics(symbol, bounds, benchmark);
  const technicals = useTechnicals(symbol, technicalsRange.bounds);
  const fundamentals = useFundamentals(symbol);
  const valuation = useValuationHistory(symbol, valuationRange.bounds);
  const shortInterest = useShortInterest(symbol, shortInterestRange.bounds);
  const peers = usePeers(symbol, 12, customPeers);

  const error =
    history.error ||
    metrics.error ||
    technicals.error ||
    fundamentals.error ||
    valuation.error ||
    shortInterest.error ||
    peers.error;

  function selectPreset(next: RangePreset) {
    setMode("preset");
    setPreset(next);
    setCustom({
      start: startForPreset(next),
      end: todayISO(),
    });
  }

  function selectCustomMode() {
    setMode("custom");
    setCustom((prev) => ({
      start: prev.start ?? startForPreset(preset) ?? startForPreset("5Y"),
      end: prev.end ?? todayISO(),
    }));
  }

  async function onRefresh() {
    if (!symbol || refreshing) return;
    setRefreshing(true);
    try {
      await Promise.all([
        fetchHistory(symbol, {
          start: priceRange.bounds.start,
          end: priceRange.bounds.end,
          refresh: true,
        }),
        fetchMetrics(symbol, {
          start: bounds.start,
          end: bounds.end,
          benchmark,
          refresh: true,
        }),
        fetchTechnicals(symbol, {
          start: technicalsRange.bounds.start,
          end: technicalsRange.bounds.end,
          refresh: true,
        }),
        fetchFundamentals(symbol, { refresh: true }),
        fetchValuationHistory(symbol, {
          start: valuationRange.bounds.start,
          end: valuationRange.bounds.end,
          refresh: true,
        }),
        fetchShortInterest(symbol, {
          start: shortInterestRange.bounds.start,
          end: shortInterestRange.bounds.end,
          refresh: true,
        }),
        fetchPeers(symbol, { extra: customPeers, refresh: true }),
      ]);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["history", symbol] }),
        qc.invalidateQueries({ queryKey: ["metrics", symbol] }),
        qc.invalidateQueries({ queryKey: ["technicals", symbol] }),
        qc.invalidateQueries({ queryKey: ["fundamentals", symbol] }),
        qc.invalidateQueries({ queryKey: ["valuation-history", symbol] }),
        qc.invalidateQueries({ queryKey: ["short-interest", symbol] }),
        qc.invalidateQueries({ queryKey: ["peers", symbol] }),
      ]);
    } finally {
      setRefreshing(false);
    }
  }

  if (!symbol) {
    return <p className="muted">Enter a valid ticker.</p>;
  }

  return (
    <div className="symbol-page fade-in">
      <div className="symbol-header">
        <div>
          <h1 className="symbol-title mono">{symbol}</h1>
          <p className="muted small">
            {metrics.data?.metrics.start ?? bounds.start ?? "—"} →{" "}
            {metrics.data?.metrics.end ?? bounds.end ?? "—"}
            {metrics.data?.metrics.source
              ? ` · ${metrics.data.metrics.source}`
              : ""}
          </p>
        </div>
        <div className="controls">
          <DateRangeControls
            mode={mode}
            preset={preset}
            custom={custom}
            onPreset={selectPreset}
            onCustomChange={setCustom}
            onModeCustom={selectCustomMode}
          />
          <label className="bench-label">
            Bench
            <input
              className="bench-input mono"
              value={benchDraft}
              onChange={(e) => setBenchDraft(e.target.value.toUpperCase())}
              onBlur={() => {
                const next = normalizeTicker(benchDraft) || "SPY";
                setBenchDraft(next);
                setBenchmark(next);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
              }}
              maxLength={8}
              placeholder="SPY"
            />
          </label>
          <button
            type="button"
            className="btn-secondary"
            disabled={refreshing}
            onClick={() => void onRefresh()}
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <div className="banner error">
          {(error as Error).message || "Failed to load symbol data."}
        </div>
      )}

      <MetricStrip
        metrics={metrics.data?.metrics}
        loading={metrics.isLoading}
        benchmark={benchmark}
      />

      <div className="panel">
        <div className="panel-head">
          <h3>Price</h3>
          <SectionRangeControls
            label="Price"
            selection={priceRange.selection}
            isOverridden={priceRange.isOverridden}
            onPreset={priceRange.selectPreset}
            onCustomMode={priceRange.selectCustomMode}
            onCustomChange={priceRange.setCustom}
            onFollowGlobal={priceRange.followGlobal}
          />
        </div>
        {history.isLoading ? (
          <div className="chart-skeleton skeleton-block" />
        ) : (
          <PriceChart bars={history.data?.bars ?? []} />
        )}
      </div>

      <ValuationHistoryPanel
        data={valuation.data}
        loading={valuation.isLoading}
        rangeControls={
          <SectionRangeControls
            label="Valuation"
            selection={valuationRange.selection}
            isOverridden={valuationRange.isOverridden}
            onPreset={valuationRange.selectPreset}
            onCustomMode={valuationRange.selectCustomMode}
            onCustomChange={valuationRange.setCustom}
            onFollowGlobal={valuationRange.followGlobal}
          />
        }
      />

      <ShortInterestPanel
        data={shortInterest.data}
        loading={shortInterest.isLoading}
        rangeControls={
          <SectionRangeControls
            label="Short interest"
            selection={shortInterestRange.selection}
            isOverridden={shortInterestRange.isOverridden}
            onPreset={shortInterestRange.selectPreset}
            onCustomMode={shortInterestRange.selectCustomMode}
            onCustomChange={shortInterestRange.setCustom}
            onFollowGlobal={shortInterestRange.followGlobal}
          />
        }
      />

      <PeerComparisonPanel
        data={peers.data}
        loading={peers.isLoading}
        customPeers={customPeers}
        onCustomPeersChange={setCustomPeers}
      />

      <OptionsSummaryPanel symbol={symbol} />

      <div className="two-col">
        <TechnicalsPanel
          series={technicals.data?.series ?? []}
          latest={technicals.data?.latest}
          loading={technicals.isLoading}
          rangeControls={
            <SectionRangeControls
              label="Technicals"
              selection={technicalsRange.selection}
              isOverridden={technicalsRange.isOverridden}
              onPreset={technicalsRange.selectPreset}
              onCustomMode={technicalsRange.selectCustomMode}
              onCustomChange={technicalsRange.setCustom}
              onFollowGlobal={technicalsRange.followGlobal}
            />
          }
        />
        <FundamentalsPanel
          data={fundamentals.data}
          loading={fundamentals.isLoading}
        />
      </div>

      {metrics.data?.disclaimer && (
        <p className="disclaimer">{metrics.data.disclaimer}</p>
      )}
    </div>
  );
}
