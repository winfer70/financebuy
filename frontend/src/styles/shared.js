/**
 * Shared Style Objects — reusable inline-style constants extracted from
 * page-level duplicates (PortfolioManagerPage, WatchlistPage, etc.).
 *
 * Import specific constants to replace inline object literals that were
 * previously copy-pasted between pages.
 */

/**
 * Modal backdrop / overlay style — fixed fullscreen dark overlay with
 * centred content.  Used by PortfolioManagerPage, WatchlistPage, and any
 * future modal dialogs.
 *
 * Usage:
 *   <div className="modal-overlay" style={MODAL_BACKDROP}
 *        onClick={e => e.target === e.currentTarget && onClose()}>
 */
export const MODAL_BACKDROP = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,.65)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};
