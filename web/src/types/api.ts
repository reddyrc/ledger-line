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
  filed?: string | null;
  report_datetime?: string | null;
  report_date?: string | null;
  anchor?: "report_date" | null;
  ret_1d?: number | null;
  ret_3d?: number | null;
  ret_5d?: number | null;
  ret_1m?: number | null;
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

export type ShortInterestPoint = {
  date: string;
  shares_short: number | null;
  shares_short_prior: number | null;
  change_pct: number | null;
  avg_daily_volume: number | null;
  days_to_cover: number | null;
};

export type ShortInterestLatest = {
  settlement_date: string;
  shares_short: number | null;
  shares_short_prior: number | null;
  change_pct: number | null;
  avg_daily_volume: number | null;
  days_to_cover: number | null;
  short_pct_float?: number | null;
  source?: string | null;
};

export type ShortInterestResponse = {
  symbol: string;
  latest: ShortInterestLatest | null;
  series: ShortInterestPoint[];
  yahoo?: {
    shares_short: number | null;
    short_pct_float: number | null;
    short_ratio: number | null;
    shares_short_prior_month: number | null;
  } | null;
  disclaimer?: string;
  error?: string;
};

export type PeerMetrics = {
  ticker: string | null;
  name: string | null;
  sector: string | null;
  industry?: string | null;
  price: number | null;
  pe: number | null;
  pb: number | null;
  ps: number | null;
  roe: number | null;
  net_margin: number | null;
  momentum_3m: number | null;
  momentum_12m: number | null;
  vol_ann: number | null;
  max_drawdown_1y: number | null;
  market_cap: number | null;
  custom?: boolean;
};

export type PeerSectorStat = {
  median: number | null;
  count: number;
  subject: number | null;
  percentile: number | null;
};

export type PeerComparisonResponse = {
  symbol: string;
  sector: string | null;
  industry?: string | null;
  peer_basis?: "industry" | "sector" | string | null;
  basis_label?: string | null;
  subject: PeerMetrics | null;
  peers: PeerMetrics[];
  sector_stats: Record<string, PeerSectorStat>;
  peer_count?: number;
  custom_tickers?: string[];
  fetched_at?: string | null;
  freshness?: "live" | "cached" | "stale" | "error" | string;
  stale?: boolean;
  warning?: string;
  disclaimer?: string;
  error?: string;
};

export type OptionContract = {
  contract_symbol: string | null;
  side: "call" | "put" | string;
  strike: number | null;
  bid: number | null;
  ask: number | null;
  last: number | null;
  mid: number | null;
  volume: number | null;
  open_interest: number | null;
  implied_volatility: number | null;
  day_low: number | null;
  day_high: number | null;
  in_the_money?: boolean | null;
  breakeven?: number | null;
  delta?: number | null;
  gamma?: number | null;
  theta?: number | null;
  vega?: number | null;
  rho?: number | null;
};

export type OptionsExpectedMove = {
  atm_strike: number | null;
  call_mid: number | null;
  put_mid: number | null;
  expected_move: number | null;
  expected_move_pct: number | null;
  price_low: number | null;
  price_high: number | null;
};

export type OptionsTotals = {
  call_oi: number | null;
  put_oi: number | null;
  call_volume: number | null;
  put_volume: number | null;
  pcr_oi: number | null;
  pcr_volume: number | null;
};

export type OptionsSummary = {
  max_pain: number | null;
  expected_move: OptionsExpectedMove;
  totals: OptionsTotals;
  atm_strike: number | null;
};

export type OptionsStrikeRow = {
  strike: number | null;
  call: OptionContract | null;
  put: OptionContract | null;
};

export type OptionsResponse = {
  symbol: string;
  expirations: string[];
  expiration: string | null;
  spot: number | null;
  summary: OptionsSummary | null;
  preview: OptionsStrikeRow[];
  calls: OptionContract[];
  puts: OptionContract[];
  fetched_at?: string | null;
  freshness?: string;
  stale?: boolean;
  warning?: string;
  disclaimer?: string;
  error?: string;
};

export type OptionsContractHistoryPoint = {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type OptionsContractResponse = {
  symbol: string;
  contract_symbol: string;
  period: string;
  side?: string | null;
  strike?: number | null;
  session_day_low?: number | null;
  session_day_high?: number | null;
  traded_low: number | null;
  traded_high: number | null;
  traded_last: number | null;
  series: OptionsContractHistoryPoint[];
  fetched_at?: string | null;
  freshness?: string;
  stale?: boolean;
  warning?: string;
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
