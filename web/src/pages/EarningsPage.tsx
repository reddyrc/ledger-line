import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useEarningsCalendar } from "../api/hooks";
import { fmtNum, normalizeTicker } from "../lib/format";

const DEFAULT =
  "SPY,QQQ,IWM,AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA";

export function EarningsPage() {
  const [draft, setDraft] = useState(DEFAULT);
  const [symbols, setSymbols] = useState(() =>
    DEFAULT.split(",")
      .map((t) => normalizeTicker(t))
      .filter(Boolean),
  );
  const [wantRefresh, setWantRefresh] = useState(false);

  const cal = useEarningsCalendar(
    { symbols, refresh: wantRefresh },
    symbols.length > 0,
  );

  useEffect(() => {
    if (wantRefresh && !cal.isFetching && cal.isFetched) {
      setWantRefresh(false);
    }
  }, [wantRefresh, cal.isFetching, cal.isFetched]);

  const events = useMemo(() => cal.data?.events ?? [], [cal.data?.events]);

  return (
    <div className="earnings-page fade-in">
      <div className="symbol-header">
        <div>
          <h1 className="symbol-title">Earnings calendar</h1>
          <p className="muted small">
            Upcoming report dates from Yahoo (may be estimates).
          </p>
        </div>
      </div>

      <div className="panel">
        <form
          className="strategy-watch-form"
          onSubmit={(e) => {
            e.preventDefault();
            const next = draft
              .split(/[\s,]+/)
              .map((t) => normalizeTicker(t))
              .filter(Boolean)
              .slice(0, 15);
            setSymbols(next);
            setWantRefresh(true);
          }}
        >
          <input
            className="strategy-watch-input mono"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            aria-label="Earnings watchlist"
          />
          <button className="btn-secondary" type="submit">
            Load
          </button>
        </form>
      </div>

      {cal.isLoading && <div className="chart-skeleton skeleton-block" />}

      {!cal.isLoading && events.length === 0 && (
        <div className="empty-panel">
          No earnings events in range. Try Load to refresh from Yahoo.
        </div>
      )}

      {events.length > 0 && (
        <div className="panel">
          <div className="table-scroll">
            <table className="data-table screener-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Report</th>
                  <th>Days</th>
                  <th>Est. EPS</th>
                  <th>Reported</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <tr key={`${ev.symbol}-${ev.report_datetime}`}>
                    <td className="mono">
                      <Link className="ticker-link" to={`/s/${ev.symbol}`}>
                        {ev.symbol}
                      </Link>
                    </td>
                    <td className="mono small">
                      {String(ev.report_datetime).slice(0, 16)}
                    </td>
                    <td className="mono">{fmtNum(ev.days_to_earnings, 0)}</td>
                    <td className="mono">{fmtNum(ev.eps_estimate)}</td>
                    <td className="mono">{fmtNum(ev.reported_eps)}</td>
                    <td>
                      <Link
                        className="muted small"
                        to={`/s/${ev.symbol}/options`}
                      >
                        Options
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {cal.data?.disclaimer && (
            <p className="disclaimer">{cal.data.disclaimer}</p>
          )}
        </div>
      )}
    </div>
  );
}
