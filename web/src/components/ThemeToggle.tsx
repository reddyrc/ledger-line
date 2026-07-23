import { useTheme } from "../theme/ThemeProvider";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="theme-toggle" role="group" aria-label="Color theme">
      <button
        type="button"
        className={theme === "dark" ? "active" : ""}
        aria-pressed={theme === "dark"}
        onClick={() => setTheme("dark")}
        title="Dark theme"
      >
        <span className="theme-toggle-full">Dark</span>
        <span className="theme-toggle-short" aria-hidden>
          ◐
        </span>
      </button>
      <button
        type="button"
        className={theme === "light" ? "active" : ""}
        aria-pressed={theme === "light"}
        onClick={() => setTheme("light")}
        title="Light theme"
      >
        <span className="theme-toggle-full">Light</span>
        <span className="theme-toggle-short" aria-hidden>
          ◑
        </span>
      </button>
    </div>
  );
}
