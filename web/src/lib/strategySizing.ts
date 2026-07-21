/** Size an options strategy from a capital budget (USD). */

export type SizingInput = {
  family: string;
  creditOrDebit: number | null | undefined;
  maxProfitPerShare: number | null | undefined;
  maxLossPerShare: number | null | undefined;
  breakevens?: Array<number | null> | null;
  capital: number;
  multiplier?: number;
};

export type SizingResult = {
  contracts: number;
  capital: number;
  capitalUsed: number;
  capitalMode: "max_loss" | "debit" | "unavailable";
  maxProfit: number | null;
  maxLoss: number | null;
  netPremium: number | null;
  breakevens: number[];
  roiOnRisk: number | null;
};

export function sizeStrategy(input: SizingInput): SizingResult {
  const mult = input.multiplier ?? 100;
  const capital = Math.max(0, Number(input.capital) || 0);
  const maxLossShare = input.maxLossPerShare;
  const maxProfitShare = input.maxProfitPerShare;
  const premiumShare = input.creditOrDebit;
  const breakevens = (input.breakevens ?? []).filter(
    (v): v is number => v != null && Number.isFinite(v),
  );

  const empty: SizingResult = {
    contracts: 0,
    capital,
    capitalUsed: 0,
    capitalMode: "unavailable",
    maxProfit: null,
    maxLoss: null,
    netPremium: null,
    breakevens,
    roiOnRisk: null,
  };

  if (maxLossShare == null || maxLossShare <= 0 || capital <= 0) {
    return empty;
  }

  // Risk budget = max loss per contract (defined-risk spreads).
  // For debit spreads this equals the debit paid; for credits it's width - credit.
  const riskPerContract = maxLossShare * mult;
  const contracts = Math.floor(capital / riskPerContract);
  if (contracts <= 0) {
    return {
      ...empty,
      capitalMode: input.family === "debit" ? "debit" : "max_loss",
    };
  }

  const capitalUsed = contracts * riskPerContract;
  const maxLoss = contracts * riskPerContract;
  const maxProfit =
    maxProfitShare != null ? contracts * maxProfitShare * mult : null;
  const netPremium =
    premiumShare != null ? contracts * premiumShare * mult : null;
  const roiOnRisk =
    maxProfit != null && maxLoss > 0 ? maxProfit / maxLoss : null;

  return {
    contracts,
    capital,
    capitalUsed,
    capitalMode: input.family === "debit" ? "debit" : "max_loss",
    maxProfit,
    maxLoss,
    netPremium,
    breakevens,
    roiOnRisk,
  };
}
