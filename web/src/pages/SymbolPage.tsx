import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
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
  useHistories,
  useHistory,
  useMetrics,
  usePeers,
  usePricePrimaryPreference,
  useEarningsPrimaryPreference,
  useAppConfig,
  useShortInterest,
  useSymbolContext,
  useTechnicals,
  useValuationHistory,
} from "../api/hooks";
import type { EarningsPrimary, PricePrimary } from "../api/client";
import { DateRangeControls } from "../components/DateRangeControls";
import { FundamentalsPanel } from "../components/FundamentalsPanel";
import { MetricStrip } from "../components/MetricStrip";
import { OptionsSummaryPanel } from "../components/OptionsSummaryPanel";
import { PeerComparisonPanel } from "../components/PeerComparisonPanel";
import { PriceChart } from "../components/PriceChart";
import { RollingRiskPanel } from "../components/RollingRiskPanel";
import { SectionRangeControls } from "../components/SectionRangeControls";
import { ShortInterestPanel } from "../components/ShortInterestPanel";
import { SymbolSectionNav } from "../components/SymbolSectionNav";
import { TechnicalsPanel } from "../components/TechnicalsPanel";
import { TiingoNewsPanel } from "../components/TiingoNewsPanel";
import { ValuationHistoryPanel } from "../components/ValuationHistoryPanel";
import { useSectionRange } from "../hooks/useSectionRange";
import { normalizeTicker } from "../lib/format";
import { useSeo } from "../lib/seo";

const COMPARE_KEY = "ledgerline.price.compare";

const SYMBOL_SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "price", label: "Price" },
  { id: "valuation", label: "Valuation" },
  { id: "short-interest", label: "Short interest" },
  { id: "peers", label: "Peers" },
  { id: "options", label: "Options" },
  { id: "rolling-risk", label: "Rolling risk" },
  { id: "technicals", label: "Technicals" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "news", label: "News" },
] as const;

