/**
 * StaleDataBanner
 *
 * Displays an amber warning strip when market data is older than expected.
 * Shown above a data panel to alert the user that prices may be stale,
 * with an optional Refresh callback to trigger a re-fetch.
 */

import React from 'react';

/**
 * StaleDataBanner: Amber banner indicating potentially stale data
 *
 * @param {number}   lastUpdated - Unix timestamp (ms) of last successful data fetch
 * @param {Function} [onRefresh] - Optional callback; renders a "Refresh" link when provided
 * @returns {JSX.Element|null} Banner element, or null when lastUpdated is falsy
 */
const StaleDataBanner = ({ lastUpdated, onRefresh }) => {
  if (!lastUpdated) return null;
  const minsAgo = Math.floor((Date.now() - lastUpdated) / 60000);
  return (
    <div style={{
      borderLeft: '3px solid var(--amber, #f59e0b)',
      background: 'rgba(245,158,11,0.08)',
      padding: '6px 12px',
      fontSize: '11px',
      color: 'var(--amber, #f59e0b)',
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      marginBottom: '8px'
    }}>
      Data may be stale (last updated {minsAgo} min ago)
      {onRefresh && (
        /* Inline refresh trigger — avoids a full page navigation */
        <button onClick={onRefresh} style={{
          background: 'none', border: 'none', color: 'var(--amber, #f59e0b)',
          cursor: 'pointer', fontSize: '11px', textDecoration: 'underline', padding: 0
        }}>Refresh</button>
      )}
    </div>
  );
};

export default StaleDataBanner;
export { StaleDataBanner };
