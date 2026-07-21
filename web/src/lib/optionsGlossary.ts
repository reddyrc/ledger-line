/** Plain-English explanations for options data points, used as hover tooltips. */
export const OPTION_TIPS = {
  spot: "Current price of the underlying stock (delayed).",
  maxPain:
    "Strike where option holders lose the most in total at expiration, based on open interest. Some traders expect price to drift toward it.",
  expMove:
    "Expected move: the market-implied price change through this expiration, approximated by the at-the-money straddle price (call mid + put mid).",
  range:
    "Implied price range through expiration: spot minus/plus the expected move.",
  pcrOi:
    "Put/Call ratio by open interest. Above 1 means more open put contracts than calls — often read as hedging or bearish positioning.",
  pcrVol:
    "Put/Call ratio by today's volume. Above 1 means puts traded more than calls today.",
  oi: "Open interest: number of contracts currently outstanding (updated overnight).",
  volume: "Contracts traded today.",
  callPutOi:
    "Total open interest across all call vs put strikes for this expiration.",
  callPutVol: "Total contracts traded today across all calls vs all puts.",
  atmIv:
    "At-the-money implied volatility: the option market's forecast of annualized volatility, averaged from the ATM call and put.",
  ivRank:
    "IV Rank: where today's ATM IV sits between its 1-year low (0%) and high (100%). High rank favors premium selling; low favors buying. Needs ~20 days of collected history.",
  ivPercentile:
    "IV Percentile: share of days in the past year with IV at or below today's. 80% means IV was lower 80% of the time.",
  earnings:
    "Days until the next scheduled earnings report. IV is usually inflated before the print and collapses after (IV crush).",
  mid: "Midpoint between bid and ask — a fair-value estimate for the contract.",
  bidAsk:
    "Best bid (what buyers pay) / best ask (what sellers want). A wide gap means poor liquidity and worse fills.",
  last: "Price of the most recent trade (may be stale for illiquid contracts).",
  iv: "Implied volatility of this contract: the annualized volatility that makes its model price match the market price.",
  hv20:
    "20-day historical (realized) volatility from daily closes, annualized. Compare to ATM IV to see if options look rich or cheap vs recent moves.",
  ivHvPremium:
    "ATM IV minus 20-day HV. Positive = implied > realized (options relatively expensive); negative favors buying premium.",
  totalOi: "Sum of call and put open interest for the snapshot expiration.",
  earningsCrush:
    "Change in ATM IV from before to after the earnings report (after − before). Negative = classic IV crush.",
  earningsActualMove:
    "Close-to-close stock return around the earnings date (pre-print close to next session close).",
  earningsExpectedMove:
    "One-session move implied by pre-earnings ATM IV: spot × IV × √(1/365). Rough proxy when the live straddle was not stored.",
  breakeven:
    "Stock price at expiration where this option breaks even: strike + premium for calls, strike − premium for puts.",
  session: "Today's low–high traded range for this contract's premium.",
  tradedLow: "Lowest daily premium traded over the selected period.",
  tradedHigh: "Highest daily premium traded over the selected period.",
  tradedLast: "Most recent daily closing premium in the selected period.",
  delta:
    "Delta: premium change per $1 move in the stock. Also a rough probability the option expires in the money.",
  gamma: "Gamma: how fast delta changes per $1 move in the stock.",
  theta: "Theta: premium lost per calendar day from time decay (negative for long options).",
  vega: "Vega: premium change per 1-point change in implied volatility.",
  rho: "Rho: premium change per 1-point change in interest rates.",
  edgeScore:
    "Heuristic 0–100 rank from mids, expected move, and max pain. Not a probability of profit.",
  creditDebit:
    "Credit = premium received to open (you keep it if the trade works). Debit = premium paid to open.",
  maxProfit: "Best-case profit per share at expiration.",
  maxLoss: "Worst-case loss per share at expiration (defined-risk spreads).",
  pop:
    "POP~: crude probability-of-profit proxy from credit vs spread width. Not a statistical probability.",
  volOi:
    "Today's volume divided by open interest. Above ~1 means more traded today than existed before — possible new positioning.",
  notional: "Approximate premium traded: volume × mid × 100.",
  uoaScore:
    "Heuristic 0–100 unusualness score blending volume/OI vs the chain median and premium notional.",
  netDelta: "Net delta of all legs: overall directional exposure per share.",
  netGamma: "Net gamma of all legs: how fast the position's delta shifts.",
  netTheta:
    "Net theta of all legs: daily time decay. Positive means the position earns from time passing.",
  netVega:
    "Net vega of all legs: sensitivity to IV changes. Negative benefits from falling IV.",
  contracts: "Number of spreads/contracts your budget covers at max loss per contract.",
  capitalUsed: "Capital at risk for the sized position (max loss × contracts).",
  netPremium: "Cash received (credit) or paid (debit) to open the sized position.",
  gainRisk: "Max gain divided by max loss for the sized position.",
} as const;
