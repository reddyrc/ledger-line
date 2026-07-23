import type { TiingoNewsItem } from "../types/api";

type Props = {
  news: TiingoNewsItem[];
  loading?: boolean;
  configured?: boolean;
};

export function TiingoNewsPanel({ news, loading, configured }: Props) {
  if (configured === false) {
    return null;
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>News</h3>
        <span className="muted small">Tiingo</span>
      </div>
      {loading && <div className="chart-skeleton skeleton-block" />}
      {!loading && news.length === 0 && (
        <div className="empty-panel">No recent headlines.</div>
      )}
      {!loading && news.length > 0 && (
        <ul className="tiingo-news-list">
          {news.map((item, i) => {
            const key = `${item.url ?? item.title ?? i}`;
            const title = item.title?.trim() || "Untitled";
            const when = item.published
              ? String(item.published).slice(0, 10)
              : null;
            return (
              <li key={key} className="tiingo-news-item">
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="tiingo-news-link"
                  >
                    {title}
                  </a>
                ) : (
                  <span>{title}</span>
                )}
                <div className="muted small tiingo-news-meta">
                  {[item.source, when].filter(Boolean).join(" · ")}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
