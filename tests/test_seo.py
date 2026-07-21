"""Tests for server-side SEO helpers."""

from finance_app.seo import (
    inject_meta,
    meta_for_path,
    robots_txt,
    sitemap_xml,
)

SAMPLE_INDEX = """<!doctype html>
<html>
  <head>
    <!-- seo:start (server replaces this block per route) -->
    <title>Default</title>
    <meta name="description" content="default" />
    <!-- seo:end -->
  </head>
  <body></body>
</html>
"""


def test_meta_for_symbol_page():
    meta = meta_for_path("/s/AAPL")
    assert "AAPL" in meta["title"]
    assert meta["robots"] == "index, follow"


def test_meta_for_options_page():
    meta = meta_for_path("/s/NVDA/options")
    assert "NVDA options" in meta["title"]
    assert meta["robots"] == "index, follow"


def test_meta_strategy_detail_noindex():
    meta = meta_for_path("/s/AAPL/strategies/abc123")
    assert meta["robots"].startswith("noindex")


def test_meta_bad_symbol_noindex():
    meta = meta_for_path("/s/<script>")
    assert meta["robots"].startswith("noindex")


def test_meta_unknown_route_noindex():
    meta = meta_for_path("/definitely/not/a/route")
    assert meta["robots"].startswith("noindex")


def test_meta_static_routes():
    for path in ("/", "/strategies", "/earnings", "/screen", "/macro"):
        meta = meta_for_path(path)
        assert meta["robots"] == "index, follow", path
        assert meta["title"]


def test_inject_meta_replaces_block():
    out = inject_meta(SAMPLE_INDEX, "/s/MSFT", "https://example.com")
    assert "MSFT stock metrics" in out
    assert "Default" not in out
    assert '<link rel="canonical" href="https://example.com/s/MSFT" />' in out
    # Block markers survive so a second pass could re-inject
    assert "<!-- seo:start -->" in out
    assert "<!-- seo:end -->" in out


def test_inject_meta_no_block_is_noop():
    html = "<html><head><title>x</title></head></html>"
    assert inject_meta(html, "/s/MSFT") == html


def test_robots_txt_includes_sitemap():
    txt = robots_txt("https://example.com")
    assert "Sitemap: https://example.com/sitemap.xml" in txt
    assert "Disallow: /api/" in txt


def test_sitemap_xml_lists_symbols_and_static():
    xml = sitemap_xml("https://example.com", ["AAPL", "bad sym", "QQQ"])
    assert "<loc>https://example.com/strategies</loc>" in xml
    assert "<loc>https://example.com/s/AAPL</loc>" in xml
    assert "<loc>https://example.com/s/AAPL/options</loc>" in xml
    assert "<loc>https://example.com/s/QQQ</loc>" in xml
    assert "bad sym" not in xml
