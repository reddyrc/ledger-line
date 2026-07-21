import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    // SEO endpoints live on the FastAPI backend; forward them in dev
    proxy: {
      "/sitemap.xml": "http://localhost:8000",
      "/robots.txt": "http://localhost:8000",
    },
  },
  preview: {
    port: 5180,
    strictPort: true,
  },
});
