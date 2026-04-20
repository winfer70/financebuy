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

  /* ── Production build configuration (P6.8, P7.15, P7.16) ───────────── */
  build: {
    // P6.8 — Disable source maps in production to prevent exposing original
    // TypeScript/JSX source code to anyone with browser DevTools open.
    sourcemap: false,

    // P7.15 — Minify output for smaller bundles and faster load times.
    minify: "esbuild",

    // Target modern browsers to enable aggressive tree-shaking.
    target: "ES2020",

    rollupOptions: {
      output: {
        // P7.16 — Split heavy React runtime into a separate chunk so it
        // can be cached by the browser independently of application code,
        // reducing repeat-visit load times.
        manualChunks: {
          "react-vendor": ["react", "react-dom"],
        },
      },
    },
  },

  /* ── Development server ─────────────────────────────────────────────── */
  server: {
    port: 5173,
    proxy: {
      // Proxy /api/v1 requests to the FastAPI backend during development.
      // No path rewriting needed — FastAPI now mounts under /api/v1.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
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
