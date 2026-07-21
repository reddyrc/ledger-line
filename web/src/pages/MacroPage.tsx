import { useMemo, useState } from "react";

import { useBootstrapMacro, useMacroList, useMacroSeries } from "../api/hooks";
import { MacroChart } from "../components/MacroChart";
import { useSeo } from "../lib/seo";

export function MacroPage() {
  useSeo(
    "Macro dashboard — rates & economic series",
    "FRED macro series alongside equity metrics: Treasury yields, inflation, and more.",
  );
  const list = useMacroList();
  const seriesMap = list.data?.series ?? {};
  const ids = useMemo(() => Object.keys(seriesMap).sort(), [seriesMap]);
  const [selected, setSelected] = useState("VIXCLS");
  const seriesId = ids.includes(selected) ? selected : ids[0] ?? "VIXCLS";
  const series = useMacroSeries(seriesId);
  const bootstrap = useBootstrapMacro();

  return (
    <div className="macro-page fade-in">
      <div className="symbol-header">
        <div>
          <h1 className="page-title">Macro</h1>
          <p className="muted">
            FRED series for rates, inflation, VIX, and recession markers.
          </p>
        </div>
        <button
          type="button"
          className="btn-secondary"
          disabled={bootstrap.isPending}
          onClick={() => bootstrap.mutate()}
        >
          {bootstrap.isPending ? "Bootstrapping…" : "Bootstrap defaults"}
        </button>
      </div>

      {bootstrap.isSuccess && (
        <div className="banner ok">
          Cached {Object.keys(bootstrap.data.ingested).length} series.
        </div>
      )}
      {bootstrap.isError && (
        <div className="banner error">
          {(bootstrap.error as Error).message}
        </div>
      )}

      <div className="macro-layout">
        <aside className="series-list panel">
          <h3>Series</h3>
          {list.isLoading && <p className="muted">Loading…</p>}
          <ul>
            {ids.map((id) => (
              <li key={id}>
                <button
                  type="button"
                  className={id === seriesId ? "active" : ""}
                  onClick={() => setSelected(id)}
                >
                  <span className="mono">{id}</span>
                  <span className="muted small">{seriesMap[id]}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
        <div className="panel grow">
          <div className="panel-head">
            <h3 className="mono">{seriesId}</h3>
            <span className="muted small">
              {seriesMap[seriesId] ?? series.data?.description ?? ""}
            </span>
          </div>
          {series.isLoading ? (
            <div className="chart-skeleton skeleton-block" />
          ) : series.isError ? (
            <div className="banner error">
              {(series.error as Error).message}
            </div>
          ) : (
            <MacroChart
              seriesId={seriesId}
              observations={series.data?.observations ?? []}
            />
          )}
          {series.data && (
            <p className="muted small">
              {series.data.count.toLocaleString()} observations
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
