import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useEarningsCalendar } from "../api/hooks";
import { fmtCompact, fmtNum, fmtPct, fmtPrice, normalizeTicker } from "../lib/format";
import { useSeo } from "../lib/seo";
import type { EarningsCalendarEvent } from "../types/api";

const DEFAULT =
  "SPY,QQQ,IWM,AAPL,MSFT,NVDA,AMZN,META,GOOGL,TSLA";

/** Yahoo Surprise(%) is percent points (3.5 = +3.5%), not a decimal fraction. */
function fmtSurprise(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
}

function signedClass(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n) || n === 0) return "";
  return n > 0 ? "pos" : "neg";
}

function formatReport(iso: string): string {
  const s = String(iso);
  return s.length >= 16 ? s.slice(0, 16).replace("T", " ") : s.slice(0, 10);
}

function revisionLabel(ev: EarningsCalendarEvent): string {
  const net = ev.eps_revision_net_30d;
  if (net == null) return "—";
  const up = ev.eps_revisions_up_30d ?? 0;
  const down = ev.eps_revisions_down_30d ?? 0;
  const sign = net > 0 ? "+" : "";
  return `${sign}${fmtNum(net, 0)} (${fmtNum(up, 0)}↑/${fmtNum(down, 0)}↓)`;
}

export function EarningsPage() {
  useSeo(
    "Earnings calendar with estimates & expected moves",
    "Upcoming earnings with EPS and revenue estimates, revision trends, historical post-earnings moves, implied volatility, and expected move context.",
  );
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
            Upcoming reports with estimates, typical post-print moves, and cached
            options context. Times may be estimates.
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
          <button className="btn-secondary" type="submit" disabled={cal.isFetching}>
            {cal.isFetching ? "Loading…" : "Load"}
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
            <table className="data-table screener-table earnings-cal-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Report</th>
                  <th title="Calendar days until the report.">Days</th>
                  <th title="Latest close from local price history.">Spot</th>
                  <th title="Consensus EPS estimate for this report.">Est EPS</th>
                  <th title="Reported EPS vs estimate (Yahoo Surprise %).">
                    Surprise
                  </th>
                  <th title="Surprise % on the prior earnings report.">
                    Last surpr
                  </th>
                  <th title="Consensus revenue estimate for the current quarter (0q).">
                    Rev est
                  </th>
                  <th title="Estimated revenue growth vs year-ago quarter.">
                    Rev YoY
                  </th>
                  <th title="Net EPS estimate revisions in the last 30 days (up − down).">
                    Rev 30d
                  </th>
                  <th title="Average absolute next-day return after past earnings reports.">
                    Avg +1d
                  </th>
                  <th title="ATM straddle expected move from cached options chain, when available.">
                    Exp move
                  </th>
                  <th title="Latest ATM implied volatility from IV snapshots / chain cache.">
                    ATM IV
                  </th>
                  <th title="IV Rank (1y) from collected ATM IV history.">IVR</th>
                  <th title="Average IV crush (after − before) around past earnings when snapshots exist.">
                    Avg crush
                  </th>
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
                      {formatReport(ev.report_datetime)}
                    </td>
                    <td className="mono">{fmtNum(ev.days_to_earnings, 0)}</td>
                    <td className="mono">{fmtPrice(ev.spot)}</td>
                    <td className="mono">
                      {fmtNum(ev.eps_estimate ?? ev.eps_estimate_avg)}
                    </td>
                    <td className={`mono ${signedClass(ev.surprise_pct)}`}>
                      {fmtSurprise(ev.surprise_pct)}
                    </td>
                    <td className={`mono ${signedClass(ev.last_surprise_pct)}`}>
                      {fmtSurprise(ev.last_surprise_pct)}
                    </td>
                    <td className="mono">{fmtCompact(ev.revenue_estimate)}</td>
                    <td className={`mono ${signedClass(ev.revenue_yoy)}`}>
                      {fmtPct(ev.revenue_yoy, 1)}
                    </td>
                    <td
                      className={`mono ${signedClass(ev.eps_revision_net_30d)}`}
                      title={
                        ev.eps_trend_delta_30d != null
                          ? `EPS trend Δ 30d: ${fmtNum(ev.eps_trend_delta_30d, 3)}`
                          : undefined
                      }
                    >
                      {revisionLabel(ev)}
                    </td>
                    <td className="mono">
                      {ev.avg_abs_move_1d != null
                        ? `±${fmtPct(ev.avg_abs_move_1d, 1)}`
                        : "—"}
                      {ev.avg_move_n != null && ev.avg_move_n > 0 && (
                        <span className="muted small"> n={ev.avg_move_n}</span>
                      )}
                    </td>
                    <td className="mono">
                      {ev.expected_move_pct != null
                        ? `±${fmtPct(ev.expected_move_pct, 1)}`
                        : ev.expected_move != null
                          ? `±${fmtPrice(ev.expected_move)}`
                          : "—"}
                    </td>
                    <td className="mono">
                      {ev.atm_iv != null ? fmtPct(ev.atm_iv, 1) : "—"}
                    </td>
                    <td className="mono">
                      {ev.iv_rank_1y != null
                        ? fmtPct(ev.iv_rank_1y, 0)
                        : "—"}
                    </td>
                    <td className={`mono ${signedClass(ev.avg_iv_crush)}`}>
                      {ev.avg_iv_crush != null
                        ? fmtPct(ev.avg_iv_crush, 1)
                        : "—"}
                    </td>
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
