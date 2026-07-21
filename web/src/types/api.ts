export type OhlcvBar = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  adj_close: number | null;
  volume: number | null;
};

export type HistoryResponse = {
  symbol: string;
  bars: OhlcvBar[];
  count: number;
};

export type MetricsPayload = {
  bars: number;
  start: string | null;
  end: string | null;
  last_price: number | null;
  cumulative_return: number | null;
  realized_volatility_ann: number | null;
  sharpe: number | null;
  sortino: number | null;
  max_drawdown: number | null;
  calmar: number | null;
  risk_free_annual: number | null;
  beta: number | null;
  correlation_to_benchmark: number | null;
  benchmark: string;
  source: string | null;
};

export type MetricsResponse = {
  symbol: string;
  metrics: MetricsPayload;
  disclaimer?: string;
  error?: string;
};

export type TechnicalsLatest = {
  date: string;
  price: number;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  bb_mid: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  sma_20: number | null;
  sma_50: number | null;
  sma_200: number | null;
};

export type TechnicalsPoint = {
  date: string;
  price: number;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  sma_20?: number | null;
  sma_50?: number | null;
  sma_200?: number | null;
};

export type TechnicalsResponse = {
  symbol: string;
  bars: number;
  latest: TechnicalsLatest;
  series: TechnicalsPoint[];
  error?: string;
};

export type FundamentalsResponse = {
  ticker: string;
  ratios: Record<string, number | null>;
  raw: Record<string, number | null>;
  growth: Record<
    string,
    Array<{
      end_date: string;
      value: number | null;
      yoy: number | null;
      form: string | null;
    }>
  >;
  disclaimer?: string;
  error?: string;
};

export type MacroListResponse = {
  series: Record<string, string>;
};

export type MacroObservation = {
  date: string;
  value: number;
};

export type MacroSeriesResponse = {
  series_id: string;
  description: string | null;
  count: number;
  observations: MacroObservation[];
};

export type ValuationMetricKey = "pe" | "pb" | "ps" | "market_cap";

export type ValuationMetricStats = {
  avg: number | null;
  median: number | null;
  latest: number | null;
  count: number;
};

export type ValuationPoint = {
  date: string;
  price: number | null;
  pe: number | null;
  pb: number | null;
  ps: number | null;
  market_cap: number | null;
};

export type EarningsPoint = {
  date: string;
  eps: number | null;
  form: string | null;
  fy: number | null;
  fp: string | null;
};

export type ValuationHistoryResponse = {
  symbol: string;
  summary: {
    pe: ValuationMetricStats;
    pb: ValuationMetricStats;
    ps: ValuationMetricStats;
    market_cap: ValuationMetricStats;
    bars: number;
    start: string | null;
    end: string | null;
  };
  series: ValuationPoint[];
  earnings: EarningsPoint[];
  disclaimer?: string;
  error?: string;
};

export type ScreenRow = {
  ticker: string;
  name: string | null;
  sector: string | null;
  price: number | null;
  market_cap: number | null;
  pe: number | null;
  pb: number | null;
  ps: number | null;
  roe: number | null;
  net_margin: number | null;
  momentum_3m: number | null;
  momentum_12m: number | null;
  vol_ann: number | null;
  max_drawdown_1y: number | null;
  error: string | null;
  updated_at: string;
};

export type ScreenResponse = {
  rows: ScreenRow[];
  total: number;
  limit: number;
  offset: number;
  snapshot_count: number;
  sort: string;
  order: string;
};

export type ScreenRefreshResponse = {
  universe: string;
  processed: number;
  ok: number;
  failed: number;
  offset: number;
  limit: number | null;
  errors: Array<{ ticker: string; error: string }>;
};
