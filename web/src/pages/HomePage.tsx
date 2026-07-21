import { Link } from "react-router-dom";

import { TickerSearch } from "../components/TickerSearch";

const SUGGESTIONS = ["INTC", "AAPL", "MSFT", "NVDA", "SPY", "QQQ"];

export function HomePage() {
  return (
    <section className="hero">
      <div className="hero-atmosphere" aria-hidden />
      <div className="hero-content">
        <p className="eyebrow">Historical quant metrics</p>
        <h1 className="hero-brand">Ledgerline</h1>
        <p className="hero-lede">
          Free-market history turned into Sharpe, drawdown, beta, and EDGAR
          fundamentals — look up any US equity or ETF.
        </p>
        <TickerSearch autofocus />
        <div className="suggest-row">
          {SUGGESTIONS.map((t) => (
            <Link key={t} to={`/s/${t}`} className="suggest">
              {t}
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
