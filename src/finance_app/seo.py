"""Server-side SEO: per-route meta tags, robots.txt, and sitemap.xml for the SPA."""

from __future__ import annotations

import html
import re
from typing import Optional

SEO_BLOCK_RE = re.compile(
    r"<!-- seo:start.*?-->.*?<!-- seo:end -->", re.DOTALL
)

SITE_NAME = "Ledgerline"
DEFAULT_TITLE = (
    "Ledgerline — Stock metrics, valuation history & options analytics"
)
DEFAULT_DESCRIPTION = (
    "Free historical quant metrics for US stocks and ETFs: Sharpe, drawdown, "
    "beta, SEC EDGAR fundamentals, valuation history, options IV, and "
    "earnings analytics."
)

# Client routes that should appear in the sitemap
STATIC_ROUTES = ["/", "/strategies", "/earnings", "/screen", "/macro"]

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _clean_symbol(raw: str) -> Optional[str]:
    sym = raw.upper().strip()
    return sym if _SYMBOL_RE.match(sym) else None


def meta_for_path(path: str) -> dict[str, str]:
    """Title/description/robots for a client route path (no query string)."""
    path = "/" + path.strip("/")

    parts = [p for p in path.split("/") if p]
    if not parts:
        return {
            "title": DEFAULT_TITLE,
            "description": DEFAULT_DESCRIPTION,
            "robots": "index, follow",
        }

    if parts[0] == "s" and len(parts) >= 2:
        sym = _clean_symbol(parts[1])
        if sym is None:
            return {
                "title": DEFAULT_TITLE,
                "description": DEFAULT_DESCRIPTION,
                "robots": "noindex, follow",
            }
        if len(parts) == 2:
            return {
                "title": f"{sym} stock metrics, valuation history & fundamentals | {SITE_NAME}",
                "description": (
                    f"{sym} historical performance: Sharpe, volatility, drawdown, "
                    f"beta, P/E and valuation history, balance sheet from SEC EDGAR, "
                    f"short interest, and post-earnings moves."
                ),
                "robots": "index, follow",
            }
        if len(parts) == 3 and parts[2] == "options":
            return {
                "title": f"{sym} options chain, implied volatility & strategy ideas | {SITE_NAME}",
                "description": (
                    f"{sym} options analytics: chain by expiration, ATM IV with IV "
                    f"rank, expected move, max pain, unusual activity, IV vs HV "
                    f"history, and heuristic strategy ideas."
                ),
                "robots": "index, follow",
            }
        # Ephemeral strategy detail pages: keep crawlers out
        return {
            "title": f"{sym} option strategy detail | {SITE_NAME}",
            "description": DEFAULT_DESCRIPTION,
            "robots": "noindex, follow",
        }

    known = {
        "strategies": (
            f"Options strategy screener | {SITE_NAME}",
            "Scan a watchlist for credit spreads, iron condors, and covered "
            "calls with liquidity filters, POP estimates, and earnings-risk "
            "annotations.",
        ),
        "earnings": (
            f"Earnings calendar with estimates & expected moves | {SITE_NAME}",
            "Upcoming earnings with EPS and revenue estimates, revision "
            "trends, historical post-earnings moves, implied volatility, and "
            "expected move context.",
        ),
        "screen": (
            f"Stock screener — value & momentum filters | {SITE_NAME}",
            "Screen US stocks by P/E, P/B, P/S, ROE, momentum, volatility, "
            "and drawdown using free fundamental and price data.",
        ),
        "macro": (
            f"Macro dashboard — rates & economic series | {SITE_NAME}",
            "FRED macro series alongside equity metrics: Treasury yields, "
            "inflation, and more.",
        ),
    }
    if parts[0] in known and len(parts) == 1:
        title, desc = known[parts[0]]
        return {"title": title, "description": desc, "robots": "index, follow"}

    return {
        "title": DEFAULT_TITLE,
        "description": DEFAULT_DESCRIPTION,
        "robots": "noindex, follow",
    }


def render_seo_block(path: str, base_url: str = "") -> str:
    meta = meta_for_path(path)
    title = html.escape(meta["title"])
    desc = html.escape(meta["description"])
    robots = meta["robots"]

    canonical = ""
    og_url = ""
    if base_url:
        url = base_url.rstrip("/") + "/" + path.strip("/")
        url = url.rstrip("/") or base_url.rstrip("/")
        canonical = f'\n    <link rel="canonical" href="{html.escape(url)}" />'
        og_url = f'\n    <meta property="og:url" content="{html.escape(url)}" />'

    return f"""<!-- seo:start -->
    <title>{title}</title>
    <meta name="description" content="{desc}" />
    <meta name="robots" content="{robots}" />{canonical}
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="{SITE_NAME}" />{og_url}
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{desc}" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="{title}" />
    <meta name="twitter:description" content="{desc}" />
    <!-- seo:end -->"""


def inject_meta(index_html: str, path: str, base_url: str = "") -> str:
    """Replace the seo:start/seo:end block in index.html for this route."""
    block = render_seo_block(path, base_url)
    replaced, n = SEO_BLOCK_RE.subn(block, index_html, count=1)
    return replaced if n else index_html


def robots_txt(base_url: str = "") -> str:
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /api/",
        "Disallow: /docs",
        "Disallow: /redoc",
        "Disallow: /openapi.json",
    ]
    if base_url:
        lines.append(f"Sitemap: {base_url.rstrip('/')}/sitemap.xml")
    return "\n".join(lines) + "\n"


def sitemap_xml(base_url: str, symbols: list[str]) -> str:
    base = base_url.rstrip("/")
    urls: list[str] = [f"{base}{r}".rstrip("/") or base for r in STATIC_ROUTES]
    for raw in symbols:
        sym = _clean_symbol(str(raw))
        if not sym:
            continue
        urls.append(f"{base}/s/{sym}")
        urls.append(f"{base}/s/{sym}/options")

    entries = "\n".join(
        f"  <url><loc>{html.escape(u)}</loc></url>" for u in dict.fromkeys(urls)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n"
        "</urlset>\n"
    )
