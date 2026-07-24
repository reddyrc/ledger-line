import type { EarningsPrimary } from "../api/client";

const STORAGE_KEY = "ledgerline.earningsPrimary";

export function isEarningsPrimary(value: unknown): value is EarningsPrimary {
  return value === "fmp" || value === "yfinance" || value === "finnhub";
}

export function readStoredEarningsPrimary(): EarningsPrimary | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isEarningsPrimary(raw) ? raw : null;
  } catch {
    return null;
  }
}

export function writeStoredEarningsPrimary(value: EarningsPrimary) {
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    /* ignore */
  }
}
