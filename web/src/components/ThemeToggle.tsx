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
        Dark
      </button>
      <button
        type="button"
        className={theme === "light" ? "active" : ""}
        aria-pressed={theme === "light"}
        onClick={() => setTheme("light")}
        title="Light theme"
      >
        Light
      </button>
    </div>
  );
}
