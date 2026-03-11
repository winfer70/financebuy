/**
 * useContextPopup — shared hook for right-click / click context menus.
 *
 * Encapsulates the state, open handler, and outside-click dismiss logic
 * that was duplicated in DashboardPage (heatmapPopup) and NewsPage
 * (tickerPopup).
 *
 * Returns:
 *   { popup, open, close }
 *   - popup: current popup state object or null.
 *   - open(data, event): show popup at click coordinates with arbitrary data.
 *   - close(): dismiss the popup.
 */

import { useState, useCallback, useEffect } from "react";

export default function useContextPopup() {
  const [popup, setPopup] = useState(null);

  /** Open the popup at the click coordinates with arbitrary payload data. */
  const open = useCallback((data, e) => {
    if (e) e.stopPropagation();
    setPopup({
      ...data,
      x: e ? e.clientX : 0,
      y: e ? e.clientY : 0,
    });
  }, []);

  /** Dismiss the popup. */
  const close = useCallback(() => setPopup(null), []);

  /* Auto-dismiss on any outside click while popup is visible. */
  useEffect(() => {
    if (!popup) return;
    const dismiss = () => setPopup(null);
    document.addEventListener("click", dismiss);
    return () => document.removeEventListener("click", dismiss);
  }, [popup]);

  return { popup, open, close };
}
