/**
 * Transaction Modal
 *
 * Modal form for creating new transactions (deposits, withdrawals, buy/sell orders).
 * Handles form state, validation, and submission with loading/error feedback.
 */

import { useState } from "react";
import { Ic } from "../common/Icons";

/**
 * TxModal: Modal for creating new transactions
 * Supports: deposit, withdrawal, buy (requires symbol), sell (requires symbol)
 */
export function TxModal({ onClose, onSubmit }) {
  const [form, setForm] = useState({
    account_id: "ACC-4821",
    transaction_type: "deposit",
    amount: "",
    currency: "USD",
    symbol: "",
  });
  const [loading, setLoading] = useState(false);
  const [err, setErr]         = useState("");
  const needsSymbol = ["buy","sell"].includes(form.transaction_type);

  const handle = async () => {
    if (!form.amount || isNaN(+form.amount) || +form.amount <= 0) return;
    setLoading(true);
    try {
      await onSubmit(form);
      onClose();
    } catch(e) {
      setErr(e.message || "Transaction failed");
    } finally {
      setLoading(false);
    }
  };

  const set = (k,v) => setForm(f=>({...f,[k]:v}));

  return (
    <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">NEW TRANSACTION</div>
          <button className="modal-close" onClick={onClose}><Ic.close/></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">Account ID</label>
            <input className="form-control" value={form.account_id} onChange={e=>set("account_id",e.target.value)}/>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Transaction Type</label>
              <select className="form-control" value={form.transaction_type} onChange={e=>set("transaction_type",e.target.value)}>
                <option value="deposit">DEPOSIT</option>
                <option value="withdrawal">WITHDRAWAL</option>
                <option value="buy">BUY</option>
                <option value="sell">SELL</option>
              </select>
            </div>
            <div className="form-field">
              <label className="form-label">Currency</label>
              <select className="form-control" value={form.currency} onChange={e=>set("currency",e.target.value)}>
                <option>USD</option><option>EUR</option><option>GBP</option>
              </select>
            </div>
          </div>
          {needsSymbol && (
            <div className="form-field">
              <label className="form-label">Symbol</label>
              <input className="form-control" placeholder="e.g. AAPL" value={form.symbol} onChange={e=>set("symbol",e.target.value.toUpperCase())}/>
            </div>
          )}
          <div className="form-field">
            <label className="form-label">Amount (USD)</label>
            <input className="form-control" type="number" min="0.01" step="0.01" placeholder="0.00"
              value={form.amount} onChange={e=>set("amount",e.target.value)}/>
            <span className="form-hint">Positive values only. Server validates on /transactions/create</span>
          </div>
        </div>
        {err && (
          <div style={{padding:"8px 20px",fontFamily:"var(--font-mono)",fontSize:11,color:"var(--red)",background:"rgba(240,68,56,0.06)",borderTop:"1px solid rgba(240,68,56,0.2)"}}>
            ⚠ {err}
          </div>
        )}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-amber" onClick={handle} disabled={loading}>
            {loading ? <span className="loading-pulse">SUBMITTING...</span> : "SUBMIT ORDER"}
          </button>
        </div>
      </div>
    </div>
  );
}
