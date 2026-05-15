/**
 * QuickSellDrawer
 *
 * Slide-in side drawer that surfaces quick position details from the dashboard.
 * Selling is handled on the Portfolio Manager page; this drawer is read-only
 * and serves as a fast-access summary with a navigation hint.
 *
 * CSS class `.quick-sell-drawer` / `.quick-sell-drawer.open` lives in globals.js.
 */

import React from 'react';

/**
 * QuickSellDrawer: Fixed right-edge panel showing position summary
 *
 * @param {object|null} position  - Position object with ticker, name, quantity,
 *                                  purchase_price fields (null = no selection)
 * @param {boolean}     isOpen    - When true the drawer slides into view
 * @param {Function}    onClose   - Callback to dismiss the drawer
 * @returns {JSX.Element}
 */
const QuickSellDrawer = ({ position, isOpen, onClose }) => (
  <div className={`quick-sell-drawer${isOpen ? ' open' : ''}`}>
    {/* Header row */}
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
      <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--amber, #f59e0b)' }}>
        POSITION
      </span>
      <button
        onClick={onClose}
        style={{ background: 'none', border: 'none', color: 'var(--muted, #888)', cursor: 'pointer', fontSize: '18px' }}
      >
        ×
      </button>
    </div>

    {/* Position details — only rendered when a position is selected */}
    {position && (
      <div style={{ fontSize: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {/* Ticker symbol */}
        <div style={{ fontSize: '18px', fontWeight: 700 }}>{position.ticker}</div>

        {/* Company name */}
        <div style={{ color: 'var(--muted, #888)' }}>{position.name}</div>

        {/* Key position metrics */}
        <div style={{ marginTop: '8px' }}>
          <div>Qty: <strong>{position.quantity}</strong></div>
          <div>Avg Cost: <strong>${Number(position.purchase_price || 0).toFixed(2)}</strong></div>
        </div>

        {/* Sell navigation hint — selling is performed in the Portfolio Manager */}
        <div style={{
          marginTop: '16px', padding: '12px', background: 'var(--bg2)',
          borderRadius: '4px', fontSize: '11px', color: 'var(--muted, #888)', lineHeight: '1.5'
        }}>
          To sell this position, go to the Portfolio Manager page.
        </div>

        <button onClick={onClose} className="btn btn-outline" style={{ marginTop: '8px' }}>
          Close
        </button>
      </div>
    )}
  </div>
);

export default QuickSellDrawer;
export { QuickSellDrawer };
