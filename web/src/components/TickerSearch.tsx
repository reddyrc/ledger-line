import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { normalizeTicker } from "../lib/format";

type Props = {
  compact?: boolean;
  autofocus?: boolean;
};

export function TickerSearch({ compact, autofocus }: Props) {
  const [value, setValue] = useState("");
  const navigate = useNavigate();

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const t = normalizeTicker(value);
    if (!t) return;
    navigate(`/s/${t}`);
    setValue("");
  }

  return (
    <form className={compact ? "search search-compact" : "search"} onSubmit={onSubmit}>
      <label className="sr-only" htmlFor={compact ? "ticker-nav" : "ticker-hero"}>
        Ticker symbol
      </label>
      <input
        id={compact ? "ticker-nav" : "ticker-hero"}
        value={value}
        onChange={(e) => setValue(e.target.value.toUpperCase())}
        placeholder={compact ? "Ticker…" : "Enter a ticker (e.g. INTC)"}
        autoFocus={autofocus}
        autoComplete="off"
        spellCheck={false}
      />
      <button type="submit">Open</button>
    </form>
  );
}
