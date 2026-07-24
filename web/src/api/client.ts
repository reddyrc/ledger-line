import type {
  EarningsCalendarResponse,
  FundamentalsResponse,
  HistoryResponse,
  IvHistoryResponse,
  MacroListResponse,
  MacroSeriesResponse,
  McapDeltaResponse,
  MetricsResponse,
  OptionsContractResponse,
  OptionsResponse,
  PeerComparisonResponse,
  RollingResponse,
  ScreenRefreshResponse,
  ScreenResponse,
  ShortInterestResponse,
  StrategiesResponse,
  StrategiesScanResponse,
  StrategyDetailResponse,
  SymbolContextResponse,
  TechnicalsResponse,
  UoaResponse,
  ValuationHistoryResponse,
} from "../types/api";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { signal });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export type PricePrimary = "tiingo" | "yfinance" | "finnhub";
export type EarningsPrimary = "fmp" | "yfinance" | "finnhub";

export type AppConfigResponse = {
  price_primary: PricePrimary;
  tiingo_configured: boolean;
  finnhub_configured: boolean;
  /** False on free Finnhub — /stock/candle is paid-only. */
  finnhub_ohlcv: boolean;
  earnings_primary: EarningsPrimary;
  fmp_configured: boolean;
};

export function fetchAppConfig(signal?: AbortSignal) {
  return getJson<AppConfigResponse>("/config", signal);
}

