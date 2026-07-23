import type { PricePrimary } from "../api/client";

const STORAGE_KEY = "ledgerline.pricePrimary";

export function isPricePrimary(value: unknown): value is PricePrimary {
  return value === "tiingo" || value === "yfinance";
}

export function readStoredPricePrimary(): PricePrimary | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return isPricePrimary(raw) ? raw : null;
  } catch {
    return null;
  }
}

export function writeStoredPricePrimary(value: PricePrimary) {
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    /* ignore */
  }
}
