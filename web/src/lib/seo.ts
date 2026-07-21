import { useEffect } from "react";

const SITE = "Ledgerline";

const DEFAULT_TITLE = `${SITE} — Stock metrics, valuation history & options analytics`;
const DEFAULT_DESCRIPTION =
  "Free historical quant metrics for US stocks and ETFs: Sharpe, drawdown, beta, SEC EDGAR fundamentals, valuation history, options IV, and earnings analytics.";

function setMeta(selector: string, attr: string, value: string) {
  const el = document.head.querySelector<HTMLMetaElement>(selector);
  if (el) el.setAttribute(attr, value);
}

/**
 * Keep title/description in sync during client-side navigation.
 * First paint is handled server-side; this covers SPA route changes.
 */
export function useSeo(title?: string, description?: string) {
  useEffect(() => {
    const t = title ? `${title} | ${SITE}` : DEFAULT_TITLE;
    const d = description ?? DEFAULT_DESCRIPTION;
    document.title = t;
    setMeta('meta[name="description"]', "content", d);
    setMeta('meta[property="og:title"]', "content", t);
    setMeta('meta[property="og:description"]', "content", d);
    setMeta('meta[name="twitter:title"]', "content", t);
    setMeta('meta[name="twitter:description"]', "content", d);
  }, [title, description]);
}
