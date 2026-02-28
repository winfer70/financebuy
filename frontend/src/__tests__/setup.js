/**
 * __tests__/setup.js — Vitest global test setup for TickerTap frontend.
 *
 * Extends Vitest's expect with @testing-library/jest-dom matchers
 * (toBeInTheDocument, toHaveTextContent, etc.) so they are available
 * in every test file without explicit imports.
 */
import "@testing-library/jest-dom";
