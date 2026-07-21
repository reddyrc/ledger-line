import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./components/Layout";
import { HomePage } from "./pages/HomePage";
import { MacroPage } from "./pages/MacroPage";
import { OptionsPage } from "./pages/OptionsPage";
import { ScreenerPage } from "./pages/ScreenerPage";
import { SymbolPage } from "./pages/SymbolPage";
import { ThemeProvider } from "./theme/ThemeProvider";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<HomePage />} />
              <Route path="s/:symbol" element={<SymbolPage />} />
              <Route path="s/:symbol/options" element={<OptionsPage />} />
              <Route path="screen" element={<ScreenerPage />} />
              <Route path="macro" element={<MacroPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
