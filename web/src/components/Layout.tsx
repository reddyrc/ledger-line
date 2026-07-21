import { Link, NavLink, Outlet } from "react-router-dom";

import { ThemeToggle } from "./ThemeToggle";
import { TickerSearch } from "./TickerSearch";

export function Layout() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">◈</span>
          <span className="brand-name">Ledgerline</span>
        </Link>
        <nav className="nav">
          <NavLink to="/" end>
            Explore
          </NavLink>
          <NavLink to="/screen">Screener</NavLink>
          <NavLink to="/macro">Macro</NavLink>
        </nav>
        <div className="topbar-end">
          <ThemeToggle />
          <TickerSearch compact />
        </div>
      </header>
      <main className="main">
        <Outlet />
      </main>
      <footer className="footer">
        Free unofficial feeds · Not for live trading decisions
      </footer>
    </div>
  );
}