function readCompareTickers(primary: string): string[] {
  try {
    const raw = localStorage.getItem(`${COMPARE_KEY}.${primary}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((t) => normalizeTicker(String(t)))
      .filter((t) => t && t !== primary)
      .slice(0, 5);
  } catch {
    return [];
  }
}

function writeCompareTickers(primary: string, tickers: string[]) {
  try {
    localStorage.setItem(
      `${COMPARE_KEY}.${primary}`,
      JSON.stringify(tickers.slice(0, 5)),
    );
  } catch {
    /* ignore */
  }
}

export function SymbolPage() {
  const { symbol: raw } = useParams();
  const symbol = normalizeTicker(raw ?? "");
  useSeo(
    `${symbol} stock metrics, valuation history & fundamentals`,
    `${symbol} historical performance: Sharpe, volatility, drawdown, beta, P/E and valuation history, balance sheet from SEC EDGAR, short interest, and post-earnings moves.`,
  );
  const [mode, setMode] = useState<"preset" | "custom">("preset");
  const [preset, setPreset] = useState<RangePreset>("5Y");
  const [custom, setCustom] = useState<DateBounds>(() => ({
    start: startForPreset("5Y"),
    end: todayISO(),
  }));
  const [benchmark, setBenchmark] = useState("SPY");
  const [benchDraft, setBenchDraft] = useState("SPY");
  const [customPeers, setCustomPeers] = useState<string[]>([]);
  const [compareTickers, setCompareTickers] = useState<string[]>(() =>
    readCompareTickers(normalizeTicker(raw ?? "")),
  );
  const [refreshing, setRefreshing] = useState(false);
  const [pricePrimary, setPricePrimary] = usePricePrimaryPreference();
  const [earningsPrimary, setEarningsPrimary] = useEarningsPrimaryPreference();
  const appConfig = useAppConfig();
  const finnhubConfigured = appConfig.data?.finnhub_configured ?? false;
  const finnhubOhlcv = appConfig.data?.finnhub_ohlcv ?? false;
  const qc = useQueryClient();

  // Reset compare list when navigating to a different primary symbol
  useEffect(() => {
    setCompareTickers(readCompareTickers(symbol));
  }, [symbol]);

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
  const rollingRange = useSectionRange(globalSelection);

  const history = useHistory(symbol, priceRange.bounds, pricePrimary);
  const compareQueries = useHistories(
    compareTickers,
    priceRange.bounds,
    pricePrimary,
  );
  const compareSeries = compareTickers.map((t, i) => ({
    symbol: t,
    bars: compareQueries[i]?.data?.bars ?? [],
  }));
  const compareLoading = compareQueries.some((q) => q.isLoading);

  function setCompare(next: string[]) {
    const cleaned = next
      .map((t) => normalizeTicker(t))
      .filter((t) => t && t !== symbol)
      .slice(0, 5);
    setCompareTickers(cleaned);
    writeCompareTickers(symbol, cleaned);
  }

  const metrics = useMetrics(symbol, bounds, benchmark, pricePrimary);
  const context = useSymbolContext(symbol, pricePrimary);
  const technicals = useTechnicals(
    symbol,
    technicalsRange.bounds,
    pricePrimary,
  );
  const fundamentals = useFundamentals(symbol);
  const valuation = useValuationHistory(
    symbol,
    valuationRange.bounds,
    earningsPrimary,
  );
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

  async function onRefresh(
    source: PricePrimary = pricePrimary,
    earningsSource: EarningsPrimary = earningsPrimary,
  ) {
    if (!symbol || refreshing) return;
    setRefreshing(true);
    try {
      await Promise.all([
        fetchHistory(symbol, {
          start: priceRange.bounds.start,
          end: priceRange.bounds.end,
          refresh: true,
          price_source: source,
        }),
        fetchMetrics(symbol, {
          start: bounds.start,
          end: bounds.end,
          benchmark,
          refresh: true,
          price_source: source,
        }),
        fetchTechnicals(symbol, {
          start: technicalsRange.bounds.start,
          end: technicalsRange.bounds.end,
          refresh: true,
          price_source: source,
        }),
        fetchFundamentals(symbol, { refresh: true }),
        fetchValuationHistory(symbol, {
          start: valuationRange.bounds.start,
          end: valuationRange.bounds.end,
          refresh: true,
          earnings_source: earningsSource,
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
        qc.invalidateQueries({ queryKey: ["symbol-context", symbol] }),
      ]);
    } finally {
      setRefreshing(false);
    }
  }

  async function onPricePrimaryChange(next: PricePrimary) {
    if (next === pricePrimary) return;
    setPricePrimary(next);
    await onRefresh(next, earningsPrimary);
  }

  async function onEarningsPrimaryChange(next: EarningsPrimary) {
    if (next === earningsPrimary) return;
    setEarningsPrimary(next);
    await onRefresh(pricePrimary, next);
  }

  if (!symbol) {
    return <p className="muted">Enter a valid ticker.</p>;
  }

  return (
    <div className="symbol-page fade-in">
      <div className="symbol-page-layout">
        <SymbolSectionNav sections={[...SYMBOL_SECTIONS]} />
        <div className="symbol-page-main">
      <div className="symbol-header">
        <div>
          <h1 className="symbol-title mono">{symbol}</h1>
          {context.data?.meta?.name && (
            <p className="symbol-company-name">{context.data.meta.name}</p>
          )}
          <p className="muted small">
            {[
              context.data?.meta?.exchange,
              `${metrics.data?.metrics.start ?? bounds.start ?? "—"} → ${
                metrics.data?.metrics.end ?? bounds.end ?? "—"
              }`,
              metrics.data?.metrics.source
                ? metrics.data.metrics.source
                : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <div
            className="price-primary-toggle"
            role="group"
            aria-label="Price data provider"
          >
            <span className="muted small">Prices</span>
            <button
              type="button"
              className={`chart-toggle-btn${pricePrimary === "tiingo" ? " active" : ""}`}
              disabled={refreshing}
              onClick={() => void onPricePrimaryChange("tiingo")}
            >
              Tiingo
            </button>
            <button
              type="button"
              className={`chart-toggle-btn${pricePrimary === "yfinance" ? " active" : ""}`}
              disabled={refreshing}
              onClick={() => void onPricePrimaryChange("yfinance")}
            >
              Yahoo
            </button>
            <button
              type="button"
              className={`chart-toggle-btn${pricePrimary === "finnhub" ? " active" : ""}`}
              disabled={
                refreshing ||
                (appConfig.isSuccess && !finnhubConfigured)
              }
              title={
                appConfig.isSuccess && !finnhubConfigured
                  ? "Set FINNHUB_API_KEY to enable"
                  : finnhubOhlcv
                    ? "Finnhub daily candles"
                    : "Finnhub preferred — free tier has no candles, so history falls back to Tiingo/Yahoo"
              }
              onClick={() => void onPricePrimaryChange("finnhub")}
            >
              Finnhub
            </button>
          </div>
          <div
            className="price-primary-toggle"
            role="group"
            aria-label="Earnings data provider"
          >
            <span className="muted small">Earnings</span>
            <button
              type="button"
              className={`chart-toggle-btn${earningsPrimary === "fmp" ? " active" : ""}`}
              disabled={refreshing}
              onClick={() => void onEarningsPrimaryChange("fmp")}
            >
              FMP
            </button>
            <button
              type="button"
              className={`chart-toggle-btn${earningsPrimary === "yfinance" ? " active" : ""}`}
              disabled={refreshing}
              onClick={() => void onEarningsPrimaryChange("yfinance")}
            >
              Yahoo
            </button>
            <button
              type="button"
              className={`chart-toggle-btn${earningsPrimary === "finnhub" ? " active" : ""}`}
              disabled={
                refreshing ||
                (appConfig.isSuccess && !finnhubConfigured)
              }
              title={
                appConfig.isSuccess && !finnhubConfigured
                  ? "Set FINNHUB_API_KEY to enable"
                  : "Finnhub earnings history"
              }
              onClick={() => void onEarningsPrimaryChange("finnhub")}
            >
              Finnhub
            </button>
          </div>
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

      <section id="overview" className="symbol-section">
        <MetricStrip
          metrics={metrics.data?.metrics}
          loading={metrics.isLoading}
          benchmark={benchmark}
        />
      </section>

      <section id="price" className="symbol-section panel">
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
          <PriceChart
            symbol={symbol}
            bars={history.data?.bars ?? []}
            compare={compareSeries}
            compareTickers={compareTickers}
            onCompareChange={setCompare}
            compareLoading={compareLoading}
          />
        )}
      </section>

      <section id="valuation" className="symbol-section">
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
      </section>

      <section id="short-interest" className="symbol-section">
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
      </section>

      <section id="peers" className="symbol-section">
        <PeerComparisonPanel
          data={peers.data}
          loading={peers.isLoading}
          customPeers={customPeers}
          onCustomPeersChange={setCustomPeers}
        />
      </section>

      <section id="options" className="symbol-section">
        <OptionsSummaryPanel symbol={symbol} />
      </section>

      <section id="rolling-risk" className="symbol-section">
        <RollingRiskPanel
          symbol={symbol}
          bounds={rollingRange.bounds}
          rangeControls={
            <SectionRangeControls
              label="Rolling risk"
              selection={rollingRange.selection}
              isOverridden={rollingRange.isOverridden}
              onPreset={rollingRange.selectPreset}
              onCustomMode={rollingRange.selectCustomMode}
              onCustomChange={rollingRange.setCustom}
              onFollowGlobal={rollingRange.followGlobal}
            />
          }
        />
      </section>

      <section id="technicals" className="symbol-section">
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
      </section>

      <div className="two-col">
        <section id="fundamentals" className="symbol-section">
          <FundamentalsPanel
            data={fundamentals.data}
            loading={fundamentals.isLoading}
          />
        </section>
        <section id="news" className="symbol-section">
          <TiingoNewsPanel
            news={context.data?.news ?? []}
            loading={context.isLoading}
            configured={context.data?.configured}
            source={context.data?.source}
          />
        </section>
      </div>

      {metrics.data?.disclaimer && (
        <p className="disclaimer">{metrics.data.disclaimer}</p>
      )}
        </div>
      </div>
    </div>
  );
}
