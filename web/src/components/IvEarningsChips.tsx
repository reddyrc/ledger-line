import type { IvContext } from "../types/api";
import { fmtNum, fmtPct } from "../lib/format";
import { OPTION_TIPS } from "../lib/optionsGlossary";

/** Shared IV / earnings chips for options surfaces. */
export function IvEarningsChips({
  iv,
  daysToEarnings,
  nextEarnings,
}: {
  iv?: IvContext | null;
  daysToEarnings?: number | null;
  nextEarnings?: string | null;
}) {
  return (
    <>
      <span className="chip" data-tip={OPTION_TIPS.atmIv}>
        ATM IV {iv?.atm_iv == null ? "—" : fmtPct(iv.atm_iv)}
      </span>
      <span className="chip" data-tip={OPTION_TIPS.ivRank}>
        IVR{" "}
        {iv?.building_history
          ? `building (${iv.sample_count ?? 0})`
          : iv?.iv_rank_1y == null
            ? "—"
            : fmtPct(iv.iv_rank_1y)}
      </span>
      <span className="chip" data-tip={OPTION_TIPS.ivPercentile}>
        IVP{" "}
        {iv?.building_history
          ? "—"
          : iv?.iv_percentile_1y == null
            ? "—"
            : fmtPct(iv.iv_percentile_1y)}
      </span>
      <span className="chip" data-tip={OPTION_TIPS.earnings}>
        {daysToEarnings == null
          ? nextEarnings
            ? `Earnings ${String(nextEarnings).slice(0, 10)}`
            : "Earnings —"
          : daysToEarnings <= 0
            ? "Earnings today/soon"
            : `Earnings in ${daysToEarnings}d`}
      </span>
    </>
  );
}

export function TermStructureTable({
  term,
}: {
  term?: Array<{
    expiration: string | null;
    dte: number | null;
    atm_iv: number | null;
    expected_move?: number | null;
  }> | null;
}) {
  if (!term?.length) return null;
  return (
    <div className="table-scroll term-structure-table">
      <table className="data-table screener-table">
        <thead>
          <tr>
            <th title="Option expiration date.">Expiration</th>
            <th title="Days to expiration.">DTE</th>
            <th title={OPTION_TIPS.atmIv}>ATM IV</th>
            <th title={OPTION_TIPS.expMove}>Exp move</th>
          </tr>
        </thead>
        <tbody>
          {term.map((row) => (
            <tr key={String(row.expiration)}>
              <td className="mono">{row.expiration ?? "—"}</td>
              <td className="mono">{fmtNum(row.dte, 0)}</td>
              <td className="mono">{fmtPct(row.atm_iv)}</td>
              <td className="mono">{fmtNum(row.expected_move)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
