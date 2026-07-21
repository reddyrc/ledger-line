import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useOptions } from "../api/hooks";
import { IvEarningsChips, TermStructureTable } from "./IvEarningsChips";
import { fmtNum, fmtPct, fmtPrice } from "../lib/format";
import { OPTION_TIPS } from "../lib/optionsGlossary";

type Props = {
  symbol: string;
};

export function OptionsSummaryPanel({ symbol }: Props) {
  const [expiration, setExpiration] = useState<string | undefined>(undefined);
  const options = useOptions(symbol, expiration);

  useEffect(() => {
    setExpiration(undefined);
  }, [symbol]);

  useEffect(() => {
    if (!expiration && options.data?.expiration) {
      setExpiration(options.data.expiration);
    }
  }, [expiration, options.data?.expiration]);

  const data = options.data;
  const summary = data?.summary;
  const move = summary?.expected_move;
  const totals = summary?.totals;

  return (
    <div className="panel fade-in">
      <div className="panel-head">
        <h3>Options</h3>
        <div className="options-head-controls">
          <label className="options-exp-label">
            Exp
            <select
              className="options-exp-select mono"
              value={expiration ?? data?.expiration ?? ""}
              onChange={(e) => setExpiration(e.target.value || undefined)}
              disabled={!data?.expirations?.length}
            >
              {(data?.expirations ?? []).map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <Link className="btn-secondary options-full-link" to={`/s/${symbol}/options`}>
            Full options view
          </Link>
        </div>
      </div>

      {options.isLoading && <div className="chart-skeleton skeleton-block" />}

      {!options.isLoading && data?.error && !summary && (
        <p className="muted">{data.error}</p>
      )}

      {data?.warning && <p className="banner warn">{data.warning}</p>}

      {summary && (
        <>
          <div className="chip-row valuation-stats">
            <span className="chip" data-tip={OPTION_TIPS.spot}>
              Spot {fmtPrice(data?.spot)}
            </span>
            <span className="chip" data-tip={OPTION_TIPS.maxPain}>
              Max pain {fmtNum(summary.max_pain, 2)}
            </span>
            <span className="chip" data-tip={OPTION_TIPS.expMove}>
              Exp move{" "}
              {move?.expected_move == null
                ? "—"
                : `±${fmtNum(move.expected_move, 2)} (${fmtPct(move.expected_move_pct)})`}
            </span>
            <span className="chip" data-tip={OPTION_TIPS.range}>
              Range{" "}
              {move?.price_low == null || move?.price_high == null
                ? "—"
                : `${fmtNum(move.price_low, 2)}–${fmtNum(move.price_high, 2)}`}
            </span>
            <span className="chip" data-tip={OPTION_TIPS.pcrOi}>
              PCR OI {fmtNum(totals?.pcr_oi, 2)}
            </span>
            <span className="chip" data-tip={OPTION_TIPS.callPutOi}>
              Call OI {fmtNum(totals?.call_oi, 0)} · Put OI{" "}
              {fmtNum(totals?.put_oi, 0)}
            </span>
            <IvEarningsChips
              iv={data?.iv_context ?? summary.iv_context}
              daysToEarnings={
                data?.days_to_earnings ?? summary.days_to_earnings
              }
              nextEarnings={data?.next_earnings ?? summary.next_earnings}
            />
          </div>

          <TermStructureTable
            term={
              (data?.iv_context ?? summary.iv_context)?.term_structure ?? null
            }
          />

          {(data?.preview?.length ?? 0) > 0 && (
            <div className="table-scroll">
              <table className="data-table screener-table options-preview-table">
                <thead>
                  <tr>
                    <th>Call mid</th>
                    <th>Call OI</th>
                    <th>Strike</th>
                    <th>Put mid</th>
                    <th>Put OI</th>
                    <th>Day rng C/P</th>
                  </tr>
                </thead>
                <tbody>
                  {data!.preview.map((row) => {
                    const isAtm = row.strike === summary.atm_strike;
                    const isPain = row.strike === summary.max_pain;
                    return (
                      <tr
                        key={String(row.strike)}
                        className={
                          isPain
                            ? "options-row-pain"
                            : isAtm
                              ? "options-row-atm"
                              : undefined
                        }
                      >
                        <td className="mono">{fmtNum(row.call?.mid)}</td>
                        <td className="mono">
                          {fmtNum(row.call?.open_interest, 0)}
                        </td>
                        <td className="mono">
                          {fmtNum(row.strike, 2)}
                          {isPain ? " · pain" : isAtm ? " · ATM" : ""}
                        </td>
                        <td className="mono">{fmtNum(row.put?.mid)}</td>
                        <td className="mono">
                          {fmtNum(row.put?.open_interest, 0)}
                        </td>
                        <td className="mono muted small">
                          {row.call?.day_low != null && row.call?.day_high != null
                            ? `${fmtNum(row.call.day_low)}–${fmtNum(row.call.day_high)}`
                            : "—"}
                          {" / "}
                          {row.put?.day_low != null && row.put?.day_high != null
                            ? `${fmtNum(row.put.day_low)}–${fmtNum(row.put.day_high)}`
                            : "—"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {data?.disclaimer && <p className="disclaimer">{data.disclaimer}</p>}
    </div>
  );
}
