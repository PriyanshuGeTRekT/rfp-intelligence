/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // In development the API runs separately (`uv run rfp serve`); requests are proxied to it.
  const api = loadEnv(mode, ".", "RFP_").RFP_API_URL ?? "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { "/api": api, "/health": api },
    },
    build: {
      sourcemap: true,
      chunkSizeWarningLimit: 600,
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      globals: true,
    },
  };
});
