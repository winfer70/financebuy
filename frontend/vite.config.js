/**
 * vite.config.js — Vite build + test configuration for TickerTap frontend.
 *
 * Includes Vitest configuration for unit testing with jsdom so React
 * components can be tested without a real browser.
 *
 * Run tests: npm test
 * Run tests with coverage: npm run test:coverage
 */

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],

  /* ── Development server ─────────────────────────────────────────────── */
  server: {
    port: 5173,
    proxy: {
      // Proxy /api requests to the FastAPI backend during development
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },

  /* ── Vitest test configuration ──────────────────────────────────────── */
  test: {
    // Use jsdom as the browser-like environment for React component tests
    environment: "jsdom",

    // Automatically set up @testing-library/jest-dom matchers
    setupFiles: ["./src/__tests__/setup.js"],

    // Include all test files
    include: ["src/**/*.{test,spec}.{js,jsx}"],

    // Global test utilities available without imports
    globals: true,

    // Coverage configuration (run with --coverage flag)
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      exclude: [
        "node_modules/",
        "src/__tests__/setup.js",
        "src/styles/globals.js",
      ],
      thresholds: {
        lines:      70,
        functions:  70,
        branches:   60,
        statements: 70,
      },
    },
  },
});
