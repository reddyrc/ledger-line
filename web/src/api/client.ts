import type {
  FundamentalsResponse,
  HistoryResponse,
  MacroListResponse,
  MacroSeriesResponse,
  MetricsResponse,
  ScreenRefreshResponse,
  ScreenResponse,
  TechnicalsResponse,
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

export function fetchHistory(
  symbol: string,
  opts: { start?: string; end?: string; refresh?: boolean } = {},
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
  } = {},
  signal?: AbortSignal,
) {
  return getJson<MetricsResponse>(
    `/symbols/${encodeURIComponent(symbol)}/metrics${qs(opts)}`,
    signal,
  );
}

export function fetchTechnicals(
  symbol: string,
  opts: { start?: string; end?: string; refresh?: boolean } = {},
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
  opts: { start?: string; end?: string; refresh?: boolean } = {},
  signal?: AbortSignal,
) {
  return getJson<ValuationHistoryResponse>(
    `/symbols/${encodeURIComponent(symbol)}/valuation-history${qs(opts)}`,
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