export function fetchHistory(
  symbol: string,
  opts: {
    start?: string;
    end?: string;
    refresh?: boolean;
    price_source?: PricePrimary;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<HistoryResponse>(
    `/symbols/${encodeURIComponent(symbol)}/history${qs(opts)}`,
    signal,
  );
}

export function fetchMetrics(
  symbol: string,
  opts: {
    start?: string;
    end?: string;
    benchmark?: string;
    refresh?: boolean;
    price_source?: PricePrimary;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<MetricsResponse>(
    `/symbols/${encodeURIComponent(symbol)}/metrics${qs(opts)}`,
    signal,
  );
}

export function fetchSymbolContext(
  symbol: string,
  opts: {
    refresh?: boolean;
    news_limit?: number;
    price_source?: PricePrimary;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<SymbolContextResponse>(
    `/symbols/${encodeURIComponent(symbol)}/context${qs({
      refresh: opts.refresh,
      news_limit:
        opts.news_limit != null ? String(opts.news_limit) : undefined,
      price_source: opts.price_source,
    })}`,
    signal,
  );
}

export function fetchTechnicals(
  symbol: string,
  opts: {
    start?: string;
    end?: string;
    refresh?: boolean;
    price_source?: PricePrimary;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<TechnicalsResponse>(
    `/symbols/${encodeURIComponent(symbol)}/technicals${qs(opts)}`,
    signal,
  );
}

export function fetchFundamentals(
  symbol: string,
  opts: { refresh?: boolean } = {},
  signal?: AbortSignal,
) {
  return getJson<FundamentalsResponse>(
    `/symbols/${encodeURIComponent(symbol)}/fundamentals${qs(opts)}`,
    signal,
  );
}

export function fetchValuationHistory(
  symbol: string,
  opts: {
    start?: string;
    end?: string;
    refresh?: boolean;
    earnings_source?: EarningsPrimary;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<ValuationHistoryResponse>(
    `/symbols/${encodeURIComponent(symbol)}/valuation-history${qs(opts)}`,
    signal,
  );
}

export function fetchShortInterest(
  symbol: string,
  opts: { start?: string; end?: string; refresh?: boolean } = {},
  signal?: AbortSignal,
) {
  return getJson<ShortInterestResponse>(
    `/symbols/${encodeURIComponent(symbol)}/short-interest${qs(opts)}`,
    signal,
  );
}

export function fetchPeers(
  symbol: string,
  opts: { limit?: number; extra?: string[]; refresh?: boolean } = {},
  signal?: AbortSignal,
) {
  return getJson<PeerComparisonResponse>(
    `/symbols/${encodeURIComponent(symbol)}/peers${qs({
      limit: opts.limit != null ? String(opts.limit) : undefined,
      extra: opts.extra?.length ? opts.extra.join(",") : undefined,
      refresh: opts.refresh ? true : undefined,
    })}`,
    signal,
  );
}

export function fetchOptions(
  symbol: string,
  opts: { expiration?: string; refresh?: boolean } = {},
  signal?: AbortSignal,
) {
  return getJson<OptionsResponse>(
    `/symbols/${encodeURIComponent(symbol)}/options${qs(opts)}`,
    signal,
  );
}

export function fetchOptionsChain(
  symbol: string,
  opts: { expiration?: string; refresh?: boolean } = {},
  signal?: AbortSignal,
) {
  return getJson<OptionsResponse>(
    `/symbols/${encodeURIComponent(symbol)}/options/chain${qs(opts)}`,
    signal,
  );
}

export function fetchOptionsContract(
  symbol: string,
  opts: {
    contract: string;
    period?: string;
    side?: string;
    strike?: number;
    day_low?: number;
    day_high?: number;
    refresh?: boolean;
  },
  signal?: AbortSignal,
) {
  return getJson<OptionsContractResponse>(
    `/symbols/${encodeURIComponent(symbol)}/options/contract${qs({
      contract: opts.contract,
      period: opts.period,
      side: opts.side,
      strike: opts.strike != null ? String(opts.strike) : undefined,
      day_low: opts.day_low != null ? String(opts.day_low) : undefined,
      day_high: opts.day_high != null ? String(opts.day_high) : undefined,
      refresh: opts.refresh ? true : undefined,
    })}`,
    signal,
  );
}

export function fetchOptionStrategies(
  symbol: string,
  opts: {
    expiration?: string;
    limit?: number;
    refresh?: boolean;
    min_oi?: number;
    min_volume?: number;
    max_spread_pct?: number;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<StrategiesResponse>(
    `/symbols/${encodeURIComponent(symbol)}/options/strategies${qs({
      expiration: opts.expiration,
      limit: opts.limit != null ? String(opts.limit) : undefined,
      refresh: opts.refresh ? true : undefined,
      min_oi: opts.min_oi != null ? String(opts.min_oi) : undefined,
      min_volume: opts.min_volume != null ? String(opts.min_volume) : undefined,
      max_spread_pct:
        opts.max_spread_pct != null ? String(opts.max_spread_pct) : undefined,
    })}`,
    signal,
  );
}

export function fetchOptionStrategyDetail(
  symbol: string,
  ideaId: string,
  opts: { expiration?: string; refresh?: boolean } = {},
  signal?: AbortSignal,
) {
  return getJson<StrategyDetailResponse>(
    `/symbols/${encodeURIComponent(symbol)}/options/strategies/${encodeURIComponent(ideaId)}${qs(opts)}`,
    signal,
  );
}

export function fetchStrategiesScan(
  opts: {
    symbols?: string[];
    expiration?: string;
    limit_per_symbol?: number;
    refresh?: boolean;
    min_oi?: number;
    min_volume?: number;
    max_spread_pct?: number;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<StrategiesScanResponse>(
    `/strategies/scan${qs({
      symbols: opts.symbols?.length ? opts.symbols.join(",") : undefined,
      expiration: opts.expiration,
      limit_per_symbol:
        opts.limit_per_symbol != null ? String(opts.limit_per_symbol) : undefined,
      refresh: opts.refresh ? true : undefined,
      min_oi: opts.min_oi != null ? String(opts.min_oi) : undefined,
      min_volume: opts.min_volume != null ? String(opts.min_volume) : undefined,
      max_spread_pct:
        opts.max_spread_pct != null ? String(opts.max_spread_pct) : undefined,
    })}`,
    signal,
  );
}

export function fetchOptionsUoa(
  symbol: string,
  opts: { expiration?: string; limit?: number; refresh?: boolean } = {},
  signal?: AbortSignal,
) {
  return getJson<UoaResponse>(
    `/symbols/${encodeURIComponent(symbol)}/options/uoa${qs({
      expiration: opts.expiration,
      limit: opts.limit != null ? String(opts.limit) : undefined,
      refresh: opts.refresh ? true : undefined,
    })}`,
    signal,
  );
}

export function fetchOptionsIvHistory(
  symbol: string,
  opts: {
    start?: string;
    end?: string;
    expiration?: string;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<IvHistoryResponse>(
    `/symbols/${encodeURIComponent(symbol)}/options/iv-history${qs({
      start: opts.start,
      end: opts.end,
      expiration: opts.expiration,
    })}`,
    signal,
  );
}

export function fetchRolling(
  symbol: string,
  opts: {
    start?: string;
    end?: string;
    window?: number;
    refresh?: boolean;
    price_source?: PricePrimary;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<RollingResponse>(
    `/symbols/${encodeURIComponent(symbol)}/rolling${qs({
      start: opts.start,
      end: opts.end,
      window: opts.window != null ? String(opts.window) : undefined,
      refresh: opts.refresh ? true : undefined,
      price_source: opts.price_source,
    })}`,
    signal,
  );
}

export function fetchEarningsCalendar(
  opts: {
    start?: string;
    end?: string;
    symbols?: string[];
    refresh?: boolean;
    earnings_source?: EarningsPrimary;
  } = {},
  signal?: AbortSignal,
) {
  return getJson<EarningsCalendarResponse>(
    `/earnings/calendar${qs({
      start: opts.start,
      end: opts.end,
      symbols: opts.symbols?.length ? opts.symbols.join(",") : undefined,
      refresh: opts.refresh ? true : undefined,
      earnings_source: opts.earnings_source,
    })}`,
    signal,
  );
}

export function fetchMcapDelta(
  opts: {
    symbols: string[];
    start?: string;
    end?: string;
    refresh?: boolean;
    price_source?: PricePrimary;
  },
  signal?: AbortSignal,
) {
  return getJson<McapDeltaResponse>(
    `/mcap-delta${qs({
      symbols: opts.symbols.join(","),
      start: opts.start,
      end: opts.end,
      refresh: opts.refresh ? true : undefined,
      price_source: opts.price_source,
    })}`,
    signal,
  );
}

export type ScreenQuery = {
  q?: string;
  sector?: string;
  pe_min?: number;
  pe_max?: number;
  pb_min?: number;
  pb_max?: number;
  ps_min?: number;
  ps_max?: number;
  roe_min?: number;
  roe_max?: number;
  market_cap_min?: number;
  market_cap_max?: number;
  momentum_3m_min?: number;
  momentum_3m_max?: number;
  momentum_12m_min?: number;
  momentum_12m_max?: number;
  vol_ann_min?: number;
  vol_ann_max?: number;
  max_drawdown_1y_min?: number;
  max_drawdown_1y_max?: number;
  sort?: string;
  order?: string;
  limit?: number;
  offset?: number;
};

export function fetchScreen(opts: ScreenQuery = {}, signal?: AbortSignal) {
  const params: Record<string, string | boolean | undefined | null> = {};
  for (const [k, v] of Object.entries(opts)) {
    if (v === undefined || v === null || v === "") continue;
    params[k] = typeof v === "number" ? String(v) : (v as string | boolean);
  }
  return getJson<ScreenResponse>(`/screen${qs(params)}`, signal);
}

export function fetchScreenSectors(signal?: AbortSignal) {
  return getJson<{ sectors: string[] }>("/screen/sectors", signal);
}

export async function refreshScreen(opts: {
  limit?: number;
  offset?: number;
  sleep?: number;
  skip_fundamentals?: boolean;
} = {}): Promise<ScreenRefreshResponse> {
  const params = qs({
    limit: opts.limit != null ? String(opts.limit) : undefined,
    offset: opts.offset != null ? String(opts.offset) : undefined,
    sleep: opts.sleep != null ? String(opts.sleep) : undefined,
    skip_fundamentals: opts.skip_fundamentals || undefined,
  });
  const res = await fetch(
    `${BASE}/screen/refresh${params}`,
    { method: "POST" },
  );
  if (!res.ok) {
    throw new ApiError(res.status, "Screener refresh failed");
  }
  return res.json() as Promise<ScreenRefreshResponse>;
}

export function fetchMacroList(signal?: AbortSignal) {
  return getJson<MacroListResponse>("/macro", signal);
}

export function fetchMacroSeries(
  seriesId: string,
  opts: { start?: string; end?: string; refresh?: boolean } = {},
  signal?: AbortSignal,
) {
  return getJson<MacroSeriesResponse>(
    `/macro/${encodeURIComponent(seriesId)}${qs(opts)}`,
    signal,
  );
}

export async function bootstrapMacro(): Promise<{
  ingested: Record<string, number>;
}> {
  const res = await fetch(`${BASE}/macro/bootstrap`, { method: "POST" });
  if (!res.ok) {
    throw new ApiError(res.status, "Failed to bootstrap macro series");
  }
  return res.json() as Promise<{ ingested: Record<string, number> }>;
}
