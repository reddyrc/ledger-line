import { useEffect, useId, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { ThemeToggle } from "./ThemeToggle";
import { TickerSearch } from "./TickerSearch";

const NAV_ITEMS = [
  { to: "/", label: "Explore", end: true },
  { to: "/strategies", label: "Strategies" },
  { to: "/earnings", label: "Earnings" },
  { to: "/mcap", label: "Mcap Δ" },
  { to: "/screen", label: "Screener" },
  { to: "/macro", label: "Macro" },
] as const;

export function Layout() {
  const location = useLocation();
  const isHome = location.pathname === "/";
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className={`app-shell${isHome ? " is-home" : ""}`}>
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">◈</span>
          <span className="brand-name">Ledgerline</span>
        </Link>
        <nav className="nav nav-desktop" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={"end" in item ? item.end : false}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        {!isHome && (
          <div className="topbar-search">
            <TickerSearch compact />
          </div>
        )}
        <div className="topbar-end">
          <ThemeToggle />
          <button
            type="button"
            className="nav-menu-btn"
            aria-expanded={menuOpen}
            aria-controls={menuId}
            onClick={() => setMenuOpen((o) => !o)}
          >
            {menuOpen ? "Close" : "Menu"}
          </button>
        </div>
      </header>
      {menuOpen && (
        <div
          className="nav-drawer-backdrop"
          aria-hidden
          onClick={() => setMenuOpen(false)}
        />
      )}
      <nav
        id={menuId}
        className={`nav-drawer${menuOpen ? " open" : ""}`}
        aria-label="Primary mobile"
        hidden={!menuOpen}
      >
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={"end" in item ? item.end : false}
            onClick={() => setMenuOpen(false)}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
      <main className="main">
        <Outlet />
      </main>
      <footer className="footer">
        Free unofficial feeds · Not for live trading decisions
      </footer>
    </div>
  );
}
