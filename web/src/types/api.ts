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

export type TiingoMeta = {
  ticker?: string;
  name?: string | null;
  exchange?: string | null;
  description?: string | null;
  start_date?: string | null;
  end_date?: string | null;
};

export type TiingoNewsItem = {
  title?: string | null;
  url?: string | null;
  published?: string | null;
  source?: string | null;
  description?: string | null;
};

export type SymbolContextResponse = {
  symbol: string;
  configured: boolean;
  meta: TiingoMeta | null;
  news: TiingoNewsItem[];
  source?: string | null;
  freshness?: string | null;
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

export type FundamentalsGrowthPoint = {
  end_date: string;
  value: number | null;
  yoy: number | null;
  form: string | null;
};

export type BalanceSheetLine = {
  key: string;
  label: string;
  section: "assets" | "liabilities" | "equity" | string;
  value: number | null;
  yoy?: number | null;
};

export type BalanceSheetHistoryRow = {
  key: string;
  label: string;
  section: "assets" | "liabilities" | "equity" | string;
  values: Array<number | null>;
};

export type BalanceSheetPayload = {
  as_of: string | null;
  form: string | null;
  lines: BalanceSheetLine[];
  history: {
    periods: string[];
    rows: BalanceSheetHistoryRow[];
  };
};

export type FundamentalsResponse = {
  ticker: string;
  ratios: Record<string, number | null>;
  raw: Record<string, number | null>;
  growth: Record<string, FundamentalsGrowthPoint[]>;
  balance_sheet?: BalanceSheetPayload | null;
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
  index_returns?: Record<
    string,
    {
      ret_1d?: number | null;
      ret_3d?: number | null;
      ret_5d?: number | null;
      ret_1m?: number | null;
    }
  > | null;
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
  benchmarks?: string[];
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

export type IvTermPoint = {
  expiration: string | null;
  dte: number | null;
  atm_iv: number | null;
  expected_move?: number | null;
};

export type IvContext = {
  atm_iv: number | null;
  iv_rank_1y: number | null;
  iv_percentile_1y: number | null;
  sample_count?: number;
  building_history?: boolean;
  term_structure?: IvTermPoint[];
};

export type UoaRow = {
  contract_symbol: string | null;
  side: string;
  strike: number | null;
  expiration?: string | null;
  dte?: number | null;
  volume: number | null;
  open_interest: number | null;
  mid?: number | null;
  implied_volatility?: number | null;
  volume_oi?: number | null;
  premium_notional?: number | null;
  score?: number | null;
  vs_median_vol_oi?: number | null;
  day_low?: number | null;
  day_high?: number | null;
};

export type IvHistoryPoint = {
  date: string;
  expiration?: string | null;
  dte?: number | null;
  atm_iv: number | null;
  spot?: number | null;
  hv_10?: number | null;
  hv_20?: number | null;
  hv_30?: number | null;
  iv_hv_premium?: number | null;
  call_oi?: number | null;
  put_oi?: number | null;
  total_oi?: number | null;
  call_volume?: number | null;
  put_volume?: number | null;
  pcr_oi?: number | null;
  pcr_volume?: number | null;
};

export type EarningsCrushEvent = {
  report_datetime: string;
  report_date: string;
  reported_eps?: number | null;
  eps_estimate?: number | null;
  surprise_pct?: number | null;
  pre_close?: number | null;
  post_close?: number | null;
  actual_move_pct?: number | null;
  expected_move?: number | null;
  expected_move_pct?: number | null;
  hit_expected?: boolean | null;
  iv_before?: number | null;
  iv_after?: number | null;
  iv_crush?: number | null;
  iv_before_date?: string | null;
  iv_after_date?: string | null;
};

export type IvHistoryResponse = {
  symbol: string;
  start: string;
  end: string;
  expiration?: string | null;
  series: IvHistoryPoint[];
  sample_count: number;
  building_history?: boolean;
  latest?: {
    atm_iv?: number | null;
    hv_20?: number | null;
    iv_hv_premium?: number | null;
    pcr_oi?: number | null;
    total_oi?: number | null;
    date?: string | null;
  };
  earnings_history?: EarningsCrushEvent[];
  disclaimer?: string;
  error?: string;
};

export type RollingPoint = {
  date: string;
  return: number | null;
  cumulative_return: number | null;
  rolling_vol_ann: number | null;
  rolling_sharpe?: number | null;
};

export type RollingResponse = {
  symbol: string;
  window: number;
  series: RollingPoint[];
};

export type OptionsSummary = {
  max_pain: number | null;
  expected_move: OptionsExpectedMove;
  totals: OptionsTotals;
  atm_strike: number | null;
  iv_context?: IvContext | null;
  days_to_earnings?: number | null;
  next_earnings?: string | null;
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
  uoa?: UoaRow[];
  iv_context?: IvContext | null;
  days_to_earnings?: number | null;
  next_earnings?: string | null;
  eps_estimate?: number | null;
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

export type StrategyLeg = {
  action: string;
  right: string;
  strike: number | null;
  mid: number | null;
  bid: number | null;
  ask: number | null;
  last: number | null;
  implied_volatility: number | null;
  contract_symbol: string | null;
  open_interest?: number | null;
  volume?: number | null;
};

export type StrategyMetrics = {
  credit_or_debit: number | null;
  max_profit: number | null;
  max_loss: number | null;
  pop_proxy: number | null;
  edge_score: number | null;
  spot: number | null;
  expected_move: number | null;
  max_pain: number | null;
  breakevens?: number[] | null;
  severity?: string | null;
  residual?: number | null;
  notes: string[];
  liquidity?: {
    min_oi?: number | null;
    min_volume?: number | null;
    max_spread_pct?: number | null;
    ok?: boolean;
  } | null;
  days_to_earnings?: number | null;
};

export type StrategyIdea = {
  id: string;
  symbol: string;
  family: "credit" | "debit" | "mispricing" | string;
  kind: string;
  title: string;
  expiration: string;
  legs: StrategyLeg[];
  metrics: StrategyMetrics;
  disclaimer?: string;
};

export type StrategiesResponse = {
  symbol: string;
  expiration: string | null;
  expirations: string[];
  spot: number | null;
  summary?: {
    max_pain: number | null;
    expected_move: number | null;
    atm_strike?: number | null;
  };
  ideas: StrategyIdea[];
  iv_context?: IvContext | null;
  days_to_earnings?: number | null;
  next_earnings?: string | null;
  fetched_at?: string | null;
  freshness?: string;
  stale?: boolean;
  disclaimer?: string;
  error?: string;
};

export type StrategyGreeks = {
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  rho?: number | null;
  source?: string;
  legs?: Array<{
    contract_symbol?: string | null;
    action?: string;
    right?: string;
    strike?: number | null;
    delta?: number | null;
    gamma?: number | null;
    theta?: number | null;
    vega?: number | null;
    rho?: number | null;
    model_price?: number | null;
  }>;
};

export type ScenarioGrid = {
  horizon?: string;
  note?: string;
  spot_shocks?: number[];
  iv_shocks?: number[];
  grid: Array<{
    spot_pct: number;
    iv_pct: number;
    pnl: number | null;
  }>;
};

export type StrategyDetailResponse = {
  symbol: string;
  expiration?: string | null;
  idea: StrategyIdea | null;
  payoff: Array<{ spot: number | null; pnl: number | null }>;
  greeks?: StrategyGreeks | null;
  scenarios?: ScenarioGrid | null;
  days_to_earnings?: number | null;
  next_earnings?: string | null;
  disclaimer?: string;
  error?: string;
};

export type StrategiesScanResponse = {
  symbols: string[];
  ideas: StrategyIdea[];
  errors: Array<{ symbol: string; error: string }>;
  disclaimer?: string;
};

export type EarningsCalendarEvent = {
  symbol: string;
  report_datetime: string;
  reported_eps: number | null;
  eps_estimate: number | null;
  surprise_pct: number | null;
  days_to_earnings: number | null;
  session?: "BMO" | "AMC" | null;
  last_surprise_pct?: number | null;
  spot?: number | null;
  avg_abs_move_1d?: number | null;
  avg_move_n?: number | null;
  revenue_estimate?: number | null;
  revenue_yoy?: number | null;
  eps_estimate_avg?: number | null;
  eps_revisions_up_30d?: number | null;
  eps_revisions_down_30d?: number | null;
  eps_revision_net_30d?: number | null;
  eps_trend_delta_30d?: number | null;
  atm_iv?: number | null;
  iv_rank_1y?: number | null;
  expected_move?: number | null;
  expected_move_pct?: number | null;
  avg_iv_crush?: number | null;
};

export type EarningsCalendarResponse = {
  from: string;
  to: string;
  symbols: string[];
  events: EarningsCalendarEvent[];
  earnings_primary?: "fmp" | "yfinance";
  source?: "fmp" | "yfinance" | string;
  fmp_configured?: boolean;
  disclaimer?: string;
};

export type UoaResponse = {
  symbol: string;
  expiration: string | null;
  rows: UoaRow[];
  freshness?: string;
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
