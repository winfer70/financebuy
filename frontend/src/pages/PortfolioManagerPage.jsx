/**
 * PortfolioManagerPage.jsx
 *
 * Full-featured portfolio manager: create named portfolios, track custom
 * positions with live prices and P&L, import via CSV, and sell/modify.
 *
 * Asset sections: STOCKS | CRYPTO | ETFs | PHYSICAL
 * Each section filters positions by asset_type and has its own Add modal.
 *
 * Data flow:
 *   1. Load portfolios on mount -> auto-select first
 *   2. Load positions when active portfolio changes
 *   3. Load live quotes from bulkQuotes after positions load
 *   4. Load price-change data when changePeriod or positions change
 *   5. All mutations reload positions + quotes
 */

import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import { useMarketStatus } from "../components/common";
import { useCurrency } from "../context/CurrencyContext";
import { useI18n } from "../context/I18nContext";
import { fmtUSD, fmtQty, fmtPct, fmtDate } from "../utils/formatters";
import { MODAL_BACKDROP as BDK } from "../styles/shared";
import AssetDetailPanel from "../components/common/AssetDetailPanel";
import AlertModal from "../components/common/AlertModal";
import StaleDataBanner from "../components/common/StaleDataBanner";

/* -- Asset section config ------------------------------------------------- */
const SECTIONS = [
  { id: "all",      label: "ALL" },
  { id: "stock",    label: "STOCKS" },
  { id: "crypto",   label: "CRYPTO" },
  { id: "etf",      label: "ETFs" },
  { id: "physical", label: "PHYSICAL" },
  { id: "trades",   label: "TRADE HISTORY" },
  { id: "rules",    label: "RULES" },
];

const METALS = [
  { name: "Gold",      symbol: "GC=F" },
  { name: "Silver",    symbol: "SI=F" },
  { name: "Platinum",  symbol: "PL=F" },
  { name: "Palladium", symbol: "PA=F" },
  { name: "Copper",    symbol: "HG=F" },
];

/* =========================================================================
   MODAL: Create Portfolio
========================================================================= */
function CreatePortfolioModal({ onClose, onCreated, token }) {
  const [name,     setName]     = useState("");
  const [strategy, setStrategy] = useState("");
  const [loading,  setLoading]  = useState(false);
  const [err,      setErr]      = useState("");

  const submit = async () => {
    if (!name.trim()) { setErr("Portfolio name is required."); return; }
    setLoading(true); setErr("");
    try {
      const p = await api.createPortfolio({ name: name.trim(), strategy: strategy.trim() || null }, token);
      onCreated(p);
    } catch (e) { setErr(e.message || "Failed to create portfolio."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">NEW PORTFOLIO</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label className="form-label">Portfolio Name *</label>
            <input className="form-control" placeholder="e.g. Tech Growth" value={name} onChange={e => setName(e.target.value)} maxLength={128} />
          </div>
          <div className="form-field">
            <label className="form-label">Strategy (optional)</label>
            <textarea className="form-control" placeholder="Describe your strategy..." value={strategy}
              onChange={e => setStrategy(e.target.value)} rows={3} maxLength={2000}
              style={{ resize: "vertical", minHeight: 72, fontFamily: "var(--font-mono)", fontSize: 12 }} />
          </div>
        </div>
        {err && <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>{err}</div>}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">CREATING...</span> : "CREATE"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Add Stock Position
========================================================================= */
function AddStockModal({ portfolioId, portfolio, onClose, onAdded, token }) {
  const [form, setForm] = useState({ ticker: "", quantity: "", purchase_date: "", purchase_price: "", group_tag: "", hard_stop_loss: "", profit_taking: "" });
  const [deductCash, setDeductCash] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const estimatedCost = (parseFloat(form.quantity) || 0) * (parseFloat(form.purchase_price) || 0);

  const submit = async () => {
    if (!form.ticker.trim()) { setErr("Ticker is required."); return; }
    if (!form.quantity || isNaN(+form.quantity) || +form.quantity <= 0) { setErr("Quantity must be a positive number."); return; }
    if (!form.purchase_price || isNaN(+form.purchase_price) || +form.purchase_price <= 0) { setErr("Purchase price must be a positive number."); return; }
    if (!form.purchase_date) { setErr("Purchase date is required."); return; }
    setLoading(true); setErr("");
    try {
      const payload = {
        ticker:         form.ticker.trim().toUpperCase(),
        name:           null,
        quantity:       parseFloat(form.quantity),
        purchase_price: parseFloat(form.purchase_price),
        purchase_date:  new Date(form.purchase_date).toISOString(),
        group_tag:      form.group_tag.trim() || null,
        asset_type:     "stock",
        hard_stop_loss: form.hard_stop_loss && !isNaN(+form.hard_stop_loss) && +form.hard_stop_loss > 0 ? parseFloat(form.hard_stop_loss) : null,
        profit_taking:  form.profit_taking && !isNaN(+form.profit_taking) && +form.profit_taking > 0 ? parseFloat(form.profit_taking) : null,
        deduct_cash:    deductCash,
      };
      const pos = await api.addPosition(portfolioId, payload, token);
      onAdded(pos);
    } catch (e) { setErr(e.message || "Failed to add position."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">ADD STOCK POSITION</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Ticker *</label>
              <input className="form-control" placeholder="AAPL" value={form.ticker} onChange={e => set("ticker", e.target.value.toUpperCase())} maxLength={20} />
            </div>
            <div className="form-field">
              <label className="form-label">Purchase Date *</label>
              <input className="form-control" type="date" value={form.purchase_date} onChange={e => set("purchase_date", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Quantity *</label>
              <input className="form-control" type="number" min="0.000001" step="any" placeholder="10" value={form.quantity} onChange={e => set("quantity", e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-label">Purchase Price (BEP) *</label>
              <input className="form-control" type="number" min="0.01" step="any" placeholder="155.00" value={form.purchase_price} onChange={e => set("purchase_price", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Group / Tag</label>
              <input className="form-control" placeholder="Core, Speculative..." value={form.group_tag} onChange={e => set("group_tag", e.target.value)} maxLength={64} />
            </div>
            <div className="form-field">
              <label className="form-label">Hard Stop Loss</label>
              <input className="form-control" type="number" min="0.01" step="any" placeholder="140.00" value={form.hard_stop_loss} onChange={e => set("hard_stop_loss", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Profit Taking</label>
              <input className="form-control" type="number" min="0.01" step="any" placeholder="200.00" value={form.profit_taking} onChange={e => set("profit_taking", e.target.value)} />
            </div>
            <div className="form-field" />
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, fontSize: 12, fontFamily: "var(--font-mono)", cursor: "pointer", color: "var(--c-text)" }}>
            <input type="checkbox" checked={deductCash} onChange={e => setDeductCash(e.target.checked)}
              style={{ accentColor: "var(--c-accent)", cursor: "pointer" }} />
            Deduct ${estimatedCost > 0 ? estimatedCost.toFixed(2) : "?"} from cash balance
          </label>
          {deductCash && estimatedCost > 0 && estimatedCost > (portfolio?.cash_balance ?? 0) && (
            <p style={{ color: "var(--red)", fontSize: 11, marginTop: 4, fontFamily: "var(--font-mono)" }}>
              Insufficient cash. Available: ${(portfolio?.cash_balance ?? 0).toFixed(2)}
            </p>
          )}
        </div>
        {err && <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>{err}</div>}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">ADDING...</span> : "ADD POSITION"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Add Crypto Position
========================================================================= */
function AddCryptoModal({ portfolioId, portfolio, onClose, onAdded, token }) {
  const [form, setForm] = useState({ ticker: "", quantity: "", purchase_date: "", purchase_price: "", hard_stop_loss: "", profit_taking: "" });
  const [deductCash, setDeductCash] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const estimatedCost = (parseFloat(form.quantity) || 0) * (parseFloat(form.purchase_price) || 0);

  const submit = async () => {
    if (!form.ticker.trim()) { setErr("Symbol is required (e.g. BTC-USD)."); return; }
    if (!form.quantity || isNaN(+form.quantity) || +form.quantity <= 0) { setErr("Quantity must be a positive number."); return; }
    if (!form.purchase_price || isNaN(+form.purchase_price) || +form.purchase_price <= 0) { setErr("Purchase price must be a positive number."); return; }
    if (!form.purchase_date) { setErr("Purchase date is required."); return; }
    setLoading(true); setErr("");
    try {
      const payload = {
        ticker:         form.ticker.trim().toUpperCase(),
        name:           null,
        quantity:       parseFloat(form.quantity),
        purchase_price: parseFloat(form.purchase_price),
        purchase_date:  new Date(form.purchase_date).toISOString(),
        group_tag:      null,
        asset_type:     "crypto",
        hard_stop_loss: form.hard_stop_loss && !isNaN(+form.hard_stop_loss) && +form.hard_stop_loss > 0 ? parseFloat(form.hard_stop_loss) : null,
        profit_taking:  form.profit_taking && !isNaN(+form.profit_taking) && +form.profit_taking > 0 ? parseFloat(form.profit_taking) : null,
        deduct_cash:    deductCash,
      };
      const pos = await api.addPosition(portfolioId, payload, token);
      onAdded(pos);
    } catch (e) { setErr(e.message || "Failed to add position."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">ADD CRYPTO POSITION</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Symbol *</label>
              <input className="form-control" placeholder="BTC-USD" value={form.ticker} onChange={e => set("ticker", e.target.value.toUpperCase())} maxLength={20} />
              <span className="form-hint">Use Yahoo format: BTC-USD, ETH-USD, SOL-USD...</span>
            </div>
            <div className="form-field">
              <label className="form-label">Purchase Date *</label>
              <input className="form-control" type="date" value={form.purchase_date} onChange={e => set("purchase_date", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Quantity *</label>
              <input className="form-control" type="number" min="0.000001" step="any" placeholder="0.5" value={form.quantity} onChange={e => set("quantity", e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-label">Purchase Price *</label>
              <input className="form-control" type="number" min="0.01" step="any" placeholder="42000.00" value={form.purchase_price} onChange={e => set("purchase_price", e.target.value)} />
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">Hard Stop Loss</label>
            <input className="form-control" type="number" min="0.01" step="any" placeholder="38000.00" value={form.hard_stop_loss} onChange={e => set("hard_stop_loss", e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-label">Profit Taking</label>
            <input className="form-control" type="number" min="0.01" step="any" placeholder="55000.00" value={form.profit_taking} onChange={e => set("profit_taking", e.target.value)} />
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, fontSize: 12, fontFamily: "var(--font-mono)", cursor: "pointer", color: "var(--c-text)" }}>
            <input type="checkbox" checked={deductCash} onChange={e => setDeductCash(e.target.checked)}
              style={{ accentColor: "var(--c-accent)", cursor: "pointer" }} />
            Deduct ${estimatedCost > 0 ? estimatedCost.toFixed(2) : "?"} from cash balance
          </label>
          {deductCash && estimatedCost > 0 && estimatedCost > (portfolio?.cash_balance ?? 0) && (
            <p style={{ color: "var(--red)", fontSize: 11, marginTop: 4, fontFamily: "var(--font-mono)" }}>
              Insufficient cash. Available: ${(portfolio?.cash_balance ?? 0).toFixed(2)}
            </p>
          )}
        </div>
        {err && <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>{err}</div>}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">ADDING...</span> : "ADD CRYPTO"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Add ETF Position
========================================================================= */
function AddETFModal({ portfolioId, portfolio, onClose, onAdded, token }) {
  const [form, setForm] = useState({ ticker: "", quantity: "", purchase_date: "", purchase_price: "", hard_stop_loss: "", profit_taking: "" });
  const [deductCash, setDeductCash] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const estimatedCost = (parseFloat(form.quantity) || 0) * (parseFloat(form.purchase_price) || 0);

  const submit = async () => {
    if (!form.ticker.trim()) { setErr("Symbol is required (e.g. GLD)."); return; }
    if (!form.quantity || isNaN(+form.quantity) || +form.quantity <= 0) { setErr("Quantity must be a positive number."); return; }
    if (!form.purchase_price || isNaN(+form.purchase_price) || +form.purchase_price <= 0) { setErr("Purchase price must be a positive number."); return; }
    if (!form.purchase_date) { setErr("Purchase date is required."); return; }
    setLoading(true); setErr("");
    try {
      const payload = {
        ticker:         form.ticker.trim().toUpperCase(),
        name:           null,
        quantity:       parseFloat(form.quantity),
        purchase_price: parseFloat(form.purchase_price),
        purchase_date:  new Date(form.purchase_date).toISOString(),
        group_tag:      null,
        asset_type:     "etf",
        hard_stop_loss: form.hard_stop_loss && !isNaN(+form.hard_stop_loss) && +form.hard_stop_loss > 0 ? parseFloat(form.hard_stop_loss) : null,
        profit_taking:  form.profit_taking && !isNaN(+form.profit_taking) && +form.profit_taking > 0 ? parseFloat(form.profit_taking) : null,
        deduct_cash:    deductCash,
      };
      const pos = await api.addPosition(portfolioId, payload, token);
      onAdded(pos);
    } catch (e) { setErr(e.message || "Failed to add position."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">ADD ETF POSITION</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Symbol *</label>
              <input className="form-control" placeholder="GLD" value={form.ticker} onChange={e => set("ticker", e.target.value.toUpperCase())} maxLength={20} />
              <span className="form-hint">e.g. GLD, SLV, QQQ, SPY, VTI...</span>
            </div>
            <div className="form-field">
              <label className="form-label">Purchase Date *</label>
              <input className="form-control" type="date" value={form.purchase_date} onChange={e => set("purchase_date", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Quantity *</label>
              <input className="form-control" type="number" min="0.000001" step="any" placeholder="25" value={form.quantity} onChange={e => set("quantity", e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-label">Purchase Price *</label>
              <input className="form-control" type="number" min="0.01" step="any" placeholder="180.00" value={form.purchase_price} onChange={e => set("purchase_price", e.target.value)} />
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">Hard Stop Loss</label>
            <input className="form-control" type="number" min="0.01" step="any" placeholder="170.00" value={form.hard_stop_loss} onChange={e => set("hard_stop_loss", e.target.value)} />
          </div>
          <div className="form-field">
            <label className="form-label">Profit Taking</label>
            <input className="form-control" type="number" min="0.01" step="any" placeholder="200.00" value={form.profit_taking} onChange={e => set("profit_taking", e.target.value)} />
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, fontSize: 12, fontFamily: "var(--font-mono)", cursor: "pointer", color: "var(--c-text)" }}>
            <input type="checkbox" checked={deductCash} onChange={e => setDeductCash(e.target.checked)}
              style={{ accentColor: "var(--c-accent)", cursor: "pointer" }} />
            Deduct ${estimatedCost > 0 ? estimatedCost.toFixed(2) : "?"} from cash balance
          </label>
          {deductCash && estimatedCost > 0 && estimatedCost > (portfolio?.cash_balance ?? 0) && (
            <p style={{ color: "var(--red)", fontSize: 11, marginTop: 4, fontFamily: "var(--font-mono)" }}>
              Insufficient cash. Available: ${(portfolio?.cash_balance ?? 0).toFixed(2)}
            </p>
          )}
        </div>
        {err && <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>{err}</div>}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">ADDING...</span> : "ADD ETF"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Add Physical Asset
========================================================================= */
function AddPhysicalModal({ portfolioId, portfolio, onClose, onAdded, token }) {
  const [form, setForm] = useState({ metal: METALS[0].symbol, quantity: "", purchase_date: "", purchase_price: "", physical_type: "coin", name: "", hard_stop_loss: "", profit_taking: "" });
  const [deductCash, setDeductCash] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const estimatedCost = (parseFloat(form.quantity) || 0) * (parseFloat(form.purchase_price) || 0);

  const submit = async () => {
    if (!form.quantity || isNaN(+form.quantity) || +form.quantity <= 0) { setErr("Quantity must be a positive number."); return; }
    if (!form.purchase_price || isNaN(+form.purchase_price) || +form.purchase_price <= 0) { setErr("Purchase price must be a positive number."); return; }
    if (!form.purchase_date) { setErr("Purchase date is required."); return; }
    setLoading(true); setErr("");
    try {
      const payload = {
        ticker:         form.metal,
        name:           form.name.trim() || null,
        quantity:       parseFloat(form.quantity),
        purchase_price: parseFloat(form.purchase_price),
        purchase_date:  new Date(form.purchase_date).toISOString(),
        group_tag:      null,
        asset_type:     "physical",
        physical_type:  form.physical_type,
        hard_stop_loss: form.hard_stop_loss && !isNaN(+form.hard_stop_loss) && +form.hard_stop_loss > 0 ? parseFloat(form.hard_stop_loss) : null,
        profit_taking:  form.profit_taking && !isNaN(+form.profit_taking) && +form.profit_taking > 0 ? parseFloat(form.profit_taking) : null,
        deduct_cash:    deductCash,
      };
      const pos = await api.addPosition(portfolioId, payload, token);
      onAdded(pos);
    } catch (e) { setErr(e.message || "Failed to add position."); }
    finally { setLoading(false); }
  };

  const selectedMetal = METALS.find(m => m.symbol === form.metal);

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">ADD PHYSICAL ASSET</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Metal *</label>
              <select className="form-control" value={form.metal} onChange={e => set("metal", e.target.value)}
                style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                {METALS.map(m => <option key={m.symbol} value={m.symbol}>{m.name} ({m.symbol})</option>)}
              </select>
            </div>
            <div className="form-field">
              <label className="form-label">Type *</label>
              <select className="form-control" value={form.physical_type} onChange={e => set("physical_type", e.target.value)}
                style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>
                <option value="coin">Coin</option>
                <option value="bar">Bar</option>
              </select>
            </div>
          </div>
          <div className="form-field">
            <label className="form-label">Name / Description</label>
            <input className="form-control" placeholder={`e.g. American Eagle 1oz ${selectedMetal?.name || ""}`} value={form.name} onChange={e => set("name", e.target.value)} maxLength={256} />
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Quantity *</label>
              <input className="form-control" type="number" min="0.000001" step="any" placeholder="5" value={form.quantity} onChange={e => set("quantity", e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-label">Purchase Price *</label>
              <input className="form-control" type="number" min="0.01" step="any" placeholder="1950.00" value={form.purchase_price} onChange={e => set("purchase_price", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Purchase Date *</label>
              <input className="form-control" type="date" value={form.purchase_date} onChange={e => set("purchase_date", e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-label">Hard Stop Loss</label>
              <input className="form-control" type="number" min="0.01" step="any" placeholder="1800.00" value={form.hard_stop_loss} onChange={e => set("hard_stop_loss", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Profit Taking</label>
              <input className="form-control" type="number" min="0.01" step="any" placeholder="2200.00" value={form.profit_taking} onChange={e => set("profit_taking", e.target.value)} />
            </div>
            <div className="form-field" />
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, fontSize: 12, fontFamily: "var(--font-mono)", cursor: "pointer", color: "var(--c-text)" }}>
            <input type="checkbox" checked={deductCash} onChange={e => setDeductCash(e.target.checked)}
              style={{ accentColor: "var(--c-accent)", cursor: "pointer" }} />
            Deduct ${estimatedCost > 0 ? estimatedCost.toFixed(2) : "?"} from cash balance
          </label>
          {deductCash && estimatedCost > 0 && estimatedCost > (portfolio?.cash_balance ?? 0) && (
            <p style={{ color: "var(--red)", fontSize: 11, marginTop: 4, fontFamily: "var(--font-mono)" }}>
              Insufficient cash. Available: ${(portfolio?.cash_balance ?? 0).toFixed(2)}
            </p>
          )}
        </div>
        {err && <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>{err}</div>}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">ADDING...</span> : "ADD PHYSICAL"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: CSV Import
   Expected CSV: Ticker,Name,Quantity,PurchaseDate,PurchasePrice,Group
========================================================================= */
function CSVImportModal({ portfolioId, onClose, onImported, token, assetType, formatValue }) {
  const [rows,    setRows]    = useState([]);
  const [err,     setErr]     = useState("");
  const [loading, setLoading] = useState(false);

  const parseCSV = (text) => {
    setErr(""); setRows([]);
    const lines = text.trim().split(/\r?\n/).filter(Boolean);
    if (lines.length < 2) { setErr("CSV must have a header row and at least one data row."); return; }
    const headers = lines[0].split(",").map(h => h.trim().toLowerCase());
    const iT = headers.indexOf("ticker");
    const iN = headers.indexOf("name");
    const iQ = headers.indexOf("quantity");
    const iD = headers.indexOf("purchasedate");
    const iP = headers.indexOf("purchaseprice");
    const iG = headers.indexOf("group");
    if (iT === -1 || iQ === -1 || iP === -1) {
      setErr("Missing required columns: Ticker, Quantity, PurchasePrice."); return;
    }
    const parsed = [];
    const parseErrors = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(",").map(c => c.trim());
      const ticker = iT >= 0 ? cols[iT]?.toUpperCase() : "";
      const qty    = parseFloat(cols[iQ] ?? "");
      const price  = parseFloat(cols[iP] ?? "");
      if (!ticker) { parseErrors.push(`Row ${i + 1}: missing ticker.`); continue; }
      if (isNaN(qty) || qty <= 0) { parseErrors.push(`Row ${i + 1}: invalid quantity.`); continue; }
      if (isNaN(price) || price <= 0) { parseErrors.push(`Row ${i + 1}: invalid purchase price.`); continue; }
      let purchaseDate = null;
      if (iD >= 0 && cols[iD]) {
        const d = new Date(cols[iD]);
        if (!isNaN(d.getTime())) purchaseDate = d.toISOString();
      }
      parsed.push({
        ticker,
        name:           (iN >= 0 ? cols[iN] : null) || null,
        quantity:       qty,
        purchase_price: price,
        purchase_date:  purchaseDate,
        group_tag:      (iG >= 0 ? cols[iG] : null) || null,
        asset_type:     assetType,
      });
    }
    if (parseErrors.length) { setErr(parseErrors.slice(0, 3).join(" ") + (parseErrors.length > 3 ? ` (+${parseErrors.length - 3} more)` : "")); return; }
    if (!parsed.length) { setErr("No valid rows found."); return; }
    setRows(parsed);
  };

  const handleFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => parseCSV(ev.target.result);
    reader.readAsText(file);
  };

  const submit = async () => {
    if (!rows.length) return;
    setLoading(true); setErr("");
    try {
      const created = await api.importPositions(portfolioId, rows, token);
      onImported(created);
    } catch (e) { setErr(e.message || "Import failed."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box" style={{ maxWidth: 640, width: "90vw" }}>
        <div className="modal-top">
          <div className="modal-title">IMPORT CSV</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--c-muted)", marginBottom: 12, lineHeight: 1.6 }}>
            Expected columns: <span style={{ color: "var(--c-accent)" }}>Ticker, Name, Quantity, PurchaseDate, PurchasePrice, Group</span><br />
            PurchaseDate format: YYYY-MM-DD. Name and Group are optional.
          </div>
          <div className="form-field">
            <label className="form-label">CSV File</label>
            <input type="file" accept=".csv,text/csv" onChange={handleFile}
              style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--c-text)", background: "transparent", border: "none", padding: 0 }} />
          </div>
          {rows.length > 0 && (
            <div style={{ maxHeight: 240, overflowY: "auto", border: "1px solid var(--c-border)", borderRadius: 4, marginTop: 8 }}>
              <table className="data-table" style={{ fontSize: 11 }}>
                <thead>
                  <tr><th>TICKER</th><th>NAME</th><th className="right">QTY</th><th className="right">BEP</th><th>DATE</th><th>GROUP</th></tr>
                </thead>
                <tbody>
                  {rows.slice(0, 50).map((r, i) => (
                    <tr key={i}>
                      <td><span className="amber">{r.ticker}</span></td>
                      <td>{r.name || "\u2014"}</td>
                      <td className="right">{fmtQty(r.quantity)}</td>
                      <td className="right">{formatValue(r.purchase_price)}</td>
                      <td>{fmtDate(r.purchase_date)}</td>
                      <td>{r.group_tag || "\u2014"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length > 50 && <div style={{ padding: "6px 12px", fontSize: 11, color: "var(--c-muted)" }}>...and {rows.length - 50} more rows</div>}
            </div>
          )}
        </div>
        {err && <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>{err}</div>}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading || !rows.length}>
            {loading ? <span className="loading-pulse">IMPORTING...</span> : `IMPORT ${rows.length} ROWS`}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Modify Position
========================================================================= */
function ModifyPositionModal({ position, onClose, onModified, token }) {
  const [form, setForm] = useState({
    quantity:       String(parseFloat(position.quantity)),
    purchase_price: String(parseFloat(position.purchase_price)),
    group_tag:      position.group_tag || "",
    hard_stop_loss: position.hard_stop_loss ? String(parseFloat(position.hard_stop_loss)) : "",
    soft_stop_loss: position.soft_stop_loss ? String(parseFloat(position.soft_stop_loss)) : "",
    profit_taking:  position.profit_taking ? String(parseFloat(position.profit_taking)) : "",
  });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.quantity || isNaN(+form.quantity) || +form.quantity <= 0) { setErr("Quantity must be a positive number."); return; }
    if (!form.purchase_price || isNaN(+form.purchase_price) || +form.purchase_price <= 0) { setErr("Purchase price must be a positive number."); return; }
    if (form.hard_stop_loss && (isNaN(+form.hard_stop_loss) || +form.hard_stop_loss < 0)) { setErr("Hard stop loss must be a non-negative number."); return; }
    if (form.soft_stop_loss && (isNaN(+form.soft_stop_loss) || +form.soft_stop_loss < 0)) { setErr("Soft stop loss must be a non-negative number."); return; }
    if (form.profit_taking && (isNaN(+form.profit_taking) || +form.profit_taking < 0)) { setErr("Profit taking must be a non-negative number."); return; }
    setLoading(true); setErr("");
    try {
      const updated = await api.modifyPosition(position.position_id, {
        quantity:       parseFloat(form.quantity),
        purchase_price: parseFloat(form.purchase_price),
        group_tag:      form.group_tag.trim() || null,
        hard_stop_loss: form.hard_stop_loss ? parseFloat(form.hard_stop_loss) : null,
        soft_stop_loss: form.soft_stop_loss ? parseFloat(form.soft_stop_loss) : null,
        profit_taking:  form.profit_taking ? parseFloat(form.profit_taking) : null,
      }, token);
      onModified(updated);
    } catch (e) { setErr(e.message || "Failed to modify position."); }
    finally { setLoading(false); }
  };

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">MODIFY POSITION {"\u2014"} {position.ticker}</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Quantity</label>
              <input className="form-control" type="number" min="0.000001" step="any" value={form.quantity} onChange={e => set("quantity", e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-label">Purchase Price (BEP)</label>
              <input className="form-control" type="number" min="0.01" step="any" value={form.purchase_price} onChange={e => set("purchase_price", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Hard Stop Loss (optional)</label>
              <input className="form-control" type="number" min="0" step="any" placeholder="e.g. 145.00" value={form.hard_stop_loss} onChange={e => set("hard_stop_loss", e.target.value)} />
            </div>
            <div className="form-field">
              <label className="form-label">Soft Stop Loss (optional)</label>
              <input className="form-control" type="number" min="0" step="any" placeholder="e.g. 150.00" value={form.soft_stop_loss} onChange={e => set("soft_stop_loss", e.target.value)} />
            </div>
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Profit Taking (optional)</label>
              <input className="form-control" type="number" min="0" step="any" placeholder="e.g. 200.00" value={form.profit_taking} onChange={e => set("profit_taking", e.target.value)} />
            </div>
            <div className="form-field" />
          </div>
          <div className="form-row">
            <div className="form-field">
              <label className="form-label">Group / Tag</label>
              <input className="form-control" placeholder="Core, Speculative..." value={form.group_tag} onChange={e => set("group_tag", e.target.value)} maxLength={64} />
            </div>
            <div className="form-field" />
          </div>
        </div>
        {err && <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>{err}</div>}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-amber" onClick={submit} disabled={loading}>
            {loading ? <span className="loading-pulse">SAVING...</span> : "SAVE CHANGES"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   MODAL: Sell Position
========================================================================= */
function SellPositionModal({ position, portfolio, onClose, onSold, onPortfolioRefresh, token }) {
  const maxQty = parseFloat(position.quantity);
  const [qty,        setQty]        = useState(String(maxQty));
  const [sellPrice,  setSellPrice]  = useState(String(parseFloat(position.purchase_price)));
  const [priceLoading, setPriceLoading] = useState(true);
  const [creditCash, setCreditCash] = useState(true);
  const [loading,    setLoading]    = useState(false);
  const [err,        setErr]        = useState("");

  // Fetch current market price on open; pre-populate sell price field
  useEffect(() => {
    let cancelled = false;
    api.getQuote(position.ticker, token)
      .then(q => { if (!cancelled) setSellPrice(String(q.price)); })
      .catch(() => { /* keep purchase_price fallback */ })
      .finally(() => { if (!cancelled) setPriceLoading(false); });
    return () => { cancelled = true; };
  }, [position.ticker, token]);

  const sell = async () => {
    const n = parseFloat(qty);
    const p = parseFloat(sellPrice);
    if (isNaN(n) || n <= 0) { setErr("Enter a valid quantity."); return; }
    if (n > maxQty) { setErr(`Cannot sell more than ${fmtQty(maxQty)} units.`); return; }
    if (isNaN(p) || p <= 0) { setErr("Enter a valid sell price."); return; }
    setLoading(true); setErr("");
    try {
      const result = await api.sellPosition(position.position_id, n, p, token, creditCash);
      onSold(result);
      if (creditCash && onPortfolioRefresh) onPortfolioRefresh();
    } catch (e) { setErr(e.message || "Sell failed."); }
    finally { setLoading(false); }
  };

  const n      = parseFloat(qty) || 0;
  const p      = parseFloat(sellPrice) || 0;
  const isFull = n >= maxQty;
  const estimatedProceeds = n * p;

  return (
    <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-top">
          <div className="modal-title">SELL {"\u2014"} {position.ticker}</div>
          <button className="modal-close" onClick={onClose}><Ic.close /></button>
        </div>
        <div className="modal-body">
          <div style={{ marginBottom: 12, fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--c-muted)" }}>
            Current position: <span style={{ color: "var(--c-text)" }}>{fmtQty(maxQty)} units</span>
          </div>
          <div className="form-field">
            <label className="form-label">Units to Sell</label>
            <input className="form-control" type="number" min="0.000001" max={maxQty} step="any"
              value={qty} onChange={e => { setErr(""); setQty(e.target.value); }} />
            <span className="form-hint">
              {isFull
                ? <span style={{ color: "var(--red)" }}>Selling all units {"\u2014"} position will be deleted.</span>
                : `${fmtQty(maxQty - n)} units remaining after sale.`}
            </span>
          </div>
          <div className="form-field" style={{ marginTop: 12 }}>
            <label className="form-label">
              Sell Price
              {priceLoading && <span style={{ fontWeight: 400, color: "var(--c-muted)", marginLeft: 6, fontSize: 10 }}>fetching market price…</span>}
            </label>
            <input className="form-control" type="number" min="0.000001" step="any"
              value={sellPrice} onChange={e => { setErr(""); setSellPrice(e.target.value); }} />
            <span className="form-hint">Current market price pre-filled. Edit to override.</span>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, fontSize: 12, fontFamily: "var(--font-mono)", cursor: "pointer", color: "var(--c-text)" }}>
            <input type="checkbox" checked={creditCash} onChange={e => setCreditCash(e.target.checked)}
              style={{ accentColor: "var(--c-accent)", cursor: "pointer" }} />
            Credit proceeds to cash balance
            {n > 0 && p > 0 && <span style={{ color: "var(--c-muted)", fontSize: 11 }}>
              (~{fmtUSD(estimatedProceeds)})
            </span>}
          </label>
        </div>
        {err && <div style={{ padding: "8px 20px", fontSize: 11, color: "var(--red)", background: "rgba(239,68,68,.06)", borderTop: "1px solid rgba(239,68,68,.2)" }}>{err}</div>}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>CANCEL</button>
          <button className="btn btn-red" onClick={sell} disabled={loading}>
            {loading ? <span className="loading-pulse">SELLING...</span> : (isFull ? "SELL ALL" : `SELL ${fmtQty(n)}`)}
          </button>
        </div>
      </div>
    </div>
  );
}

/* =========================================================================
   SORT HEADER
========================================================================= */
function SortTh({ label, col, sortCol, sortDir, onSort, right }) {
  const active = sortCol === col;
  return (
    <th className={right ? "right" : ""} onClick={() => onSort(col)}
      style={{ cursor: "pointer", userSelect: "none", whiteSpace: "nowrap" }}>
      {label}
      {active
        ? <span style={{ marginLeft: 4, opacity: .8 }}>{sortDir === "asc" ? "\u25B2" : "\u25BC"}</span>
        : <span style={{ marginLeft: 4, opacity: .25 }}>{"\u21C5"}</span>}
    </th>
  );
}

/* =========================================================================
   MAIN PAGE
========================================================================= */
export function PortfolioManagerPage({ token, onViewChart, onViewNews, onTradeAI, pageParams }) {
  /* -- State -------------------------------------------------------------- */
  const { formatValue } = useCurrency();
  const { t } = useI18n();
  const { isOpen: marketOpen } = useMarketStatus();
  const pollRef = useRef(null);
  const [portfolios,         setPortfolios]         = useState([]);
  const [activePortfolioId,  setActivePortfolioId]  = useState(null);
  const [positions,          setPositions]          = useState([]);
  const [quotes,             setQuotes]             = useState({});
  const [priceChanges,       setPriceChanges]       = useState({});
  const [changePeriod,       setChangePeriod]       = useState("1D");
  const [sortCol,            setSortCol]            = useState(null);
  const [sortDir,            setSortDir]            = useState("asc");

  /* -- Apply sort params passed from parent (e.g. Dashboard VIEW ALL) ----- */
  useEffect(() => {
    if (pageParams?.sortCol) {
      setSortCol(pageParams.sortCol);
      setSortDir(pageParams.sortDir || "desc");
    }
  }, [pageParams]);

  const [loadingPortfolios,  setLoadingPortfolios]  = useState(false);
  const [loadingPositions,   setLoadingPositions]   = useState(false);
  const [globalErr,          setGlobalErr]          = useState("");
  const [activeSection,      setActiveSection]      = useState("all");
  const [smaData,            setSmaData]            = useState({});   // { AAPL: { 50: 180.12, 200: 165.30 }, ... }
  const [customSmaPeriod,    setCustomSmaPeriod]    = useState(200);
  const [editingStopLoss,      setEditingStopLoss]      = useState(null); // position_id or null
  const [stopLossInput,        setStopLossInput]        = useState("");
  const [editingSoftStopLoss,  setEditingSoftStopLoss]  = useState(null); // position_id or null
  const [softStopLossInput,    setSoftStopLossInput]    = useState("");
  const [editingProfitTaking, setEditingProfitTaking] = useState(null); // position_id or null
  const [profitTakingInput,   setProfitTakingInput]   = useState("");

  // Modals
  const [showCreate,    setShowCreate]    = useState(false);
  const [showAddModal,  setShowAddModal]  = useState(null);   // "stock"|"crypto"|"etf"|"physical" or null
  const [showImport,    setShowImport]    = useState(false);
  const [modifyPos,     setModifyPos]     = useState(null);
  const [sellPos,       setSellPos]       = useState(null);
  const [detailSymbol,  setDetailSymbol]  = useState(null);   // symbol for AssetDetailPanel modal
  const [alertSymbol,   setAlertSymbol]   = useState(null);   // symbol for AlertModal
  const [alertPrice,    setAlertPrice]    = useState(null);   // current price for AlertModal

  // Portfolio scoring (detailed)
  const [scoreLoading,  setScoreLoading]  = useState(false);
  const [scoreResults,  setScoreResults]  = useState(null);   // array of PositionScore or null
  const [showScoreModal, setShowScoreModal] = useState(false);

  // Trade history
  const [trades,        setTrades]        = useState([]);
  const [loadingTrades, setLoadingTrades] = useState(false);

  // Cash adjustment
  const [showCashModal, setShowCashModal] = useState(false);
  const [cashAmount,    setCashAmount]    = useState("");
  const [cashNotes,     setCashNotes]     = useState("");
  const [cashLoading,   setCashLoading]   = useState(false);

  // Portfolio rules
  const [ruleAlerts,      setRuleAlerts]      = useState([]);
  const [loadingAlerts,   setLoadingAlerts]   = useState(false);
  const [runningRules,    setRunningRules]    = useState(false);
  const [rulesSchedule,   setRulesSchedule]   = useState("on_demand");
  const [alertSevFilter,  setAlertSevFilter]  = useState(null);   // null | "info" | "warning" | "critical"
  const [alertStateFilter, setAlertStateFilter] = useState(null); // null | "active" | "snoozed" | "actioned"

  /* Stale-quote tracking — banner appears after 5 min without a fresh fetch */
  const [quotesTimestamp, setQuotesTimestamp] = useState(null);
  const [quotesStale,     setQuotesStale]     = useState(false);

  /* Column visibility — persisted to localStorage */
  const DEFAULT_COLS = new Set(["ticker", "name", "qty", "bep", "price", "value", "gainloss", "chg", "actions"]);
  const [visibleCols, setVisibleCols] = useState(() => {
    try {
      const s = localStorage.getItem("tickertap_visible_cols");
      return s ? new Set(JSON.parse(s)) : new Set(DEFAULT_COLS);
    } catch { return new Set(DEFAULT_COLS); }
  });
  const [showColPicker, setShowColPicker] = useState(false);

  /**
   * toggleCol — toggles a column in the visible-columns set and persists to localStorage.
   * @param {string} col - column ID to toggle
   */
  const toggleCol = (col) => {
    setVisibleCols(prev => {
      const next = new Set(prev);
      if (next.has(col)) next.delete(col); else next.add(col);
      localStorage.setItem("tickertap_visible_cols", JSON.stringify([...next]));
      return next;
    });
  };

  /* -- Data loading ------------------------------------------------------- */
  const loadPortfolios = useCallback(async () => {
    if (!token) return;
    setLoadingPortfolios(true); setGlobalErr("");
    try {
      const list = await api.listPortfolios(token);
      setPortfolios(list);
      if (list.length && !activePortfolioId) setActivePortfolioId(list[0].portfolio_id);
    } catch (e) { setGlobalErr(e.message || "Failed to load portfolios."); }
    finally { setLoadingPortfolios(false); }
  }, [token]); // eslint-disable-line

  const loadPositions = useCallback(async (portfolioId) => {
    if (!token || !portfolioId) { setPositions([]); return; }
    setLoadingPositions(true); setGlobalErr("");
    try {
      const list = await api.listPositions(portfolioId, token);
      setPositions(list);
    } catch (e) { setGlobalErr(e.message || "Failed to load positions."); }
    finally { setLoadingPositions(false); }
  }, [token]);

  const loadQuotes = useCallback(async (positionList, { replace = false } = {}) => {
    if (!token || !positionList.length) { setQuotes({}); return; }
    const tickers = [...new Set(positionList.map(p => p.ticker))];
    // Batch into groups of 50 to stay within the server's per-request symbol cap.
    const BATCH = 50;
    const batches = [];
    for (let i = 0; i < tickers.length; i += BATCH) batches.push(tickers.slice(i, i + BATCH));
    try {
      const batchResults = await Promise.all(batches.map(b => api.bulkQuotes(b, token)));
      const incoming = {};
      batchResults.flat().forEach(q => { incoming[q.symbol] = q; });
      // Merge into existing state so intermittent per-symbol failures
      // during polling don't wipe previously-loaded data.
      setQuotes(prev => replace ? incoming : { ...prev, ...incoming });
      /* Mark quotes as fresh — stale banner resets its 5-min countdown */
      setQuotesTimestamp(Date.now());
      setQuotesStale(false);
    } catch (e) {
      console.error("[PortfolioManager] bulkQuotes failed:", e?.message ?? e);
    }
  }, [token]);

  const loadPriceChanges = useCallback(async (positionList, period, { replace = false } = {}) => {
    if (!token || !positionList.length) { setPriceChanges({}); return; }
    const tickers = [...new Set(positionList.map(p => p.ticker))];
    const results = await Promise.allSettled(
      tickers.map(sym => api.priceChange(sym, period, token))
    );
    const incoming = {};
    results.forEach((r, i) => {
      if (r.status === "fulfilled" && r.value) incoming[tickers[i]] = r.value.change_pct;
    });
    // Merge into existing state so intermittent per-symbol failures
    // during polling don't wipe previously-loaded data.
    setPriceChanges(prev => replace ? incoming : { ...prev, ...incoming });
  }, [token]);

  const loadSmaData = useCallback(async (positionList, customPeriod) => {    if (!token || !positionList.length) { setSmaData({}); return; }
    const tickers = [...new Set(positionList.map(p => p.ticker))];
    const [res50, resCustom] = await Promise.allSettled([
      api.bulkSma(tickers, 50, token),
      customPeriod !== 50 ? api.bulkSma(tickers, customPeriod, token) : Promise.resolve([]),
    ]);
    const map = {};
    if (res50.status === "fulfilled" && res50.value) {
      res50.value.forEach(r => { if (!map[r.symbol]) map[r.symbol] = {}; map[r.symbol][50] = r.sma; });
    }
    if (resCustom.status === "fulfilled" && resCustom.value) {
      resCustom.value.forEach(r => { if (!map[r.symbol]) map[r.symbol] = {}; map[r.symbol][customPeriod] = r.sma; });
    }
    // If custom === 50, copy the 50 data
    if (customPeriod === 50 && res50.status === "fulfilled" && res50.value) {
      res50.value.forEach(r => { if (map[r.symbol]) map[r.symbol][customPeriod] = r.sma; });
    }
    setSmaData(map);
  }, [token]);

  /**
   * loadTrades — fetches trade history for the active portfolio.
   * Called when the user switches to the TRADE HISTORY tab.
   */
  const loadTrades = useCallback(async (portfolioId) => {
    if (!token || !portfolioId) { setTrades([]); return; }
    setLoadingTrades(true);
    try {
      const list = await api.getPortfolioTrades(portfolioId, token);
      setTrades(list);
    } catch (e) {
      console.error("[PortfolioManager] loadTrades failed:", e?.message ?? e);
    } finally { setLoadingTrades(false); }
  }, [token]);

  /**
   * loadRuleAlerts — fetches rule alerts for the active portfolio.
   * Applies optional severity and state filters.
   *
   * @param {string}      portfolioId  - Portfolio UUID
   * @param {string|null} sevFilter    - Severity filter or null for all
   * @param {string|null} stateFilter  - State filter or null for all
   */
  const loadRuleAlerts = useCallback(async (portfolioId, sevFilter = null, stateFilter = null) => {
    if (!token || !portfolioId) { setRuleAlerts([]); return; }
    setLoadingAlerts(true);
    try {
      const list = await api.getRuleAlerts(portfolioId, {
        severity:  sevFilter  || undefined,
        state:     stateFilter || undefined,
      }, token);
      setRuleAlerts(list);
    } catch (e) {
      console.error("[PortfolioManager] loadRuleAlerts failed:", e?.message ?? e);
    } finally { setLoadingAlerts(false); }
  }, [token]);

  /**
   * handleDeleteTrade — confirms and deletes a trade record by ID.
   * Removes the entry from local state optimistically after the server
   * confirms deletion (204 No Content).
   *
   * @param {string} tradeId - UUID of the trade to remove
   */
  const handleDeleteTrade = async (tradeId) => {
    if (!window.confirm("Delete this trade record?")) return;
    try {
      await api.deleteTrade(tradeId, token);
      // Remove the deleted trade from local state without a full reload.
      setTrades(prev => prev.filter(t => t.trade_id !== tradeId));
    } catch (e) {
      console.error("Delete trade failed:", e?.message ?? e);
    }
  };

  /**
   * handleRunRules — enqueues portfolio rules evaluation on the arq worker.
   * Passes the current rulesSchedule value so the worker knows whether to
   * re-enqueue automatically on each market-hours cycle.
   * Reloads rule alerts after a short delay to let the worker settle.
   */
  const handleRunRules = async () => {
    if (!activePortfolioId) return;
    setRunningRules(true);
    try {
      await api.runPortfolioRules(activePortfolioId, rulesSchedule, token);
      // Give the worker ~3s to process before refreshing alerts
      setTimeout(() => loadRuleAlerts(activePortfolioId, alertSevFilter, alertStateFilter), 3000);
    } catch (e) {
      console.error("[PortfolioManager] runRules failed:", e?.message ?? e);
    } finally {
      setRunningRules(false);
    }
  };

  /**
   * handlePatchAlert — updates a rule alert state (snoozed | actioned | expired).
   * Optimistically updates the local alerts list without a full reload.
   *
   * @param {string} alertId  - Alert UUID
   * @param {string} newState - New state value
   */
  const handlePatchAlert = async (alertId, newState) => {
    try {
      const updated = await api.patchRuleAlert(alertId, { state: newState }, token);
      setRuleAlerts(prev => prev.map(a => a.alert_id === alertId ? updated : a));
    } catch (e) {
      console.error("[PortfolioManager] patchAlert failed:", e?.message ?? e);
    }
  };

  /* -- Effects ------------------------------------------------------------ */
  useEffect(() => { loadPortfolios(); }, [loadPortfolios]);

  useEffect(() => {
    setPositions([]); setQuotes({}); setPriceChanges({});
    if (activePortfolioId) loadPositions(activePortfolioId);
  }, [activePortfolioId, loadPositions]);

  useEffect(() => {
    if (positions.length) {
      loadQuotes(positions, { replace: true });
      loadPriceChanges(positions, changePeriod, { replace: true });
      loadSmaData(positions, customSmaPeriod);
    }
  }, [positions]); // eslint-disable-line

  useEffect(() => {
    if (positions.length) loadPriceChanges(positions, changePeriod, { replace: true });
  }, [changePeriod]); // eslint-disable-line

  useEffect(() => {
    if (positions.length) loadSmaData(positions, customSmaPeriod);
  }, [customSmaPeriod]); // eslint-disable-line

  /* Load trade history when the TRADE HISTORY tab becomes active */
  useEffect(() => {
    if (activeSection === "trades" && activePortfolioId) loadTrades(activePortfolioId);
  }, [activeSection, activePortfolioId]); // eslint-disable-line

  /* Load rule alerts when the RULES tab becomes active */
  useEffect(() => {
    if (activeSection === "rules" && activePortfolioId) loadRuleAlerts(activePortfolioId, alertSevFilter, alertStateFilter);
  }, [activeSection, activePortfolioId]); // eslint-disable-line

  /* Check staleness every minute — marks quotes as stale after 5 minutes */
  useEffect(() => {
    if (!quotesTimestamp) return;
    const id = setInterval(() => {
      setQuotesStale(Date.now() - quotesTimestamp > 300000);
    }, 60000);
    return () => clearInterval(id);
  }, [quotesTimestamp]);

  /* -- Live price polling ------------------------------------------------- */
  /* Refreshes quotes and price changes at a market-aware interval:
     15 seconds during market hours, 5 minutes when closed.
     SMA data changes infrequently so it is not polled. */
  useEffect(() => {
    clearInterval(pollRef.current);
    if (!positions.length) return;
    const ms = marketOpen ? 15_000 : 300_000;
    pollRef.current = setInterval(() => {
      loadQuotes(positions);
      loadPriceChanges(positions, changePeriod);
    }, ms);
    return () => clearInterval(pollRef.current);
  }, [positions, changePeriod, marketOpen, loadQuotes, loadPriceChanges]);

  /* -- Derived data -------------------------------------------------------- */
  const activePortfolio = useMemo(
    () => portfolios.find(p => p.portfolio_id === activePortfolioId) || null,
    [portfolios, activePortfolioId]
  );

  /* -- Filter by section -------------------------------------------------- */
  const sectionPositions = useMemo(
    () => activeSection === "all" ? positions : positions.filter(p => (p.asset_type || "stock") === activeSection),
    [positions, activeSection]
  );

  const sectionCounts = useMemo(() => {
    const counts = { all: positions.length, stock: 0, crypto: 0, etf: 0, physical: 0 };
    positions.forEach(p => { counts[p.asset_type || "stock"] = (counts[p.asset_type || "stock"] || 0) + 1; });
    // Show active alert count on RULES tab badge
    counts.rules = ruleAlerts.filter(a => a.state === "active").length;
    return counts;
  }, [positions, ruleAlerts]);

  const sortedPositions = useMemo(() => {
    if (!sortCol) return sectionPositions;
    const mul = sortDir === "asc" ? 1 : -1;
    return [...sectionPositions].sort((a, b) => {
      let av, bv;
      switch (sortCol) {
        case "ticker":        av = a.ticker;             bv = b.ticker;             break;
        case "name":          av = quotes[a.ticker]?.name || a.name || ""; bv = quotes[b.ticker]?.name || b.name || ""; break;
        case "purchase_date": av = a.purchase_date || ""; bv = b.purchase_date || ""; break;
        case "quantity":      av = parseFloat(a.quantity); bv = parseFloat(b.quantity); break;
        case "bep":           av = parseFloat(a.purchase_price); bv = parseFloat(b.purchase_price); break;
        case "price":         av = quotes[a.ticker]?.price || 0; bv = quotes[b.ticker]?.price || 0; break;
        case "change":        av = priceChanges[a.ticker] ?? -Infinity; bv = priceChanges[b.ticker] ?? -Infinity; break;
        case "value":         av = (quotes[a.ticker]?.price || 0) * parseFloat(a.quantity); bv = (quotes[b.ticker]?.price || 0) * parseFloat(b.quantity); break;
        case "gainloss":      av = ((quotes[a.ticker]?.price || 0) - parseFloat(a.purchase_price)) * parseFloat(a.quantity);
                              bv = ((quotes[b.ticker]?.price || 0) - parseFloat(b.purchase_price)) * parseFloat(b.quantity); break;
        case "sma50":         av = smaData[a.ticker]?.[50] ?? -Infinity; bv = smaData[b.ticker]?.[50] ?? -Infinity; break;
        case "smaCustom":     av = smaData[a.ticker]?.[customSmaPeriod] ?? -Infinity; bv = smaData[b.ticker]?.[customSmaPeriod] ?? -Infinity; break;
        case "hardstoploss":  av = parseFloat(a.hard_stop_loss) || -Infinity; bv = parseFloat(b.hard_stop_loss) || -Infinity; break;
        case "softstoploss":  av = parseFloat(a.soft_stop_loss) || -Infinity; bv = parseFloat(b.soft_stop_loss) || -Infinity; break;
        case "profittaking":  av = parseFloat(a.profit_taking) || -Infinity; bv = parseFloat(b.profit_taking) || -Infinity; break;
        default:              av = 0; bv = 0;
      }
      if (typeof av === "string") return mul * av.localeCompare(bv);
      return mul * (av - bv);
    });
  }, [sectionPositions, sortCol, sortDir, quotes, priceChanges, smaData, customSmaPeriod]);

  /* Summary across non-excluded positions, filtered by active section */
  const summary = useMemo(() => {
    const sectionFiltered = activeSection === "all"
      ? positions
      : positions.filter(p => (p.asset_type || "stock") === activeSection);
    const active = sectionFiltered.filter(p => !p.is_excluded);
    let totalValue = 0, totalCost = 0, periodGL = 0;
    active.forEach(p => {
      const price = quotes[p.ticker]?.price;
      const qty   = parseFloat(p.quantity);
      const bep   = parseFloat(p.purchase_price);
      // Only include positions that have a loaded price so totalValue and
      // totalCost stay in sync; prevents huge phantom losses while quotes
      // are still loading.
      if (price != null) {
        totalValue += price * qty;
        totalCost  += bep * qty;
      }
      // Aggregate period gain/loss using per-ticker change percentages.
      // ref_price = price / (1 + chgPct/100) is the previous reference price;
      // dollar G/L = (price - ref_price) * qty = qty * price * chgPct / (100 + chgPct).
      const chgPct = priceChanges[p.ticker];
      if (chgPct != null && price != null) periodGL += qty * price * chgPct / (100 + chgPct);
    });
    const gainLoss = totalValue - totalCost;
    const gainPct  = totalCost > 0 ? (gainLoss / totalCost) * 100 : 0;
    const periodPct = totalValue > 0 ? (periodGL / totalValue) * 100 : 0;
    return { totalValue, totalCost, gainLoss, gainPct, count: active.length, periodGL, periodPct };
  }, [positions, quotes, activeSection, priceChanges]);

  /* -- Sorting ------------------------------------------------------------ */
  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  };

  /* -- Actions ------------------------------------------------------------ */
  const handleDeletePortfolio = async (pid) => {
    if (!window.confirm("Delete this portfolio and all its positions?")) return;
    try {
      await api.deletePortfolio(pid, token);
      const next = portfolios.filter(p => p.portfolio_id !== pid);
      setPortfolios(next);
      if (activePortfolioId === pid) setActivePortfolioId(next[0]?.portfolio_id || null);
    } catch (e) { setGlobalErr(e.message || "Failed to delete portfolio."); }
  };

  const handleDeletePosition = async (pos) => {
    if (!window.confirm(`Delete ${pos.ticker} position?`)) return;
    try {
      await api.deletePosition(pos.position_id, token);
      const next = positions.filter(p => p.position_id !== pos.position_id);
      setPositions(next);
    } catch (e) { setGlobalErr(e.message || "Failed to delete position."); }
  };

  const handleToggleExclude = async (pos) => {
    try {
      const updated = await api.modifyPosition(pos.position_id, { is_excluded: !pos.is_excluded }, token);
      setPositions(prev => prev.map(p => p.position_id === pos.position_id ? updated : p));
    } catch (e) { setGlobalErr(e.message || "Failed to update position."); }
  };

  const handleSaveStopLoss = async (pos) => {
    const val = stopLossInput.trim();
    const numVal = val === "" ? 0 : parseFloat(val);
    if (val !== "" && (isNaN(numVal) || numVal < 0)) { setGlobalErr("Hard stop loss must be a positive number or empty."); return; }
    try {
      const updated = await api.modifyPosition(pos.position_id, { hard_stop_loss: numVal || 0 }, token);
      setPositions(prev => prev.map(p => p.position_id === pos.position_id ? updated : p));
      setEditingStopLoss(null);
    } catch (e) { setGlobalErr(e.message || "Failed to update hard stop loss."); }
  };

  const handleSaveSoftStopLoss = async (pos) => {
    const val = softStopLossInput.trim();
    const numVal = val === "" ? 0 : parseFloat(val);
    if (val !== "" && (isNaN(numVal) || numVal < 0)) { setGlobalErr("Soft stop loss must be a positive number or empty."); return; }
    try {
      const updated = await api.modifyPosition(pos.position_id, { soft_stop_loss: numVal || 0 }, token);
      setPositions(prev => prev.map(p => p.position_id === pos.position_id ? updated : p));
      setEditingSoftStopLoss(null);
    } catch (e) { setGlobalErr(e.message || "Failed to update soft stop loss."); }
  };

  /**
   * handleSaveProfitTaking — inline edit handler for the profit-taking cell.
   * Sends a PATCH to update the position's profit_taking target price.
   * An empty value clears the target (sends 0 which the backend maps to null).
   */
  const handleSaveProfitTaking = async (pos) => {
    const val = profitTakingInput.trim();
    const numVal = val === "" ? 0 : parseFloat(val);
    if (val !== "" && (isNaN(numVal) || numVal < 0)) { setGlobalErr("Profit taking must be a positive number or empty."); return; }
    try {
      const updated = await api.modifyPosition(pos.position_id, { profit_taking: numVal || 0 }, token);
      setPositions(prev => prev.map(p => p.position_id === pos.position_id ? updated : p));
      setEditingProfitTaking(null);
    } catch (e) { setGlobalErr(e.message || "Failed to update profit taking."); }
  };

  /**
   * handleExportCSV — generates a CSV from current positions + live quotes
   * and triggers a browser download.
   *
   * Columns: Name, Ticker, Type, Date, Qty, BEP, Price, Value, Gain/Loss,
   *          Gain%, Stop Loss, Group
   *
   * Uses sortedPositions (respects current section filter + sort) and the
   * quotes map for live pricing. No backend call required.
   */
  const handleExportCSV = () => {
    const header = ["Name","Ticker","Type","Date","Qty","BEP","Price","Value","Gain/Loss","Gain%","Hard Stop Loss","Soft Stop Loss","Profit Taking","Group"];
    const rows = sortedPositions.map(pos => {
      const q = quotes[pos.ticker];
      const price = q?.price;
      const qty = parseFloat(pos.quantity);
      const bep = parseFloat(pos.purchase_price);
      const value = price != null ? price * qty : null;
      const gainLoss = price != null ? (price - bep) * qty : null;
      const gainPct = gainLoss != null && bep * qty !== 0 ? (gainLoss / (bep * qty)) * 100 : null;
      const displayName = (pos.asset_type === "physical"
        ? (pos.name || METALS.find(m => m.symbol === pos.ticker)?.name || q?.name || pos.ticker)
        : (q?.name || pos.name || pos.ticker));
      return [
        displayName,
        pos.ticker,
        pos.asset_type || "stock",
        pos.purchase_date || "",
        qty,
        bep.toFixed(2),
        price != null ? price.toFixed(2) : "",
        value != null ? value.toFixed(2) : "",
        gainLoss != null ? gainLoss.toFixed(2) : "",
        gainPct != null ? gainPct.toFixed(2) + "%" : "",
        pos.hard_stop_loss ? parseFloat(pos.hard_stop_loss).toFixed(2) : "",
        pos.soft_stop_loss ? parseFloat(pos.soft_stop_loss).toFixed(2) : "",
        pos.profit_taking ? parseFloat(pos.profit_taking).toFixed(2) : "",
        pos.group_tag || "",
      ];
    });
    /* Escape CSV fields that contain commas, quotes, or newlines */
    const esc = (v) => {
      const s = String(v);
      return s.includes(",") || s.includes('"') || s.includes("\n") ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const csv = [header.map(esc).join(","), ...rows.map(r => r.map(esc).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const pName = (activePortfolio?.name || "portfolio").replace(/[^a-zA-Z0-9_-]/g, "_");
    a.href = url;
    a.download = `${pName}_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handlePortfolioCreated = (p) => {
    const next = [...portfolios, p];
    setPortfolios(next);
    setActivePortfolioId(p.portfolio_id);
    setShowCreate(false);
  };

  const handlePositionAdded = (pos) => {
    const next = [...positions, pos];
    setPositions(next);
    setShowAddModal(null);
    loadQuotes(next);
    loadPriceChanges(next, changePeriod);
    // Refresh portfolios to reflect updated cash_balance if deduct_cash was used
    loadPortfolios();
  };

  const handleImported = (imported) => {
    const next = [...positions, ...imported];
    setPositions(next);
    setShowImport(false);
    loadQuotes(next);
    loadPriceChanges(next, changePeriod);
  };

  const handleModified = (updated) => {
    setPositions(prev => prev.map(p => p.position_id === updated.position_id ? updated : p));
    setModifyPos(null);
  };

  const handleSold = (result) => {
    if (result === null) {
      setPositions(prev => prev.filter(p => p.position_id !== sellPos.position_id));
    } else {
      setPositions(prev => prev.map(p => p.position_id === result.position_id ? result : p));
    }
    setSellPos(null);
    // Refresh portfolio list so cash_balance is current
    loadPortfolios();
  };

  /**
   * handleDetailedScore — runs a detailed portfolio score with P&L per position.
   * Builds a positions array from current state (tickers with purchase_price,
   * stop_loss, profit_taking) and calls the extended scoring endpoint.
   */
  const handleDetailedScore = async () => {
    if (!activePortfolioId || !positions.length) return;
    setScoreLoading(true); setScoreResults(null);
    try {
      const positionItems = positions.map(p => ({
        ticker:         p.ticker,
        quantity:       parseFloat(p.quantity),
        purchase_price: parseFloat(p.purchase_price),
        hard_stop_loss: p.hard_stop_loss ? parseFloat(p.hard_stop_loss) : null,
        profit_taking:  p.profit_taking ? parseFloat(p.profit_taking) : null,
      }));
      const results = await api.scorePortfolioDetailed(positionItems, token);
      // response is PortfolioScoreResponse — extract the positions array
      setScoreResults(results.positions ?? []);
      setShowScoreModal(true);
    } catch (e) { setGlobalErr(e.message || "Scoring failed."); }
    finally { setScoreLoading(false); }
  };

  /**
   * handleAdjustCash — posts a manual cash balance adjustment.
   * Refreshes portfolios so the header shows the updated balance.
   */
  const handleAdjustCash = async () => {
    const amount = parseFloat(cashAmount);
    if (isNaN(amount) || amount === 0) return;
    setCashLoading(true);
    try {
      await api.adjustPortfolioCash(activePortfolioId, amount, cashNotes.trim() || null, token);
      setShowCashModal(false);
      setCashAmount(""); setCashNotes("");
      loadPortfolios();
    } catch (e) { setGlobalErr(e.message || "Cash adjustment failed."); }
    finally { setCashLoading(false); }
  };

  const showTypeCol  = (activeSection === "physical" || activeSection === "all") && visibleCols.has("type");
  const showGroupCol = activeSection !== "physical" && visibleCols.has("group");

  /* -- Render ------------------------------------------------------------- */
  return (
    <div className="page-scroll">
      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title">PORTFOLIO MANAGER</div>
          <div className="page-sub">
            {portfolios.length} PORTFOLIO{portfolios.length !== 1 ? "S" : ""}
            {activePortfolio && ` \u00B7 ${positions.length} POSITION${positions.length !== 1 ? "S" : ""}`}
          </div>
        </div>
        <div className="page-actions">
          <button className="btn btn-outline" onClick={() => setShowCreate(true)}>
            <Ic.plus /> NEW PORTFOLIO
          </button>
        </div>
      </div>

      {/* Global error */}
      {globalErr && (
        <div style={{ margin: "0 0 12px", padding: "8px 16px", background: "rgba(239,68,68,.08)", border: "1px solid rgba(239,68,68,.25)", borderRadius: 4, fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--red)" }}>
          {globalErr}
        </div>
      )}

      {/* Empty state */}
      {portfolios.length === 0 && !loadingPortfolios && (
        <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--c-muted)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
          No portfolios yet. Click <strong>NEW PORTFOLIO</strong> to get started.
        </div>
      )}

      {portfolios.length > 0 && (
        <>
          {/* Portfolio tab bar */}
          <div style={{ display: "flex", gap: 4, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
            {portfolios.map(p => (
              <button
                key={p.portfolio_id}
                onClick={() => setActivePortfolioId(p.portfolio_id)}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "6px 14px", borderRadius: 3, fontSize: 11,
                  fontFamily: "var(--font-mono)", letterSpacing: ".06em", fontWeight: 600,
                  cursor: "pointer", border: "1px solid",
                  borderColor: p.portfolio_id === activePortfolioId ? "var(--c-accent)" : "var(--c-border)",
                  background: p.portfolio_id === activePortfolioId ? "rgba(59,130,246,.12)" : "var(--c-surface)",
                  color: p.portfolio_id === activePortfolioId ? "var(--c-accent)" : "var(--c-muted)",
                  transition: "all .15s",
                }}
              >
                {p.name}
                <span
                  onClick={e => { e.stopPropagation(); handleDeletePortfolio(p.portfolio_id); }}
                  title="Delete portfolio"
                  style={{ opacity: .5, marginLeft: 2, lineHeight: 1, cursor: "pointer" }}
                >{"\u00D7"}</span>
              </button>
            ))}
          </div>

          {/* Active portfolio strategy + toolbar */}
          {activePortfolio && (
            <div style={{ marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
              <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--c-muted)", maxWidth: 600, lineHeight: 1.6 }}>
                {activePortfolio.strategy
                  ? <span style={{ color: "var(--c-text)" }}>{activePortfolio.strategy}</span>
                  : <span style={{ fontStyle: "italic" }}>No strategy description.</span>}
                {/* Cash balance display */}
                <span style={{ marginLeft: 16, color: "var(--c-accent)", fontWeight: 700 }}>
                  CASH: ${parseFloat(activePortfolio.cash_balance ?? 0).toFixed(2)}
                </span>
                <button
                  onClick={() => setShowCashModal(true)}
                  title="Adjust cash balance"
                  style={{ marginLeft: 6, background: "none", border: "1px solid var(--c-border)", borderRadius: 3, color: "var(--c-muted)", cursor: "pointer", fontSize: 11, fontFamily: "var(--font-mono)", padding: "1px 7px", lineHeight: 1.4 }}
                >+/−</button>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn btn-outline" onClick={handleDetailedScore} disabled={scoreLoading || !positions.length}>
                  {scoreLoading ? <span className="loading-pulse">SCORING...</span> : "DETAILED SCORE"}
                </button>
                <button className="btn btn-outline" onClick={() => setShowImport(true)}>
                  <Ic.upload /> IMPORT CSV
                </button>
                <button className="btn btn-outline" onClick={handleExportCSV} disabled={sortedPositions.length === 0}>
                  <Ic.download /> EXPORT CSV
                </button>
              </div>
            </div>
          )}

          {/* Summary strip (total across all sections) */}
          <div className="grid-stats stagger" style={{ marginBottom: 16 }}>
            {[
              { lbl: "TOTAL VALUE",     val: formatValue(summary.totalValue),  cls: "" },
              { lbl: "TOTAL COST",      val: formatValue(summary.totalCost),   cls: "" },
              { lbl: "GAIN / LOSS",     val: formatValue(summary.gainLoss, { showSign: true }),    cls: summary.gainLoss >= 0 ? "green" : "red" },
              { lbl: "RETURN",          val: fmtPct(summary.gainPct),     cls: summary.gainPct >= 0 ? "green" : "red" },
              { lbl: `${changePeriod} G/L`, val: <>{formatValue(summary.periodGL, { showSign: true })} <span style={{ fontSize: 10, opacity: .75 }}>({fmtPct(summary.periodPct)})</span></>, cls: summary.periodGL >= 0 ? "green" : "red" },
              { lbl: "ACTIVE POS.",     val: summary.count,               cls: "" },
              { lbl: "CASH",            val: formatValue(activePortfolio?.cash_balance ?? 0), cls: "amber" },
            ].map((s, i) => (
              <div key={i} className="stat-block">
                <div className="stat-lbl">{s.lbl}</div>
                <div className={`stat-val${s.cls ? " " + s.cls : ""}`}>{s.val}</div>
              </div>
            ))}
          </div>

          {/* Section tabs: STOCKS | CRYPTO | ETFs | PHYSICAL */}
          <div style={{ display: "flex", gap: 2, marginBottom: 16, borderBottom: "1px solid var(--c-border)", paddingBottom: 0 }}>
            {SECTIONS.map(s => (
              <button
                key={s.id}
                onClick={() => { setActiveSection(s.id); setSortCol(null); }}
                style={{
                  padding: "8px 16px", fontSize: 11,
                  fontFamily: "var(--font-mono)", letterSpacing: ".06em", fontWeight: 600,
                  cursor: "pointer", border: "none", borderBottom: "2px solid",
                  borderBottomColor: activeSection === s.id ? "var(--c-accent)" : "transparent",
                  background: "transparent",
                  color: activeSection === s.id ? "var(--c-accent)" : "var(--c-muted)",
                  transition: "all .15s",
                  marginBottom: -1,
                }}
              >
                {s.label}
                {sectionCounts[s.id] > 0 && (
                  <span style={{ marginLeft: 6, fontSize: 10, opacity: .7 }}>({sectionCounts[s.id]})</span>
                )}
              </button>
            ))}
          </div>

          {/* Section action bar */}
          {activeSection !== "all" && activeSection !== "trades" && activeSection !== "rules" && (
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
              <button className="btn btn-amber" onClick={() => setShowAddModal(activeSection)}>
                <Ic.plus /> ADD {SECTIONS.find(s => s.id === activeSection)?.label.replace(/s$/i, "") || "POSITION"}
              </button>
            </div>
          )}

          {/* Trade History panel — shown only when TRADE HISTORY tab is active */}
          {activeSection === "trades" && (
            <div className="panel page-inner stagger">
              <div className="panel-header">
                <span className="panel-title">TRADE HISTORY</span>
                {loadingTrades && <span style={{ fontSize: 11, color: "var(--c-muted)", marginLeft: 10 }} className="loading-pulse">LOADING...</span>}
              </div>

              {/* Realized P&L summary card */}
              {(() => {
                const sellTrades = trades.filter(tr => tr.trade_type === "SELL" && tr.cost_basis != null);
                const totalPnl = sellTrades.reduce((sum, tr) => sum + (parseFloat(tr.price) - parseFloat(tr.cost_basis)) * parseFloat(tr.quantity), 0);
                const profitable = sellTrades.filter(tr => (parseFloat(tr.price) - parseFloat(tr.cost_basis)) * parseFloat(tr.quantity) > 0).length;
                const losing = sellTrades.filter(tr => (parseFloat(tr.price) - parseFloat(tr.cost_basis)) * parseFloat(tr.quantity) < 0).length;
                const pnlColor = totalPnl > 0 ? "var(--green)" : totalPnl < 0 ? "var(--red)" : "var(--c-muted)";
                return (
                  <div style={{ display: "flex", alignItems: "center", gap: 24, padding: "10px 14px", marginBottom: 12, background: "rgba(255,255,255,0.03)", border: "1px solid var(--c-border)", borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 11 }}>
                    <div>
                      <span style={{ color: "var(--c-muted)", marginRight: 8 }}>REALIZED P&L</span>
                      <span style={{ color: pnlColor, fontWeight: 700, fontSize: 13 }}>
                        {sellTrades.length === 0 ? "—" : `${totalPnl >= 0 ? "+" : ""}$${Math.abs(totalPnl).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                      </span>
                    </div>
                    <div style={{ color: "var(--c-muted)" }}>|</div>
                    <div>
                      <span style={{ color: "var(--green)", marginRight: 4 }}>{profitable}</span>
                      <span style={{ color: "var(--c-muted)" }}>profitable</span>
                    </div>
                    <div>
                      <span style={{ color: "var(--red)", marginRight: 4 }}>{losing}</span>
                      <span style={{ color: "var(--c-muted)" }}>losing</span>
                    </div>
                    {sellTrades.length > 0 && (
                      <div style={{ color: "var(--c-muted)" }}>
                        {sellTrades.length} closed trade{sellTrades.length !== 1 ? "s" : ""}
                      </div>
                    )}
                  </div>
                );
              })()}

              <div style={{ overflowX: "auto" }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>DATE</th>
                      <th>TYPE</th>
                      <th>TICKER</th>
                      <th className="right">QTY</th>
                      <th className="right">PRICE</th>
                      <th className="right">TOTAL</th>
                      <th className="right">REALIZED P&L</th>
                      <th>NOTES</th>
                      <th>ACTIONS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.length === 0 && !loadingTrades && (
                      <tr>
                        <td colSpan={9} style={{ textAlign: "center", padding: "32px 0", color: "var(--c-muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          No trades recorded yet. Trades are logged when you buy or sell positions with cash integration enabled.
                        </td>
                      </tr>
                    )}
                    {trades.map(tr => (
                      <tr key={tr.trade_id} style={{ borderLeft: tr.trade_type === "BUY" ? "3px solid rgba(34,197,94,.35)" : "3px solid rgba(239,68,68,.35)" }}>
                        <td style={{ fontSize: 11, whiteSpace: "nowrap" }}>{fmtDate(tr.created_at)}</td>
                        <td>
                          <span style={{ fontWeight: 700, color: tr.trade_type === "BUY" ? "var(--green)" : "var(--red)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                            {tr.trade_type}
                          </span>
                        </td>
                        <td><span className="amber" style={{ fontWeight: 700 }}>{tr.ticker}</span></td>
                        <td className="right" style={{ fontVariantNumeric: "tabular-nums" }}>{fmtQty(parseFloat(tr.quantity))}</td>
                        <td className="right" style={{ fontVariantNumeric: "tabular-nums" }}>{formatValue(parseFloat(tr.price))}</td>
                        <td className="right" style={{ fontVariantNumeric: "tabular-nums" }}>{formatValue(parseFloat(tr.total_value))}</td>
                        <td className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                          {tr.trade_type === "SELL" && tr.cost_basis != null
                            ? (() => {
                                const pnl = (parseFloat(tr.price) - parseFloat(tr.cost_basis)) * parseFloat(tr.quantity);
                                const color = pnl >= 0 ? "var(--green)" : "var(--red)";
                                const sign = pnl >= 0 ? "+" : "-";
                                return (
                                  <span style={{ color, fontWeight: 600 }}>
                                    {sign}${Math.abs(pnl).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                  </span>
                                );
                              })()
                            : <span style={{ color: "var(--c-muted)" }}>&mdash;</span>
                          }
                        </td>
                        <td style={{ fontSize: 11, color: "var(--c-muted)" }}>{tr.notes || "\u2014"}</td>
                        <td style={{ textAlign: "center" }}>
                          {/* Delete trade button — removes record after confirmation */}
                          <button
                            onClick={() => handleDeleteTrade(tr.trade_id)}
                            title="Delete trade record"
                            style={{ background: "none", border: "none", color: "var(--red)", cursor: "pointer", fontSize: 14, padding: "0 4px" }}
                          >
                            ×
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Rules panel — shown only when RULES tab is active */}
          {activeSection === "rules" && (
            <div className="panel page-inner stagger">
              <div className="panel-header">
                <span className="panel-title">PORTFOLIO RULES</span>
                {loadingAlerts && <span className="loading-pulse" style={{ fontSize: 11, color: "var(--c-muted)", marginLeft: 10 }}>LOADING...</span>}
              </div>

              {/* Controls: run + schedule picker + refresh */}
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 12, padding: "0 2px" }}>
                <button
                  className="btn btn-amber"
                  onClick={handleRunRules}
                  disabled={runningRules || !activePortfolioId}
                >
                  {runningRules ? <span className="loading-pulse">RUNNING...</span> : "▶ RUN RULES"}
                </button>
                <select
                  value={rulesSchedule}
                  onChange={e => setRulesSchedule(e.target.value)}
                  style={{ background: "var(--c-surface)", border: "1px solid var(--c-border)", color: "var(--c-text)", fontFamily: "var(--font-mono)", fontSize: 11, borderRadius: 3, padding: "5px 8px", cursor: "pointer" }}
                >
                  <option value="on_demand">On demand</option>
                  <option value="market_hours">Auto — market hours</option>
                  <option value="end_of_day">Auto — end of day</option>
                </select>
                <button
                  className="btn btn-ghost"
                  onClick={() => loadRuleAlerts(activePortfolioId, alertSevFilter, alertStateFilter)}
                  style={{ marginLeft: "auto" }}
                >
                  ↻ REFRESH
                </button>
              </div>

              {/* Filter chips: severity + state */}
              <div style={{ display: "flex", gap: 6, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
                {[null, "critical", "warning", "info"].map(sev => {
                  const active = alertSevFilter === sev;
                  const color = sev === "critical" ? "var(--red)" : sev === "warning" ? "#f59e0b" : sev === "info" ? "var(--blue)" : "var(--c-accent)";
                  return (
                    <button
                      key={sev ?? "all_sev"}
                      onClick={() => { setAlertSevFilter(sev); loadRuleAlerts(activePortfolioId, sev, alertStateFilter); }}
                      style={{
                        padding: "3px 10px", fontSize: 10, fontFamily: "var(--font-mono)", borderRadius: 3,
                        cursor: "pointer", border: "1px solid",
                        borderColor: active ? color : "var(--c-border)",
                        background: active ? "rgba(255,255,255,0.05)" : "transparent",
                        color: active ? color : "var(--c-muted)",
                      }}
                    >
                      {sev ? sev.toUpperCase() : "ALL SEV"}
                    </button>
                  );
                })}
                <div style={{ width: 1, height: 16, background: "var(--c-border)" }} />
                {[null, "active", "snoozed", "actioned"].map(st => {
                  const active = alertStateFilter === st;
                  return (
                    <button
                      key={st ?? "all_st"}
                      onClick={() => { setAlertStateFilter(st); loadRuleAlerts(activePortfolioId, alertSevFilter, st); }}
                      style={{
                        padding: "3px 10px", fontSize: 10, fontFamily: "var(--font-mono)", borderRadius: 3,
                        cursor: "pointer", border: "1px solid",
                        borderColor: active ? "var(--c-accent)" : "var(--c-border)",
                        background: active ? "rgba(255,255,255,0.05)" : "transparent",
                        color: active ? "var(--c-accent)" : "var(--c-muted)",
                      }}
                    >
                      {st ? st.toUpperCase() : "ALL STATES"}
                    </button>
                  );
                })}
              </div>

              {/* Empty state */}
              {ruleAlerts.length === 0 && !loadingAlerts && (
                <div style={{ padding: "48px 20px", textAlign: "center", color: "var(--c-muted)", fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.7 }}>
                  No rule alerts found.<br />
                  <span style={{ fontSize: 11 }}>Click <strong style={{ color: "var(--c-text)" }}>▶ RUN RULES</strong> to analyze current positions.</span>
                </div>
              )}

              {/* Alert cards */}
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {ruleAlerts.map(alert => {
                  const sevColor = alert.severity === "critical" ? "var(--red)" : alert.severity === "warning" ? "#f59e0b" : "var(--cyan)";
                  const sevBg    = alert.severity === "critical" ? "rgba(240,68,56,.08)"  : alert.severity === "warning" ? "rgba(245,158,11,.08)" : "rgba(15,192,208,.06)";
                  const isActioned = alert.state === "actioned";
                  const isSnoozed  = alert.state === "snoozed";
                  return (
                    <div
                      key={alert.alert_id}
                      style={{
                        padding: "12px 14px", borderRadius: 4, border: "1px solid",
                        borderColor: isActioned || isSnoozed ? "var(--c-border)" : sevColor,
                        background: isActioned || isSnoozed ? "rgba(255,255,255,0.015)" : sevBg,
                        opacity: isActioned ? 0.5 : 1,
                        display: "flex", flexDirection: "column", gap: 6,
                        transition: "opacity .2s",
                      }}
                    >
                      {/* Header row */}
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <span className="amber" style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 13 }}>
                          {alert.ticker}
                        </span>
                        <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", padding: "1px 7px", borderRadius: 3, border: "1px solid var(--c-border)", color: "var(--c-muted)", textTransform: "uppercase", letterSpacing: ".04em" }}>
                          {(alert.rule_type || "").replace(/_/g, " ")}
                        </span>
                        <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", padding: "1px 7px", borderRadius: 3, border: `1px solid ${sevColor}`, color: sevColor, textTransform: "uppercase", letterSpacing: ".04em", marginLeft: "auto" }}>
                          {alert.severity}
                        </span>
                        {isSnoozed  && <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--c-muted)", padding: "1px 7px", border: "1px solid var(--c-border)", borderRadius: 3 }}>SNOOZED</span>}
                        {isActioned && <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--c-muted)", padding: "1px 7px", border: "1px solid var(--c-border)", borderRadius: 3 }}>ACTIONED</span>}
                      </div>

                      {/* Title */}
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--bright)", fontWeight: 600 }}>
                        {alert.title}
                      </div>

                      {/* Detail message */}
                      {alert.detail && (
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--c-text)", lineHeight: 1.6 }}>
                          {alert.detail}
                        </div>
                      )}

                      {/* Footer: timestamp + action buttons */}
                      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 2, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 10, color: "var(--c-muted)", fontFamily: "var(--font-mono)" }}>
                          {alert.triggered_at ? new Date(alert.triggered_at).toLocaleString() : ""}
                        </span>
                        {!isActioned && (
                          <>
                            {!isSnoozed && (
                              <button
                                onClick={() => handlePatchAlert(alert.alert_id, "snoozed")}
                                style={{ marginLeft: "auto", padding: "2px 10px", fontSize: 10, fontFamily: "var(--font-mono)", cursor: "pointer", background: "transparent", border: "1px solid var(--c-border)", borderRadius: 3, color: "var(--c-muted)" }}
                              >
                                SNOOZE
                              </button>
                            )}
                            <button
                              onClick={() => handlePatchAlert(alert.alert_id, "actioned")}
                              style={{ padding: "2px 10px", fontSize: 10, fontFamily: "var(--font-mono)", cursor: "pointer", background: "transparent", border: `1px solid ${sevColor}`, borderRadius: 3, color: sevColor, marginLeft: isSnoozed ? "auto" : undefined }}
                            >
                              MARK ACTIONED
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Positions table — hidden on TRADE HISTORY and RULES tabs */}
          {activeSection !== "trades" && activeSection !== "rules" && (
          <div className="panel page-inner stagger">
            <div className="panel-header">
              <span className="panel-title">{SECTIONS.find(s => s.id === activeSection)?.label || "POSITIONS"}</span>
              {loadingPositions && <span style={{ fontSize: 11, color: "var(--c-muted)", marginLeft: 10 }} className="loading-pulse">LOADING...</span>}
              {/* Column visibility picker — toggles optional columns */}
              {(() => {
                const OPTIONAL_COLS = [
                  { id: "50sma",           label: "50 SMA" },
                  { id: "hard_stop_loss",  label: "Hard Stop" },
                  { id: "soft_stop_loss",  label: "Soft Stop" },
                  { id: "profit_taking",   label: "Prof. Take" },
                  { id: "group",           label: "Group" },
                  { id: "type",            label: "Type" },
                  { id: "purchase_date",   label: "Date" },
                ];
                return (
                  <div style={{ position: "relative", display: "inline-block", marginLeft: "auto" }}>
                    <button
                      className="btn-ghost"
                      onClick={() => setShowColPicker(v => !v)}
                      style={{ fontSize: "10px", padding: "3px 8px", fontFamily: "var(--font-mono)", border: "1px solid var(--border)", cursor: "pointer", background: "transparent", color: "var(--muted)" }}
                    >
                      COLUMNS ▾
                    </button>
                    {showColPicker && (
                      <div className="col-picker-popover">
                        {OPTIONAL_COLS.map(({ id, label }) => (
                          <label key={id}>
                            <input
                              type="checkbox"
                              checked={visibleCols.has(id)}
                              onChange={() => toggleCol(id)}
                              style={{ accentColor: "var(--c-accent)", cursor: "pointer" }}
                            />
                            {label}
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>
            {/* Stale data banner — appears when quotes are older than 5 minutes */}
            {quotesStale && (
              <StaleDataBanner
                lastUpdated={quotesTimestamp}
                onRefresh={() => { setQuotesStale(false); loadQuotes(positions); }}
              />
            )}
            <div className="table-responsive" style={{ overflow: "auto", maxHeight: "calc(100vh - 320px)", position: "relative", zIndex: 1 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th title="Exclude from summary">EXC</th>
                    <SortTh label="NAME"   col="name"          sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    <SortTh label="TICKER" col="ticker"        sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    {showTypeCol && <th>TYPE</th>}
                    {visibleCols.has("purchase_date") && <SortTh label="DATE" col="purchase_date" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />}
                    <SortTh label="QTY"    col="quantity"      sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />
                    <SortTh label="BEP"    col="bep"           sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />
                    <SortTh label="PRICE"  col="price"         sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />
                    {visibleCols.has("50sma") && <SortTh label="50 SMA" col="sma50" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />}
                    <th className="right" style={{ whiteSpace: "nowrap", cursor: "default" }}>
                      SMA
                      <input
                        type="number" min="5" max="200" step="1"
                        value={customSmaPeriod}
                        onChange={e => { const v = parseInt(e.target.value); if (v >= 5 && v <= 200) setCustomSmaPeriod(v); }}
                        onClick={e => e.stopPropagation()}
                        style={{ marginLeft: 4, width: 42, background: "var(--c-surface)", border: "1px solid var(--c-border)", color: "var(--c-text)", fontFamily: "var(--font-mono)", fontSize: 10, borderRadius: 2, padding: "1px 3px", textAlign: "center" }}
                      />
                    </th>
                    {visibleCols.has("hard_stop_loss") && <SortTh label="HARD STOP"    col="hardstoploss" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />}
                    {visibleCols.has("soft_stop_loss") && <SortTh label="SOFT STOP"    col="softstoploss" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />}
                    {visibleCols.has("profit_taking")  && <SortTh label="PROFIT TAKING" col="profittaking" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />}
                    <th className="right" title="Allocation % relative to current view">ALLOC %</th>
                    <th className="right" onClick={() => handleSort("change")}
                      style={{ whiteSpace: "nowrap", cursor: "pointer", userSelect: "none" }}>
                      CHG
                      {sortCol === "change"
                        ? <span style={{ marginLeft: 4, opacity: .8 }}>{sortDir === "asc" ? "\u25B2" : "\u25BC"}</span>
                        : <span style={{ marginLeft: 4, opacity: .25 }}>{"\u21C5"}</span>}
                      <select
                        value={changePeriod}
                        onChange={e => setChangePeriod(e.target.value)}
                        onClick={e => e.stopPropagation()}
                        style={{ marginLeft: 4, background: "var(--c-surface)", border: "1px solid var(--c-border)", color: "var(--c-text)", fontFamily: "var(--font-mono)", fontSize: 10, borderRadius: 2, padding: "1px 3px", cursor: "pointer" }}
                      >
                        {["1D","1W","1M","3M","1Y"].map(p => <option key={p}>{p}</option>)}
                      </select>
                    </th>
                    <SortTh label="VALUE"    col="value"   sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />
                    <SortTh label="GAIN/LOSS" col="gainloss" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} right />
                    {showGroupCol && <th>GROUP</th>}
                    <th>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPositions.length === 0 && !loadingPositions && (
                    <tr>
                      <td colSpan={99} style={{ textAlign: "center", padding: "32px 0", color: "var(--c-muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                        {activeSection === "all"
                          ? "No positions yet. Switch to a category tab to add positions."
                          : `No ${SECTIONS.find(s => s.id === activeSection)?.label.toLowerCase()} positions. Click ADD to get started.`}
                      </td>
                    </tr>
                  )}
                  {sortedPositions.map(pos => {
                    const q        = quotes[pos.ticker];
                    const price    = q?.price;
                    const qty      = parseFloat(pos.quantity);
                    const bep      = parseFloat(pos.purchase_price);
                    const value    = price != null ? price * qty : null;
                    const gainLoss = price != null ? (price - bep) * qty : null;
                    const gainPct  = gainLoss != null ? (gainLoss / (bep * qty)) * 100 : null;
                    const changePct = priceChanges[pos.ticker];
                    const excluded = pos.is_excluded;

                    // For physical: show stored name or metal name
                    const posIsPhysical = (pos.asset_type || "stock") === "physical";
                    const displayName = posIsPhysical
                      ? (pos.name || METALS.find(m => m.symbol === pos.ticker)?.name || q?.name || pos.ticker)
                      : (q?.name || pos.name || null);

                    return (
                      <tr key={pos.position_id} style={{ opacity: excluded ? .45 : 1, transition: "opacity .15s" }}>
                        <td style={{ textAlign: "center" }}>
                          <input
                            type="checkbox"
                            checked={excluded}
                            onChange={() => handleToggleExclude(pos)}
                            title={excluded ? "Include in summary" : "Exclude from summary"}
                            style={{ cursor: "pointer", accentColor: "var(--c-accent)" }}
                          />
                        </td>

                        <td data-label="NAME" style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {displayName || <span style={{ color: "var(--c-muted)" }}>{"\u2014"}</span>}
                        </td>

                        <td data-label="TICKER"><span className="amber" style={{ fontWeight: 700 }}>{pos.ticker}</span></td>

                        {showTypeCol && (
                          <td data-label="TYPE" style={{ fontSize: 11, textTransform: "capitalize" }}>
                            {pos.physical_type || "\u2014"}
                          </td>
                        )}

                        {visibleCols.has("purchase_date") && (
                          <td data-label="DATE" style={{ whiteSpace: "nowrap", fontSize: 11 }}>{fmtDate(pos.purchase_date)}</td>
                        )}

                        <td data-label="QTY" className="right" style={{ fontVariantNumeric: "tabular-nums" }}>{fmtQty(qty)}</td>

                        <td data-label="BEP" className="right" style={{ fontVariantNumeric: "tabular-nums" }}>{formatValue(bep)}</td>

                        <td data-label="PRICE" className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                          {price != null ? formatValue(price) : <span className="loading-pulse" style={{ color: "var(--c-muted)", fontSize: 11 }}>...</span>}
                        </td>

                        {visibleCols.has("50sma") && (
                          <td data-label="50 SMA" className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                            {smaData[pos.ticker]?.[50] != null ? formatValue(smaData[pos.ticker][50]) : <span style={{ color: "var(--c-muted)", fontSize: 11 }}>...</span>}
                          </td>
                        )}

                        <td data-label="SMA N" className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                          {smaData[pos.ticker]?.[customSmaPeriod] != null ? formatValue(smaData[pos.ticker][customSmaPeriod]) : <span style={{ color: "var(--c-muted)", fontSize: 11 }}>...</span>}
                        </td>

                        {visibleCols.has("hard_stop_loss") && (
                        <td data-label="HARD STOP" className="right" style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                          {editingStopLoss === pos.position_id ? (
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                              <input
                                type="number" min="0" step="any"
                                value={stopLossInput}
                                onChange={e => setStopLossInput(e.target.value)}
                                onKeyDown={e => { if (e.key === "Enter") handleSaveStopLoss(pos); if (e.key === "Escape") setEditingStopLoss(null); }}
                                autoFocus
                                style={{ width: 72, background: "var(--c-surface)", border: "1px solid var(--c-border)", color: "var(--c-text)", fontFamily: "var(--font-mono)", fontSize: 11, borderRadius: 2, padding: "2px 4px", textAlign: "right" }}
                              />
                              <button onClick={() => handleSaveStopLoss(pos)} style={{ background: "none", border: "none", color: "var(--green)", cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }} title="Save">{"\u2713"}</button>
                              <button onClick={() => setEditingStopLoss(null)} style={{ background: "none", border: "none", color: "var(--red)", cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }} title="Cancel">{"\u2717"}</button>
                            </span>
                          ) : (
                            <span
                              onClick={() => { setEditingStopLoss(pos.position_id); setStopLossInput(pos.hard_stop_loss ? String(parseFloat(pos.hard_stop_loss)) : ""); }}
                              style={{ cursor: "pointer", color: pos.hard_stop_loss && price != null && price <= parseFloat(pos.hard_stop_loss) ? "var(--red)" : undefined, fontWeight: pos.hard_stop_loss && price != null && price <= parseFloat(pos.hard_stop_loss) ? 700 : undefined }}
                              title="Click to edit hard stop loss (DeGiro standing order)"
                            >
                              {pos.hard_stop_loss ? formatValue(parseFloat(pos.hard_stop_loss)) : <span style={{ color: "var(--c-muted)" }}>{"\u2014"}</span>}
                            </span>
                          )}
                        </td>
                        )}

                        {visibleCols.has("soft_stop_loss") && (
                        <td data-label="SOFT STOP" className="right" style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                          {editingSoftStopLoss === pos.position_id ? (
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                              <input
                                type="number" min="0" step="any"
                                value={softStopLossInput}
                                onChange={e => setSoftStopLossInput(e.target.value)}
                                onKeyDown={e => { if (e.key === "Enter") handleSaveSoftStopLoss(pos); if (e.key === "Escape") setEditingSoftStopLoss(null); }}
                                autoFocus
                                style={{ width: 72, background: "var(--c-surface)", border: "1px solid var(--c-border)", color: "var(--c-text)", fontFamily: "var(--font-mono)", fontSize: 11, borderRadius: 2, padding: "2px 4px", textAlign: "right" }}
                              />
                              <button onClick={() => handleSaveSoftStopLoss(pos)} style={{ background: "none", border: "none", color: "var(--green)", cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }} title="Save">{"\u2713"}</button>
                              <button onClick={() => setEditingSoftStopLoss(null)} style={{ background: "none", border: "none", color: "var(--red)", cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }} title="Cancel">{"\u2717"}</button>
                            </span>
                          ) : (
                            <span
                              onClick={() => { setEditingSoftStopLoss(pos.position_id); setSoftStopLossInput(pos.soft_stop_loss ? String(parseFloat(pos.soft_stop_loss)) : ""); }}
                              style={{ cursor: "pointer", color: pos.soft_stop_loss && price != null && price <= parseFloat(pos.soft_stop_loss) ? "var(--amber)" : undefined, fontWeight: pos.soft_stop_loss && price != null && price <= parseFloat(pos.soft_stop_loss) ? 700 : undefined }}
                              title="Click to edit soft stop loss (Telegram alert)"
                            >
                              {pos.soft_stop_loss ? formatValue(parseFloat(pos.soft_stop_loss)) : <span style={{ color: "var(--c-muted)" }}>{"\u2014"}</span>}
                            </span>
                          )}
                        </td>
                        )}

                        {/* Profit Taking — inline editable like Stop Loss */}
                        {visibleCols.has("profit_taking") && (
                        <td data-label="PROFIT TAKING" className="right" style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
                          {editingProfitTaking === pos.position_id ? (
                            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                              <input
                                type="number" min="0" step="any"
                                value={profitTakingInput}
                                onChange={e => setProfitTakingInput(e.target.value)}
                                onKeyDown={e => { if (e.key === "Enter") handleSaveProfitTaking(pos); if (e.key === "Escape") setEditingProfitTaking(null); }}
                                autoFocus
                                style={{ width: 72, background: "var(--c-surface)", border: "1px solid var(--c-border)", color: "var(--c-text)", fontFamily: "var(--font-mono)", fontSize: 11, borderRadius: 2, padding: "2px 4px", textAlign: "right" }}
                              />
                              <button onClick={() => handleSaveProfitTaking(pos)} style={{ background: "none", border: "none", color: "var(--green)", cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }} title="Save">{"\u2713"}</button>
                              <button onClick={() => setEditingProfitTaking(null)} style={{ background: "none", border: "none", color: "var(--red)", cursor: "pointer", padding: 0, fontSize: 14, lineHeight: 1 }} title="Cancel">{"\u2717"}</button>
                            </span>
                          ) : (
                            <span
                              onClick={() => { setEditingProfitTaking(pos.position_id); setProfitTakingInput(pos.profit_taking ? String(parseFloat(pos.profit_taking)) : ""); }}
                              style={{ cursor: "pointer", color: pos.profit_taking && price != null && price >= parseFloat(pos.profit_taking) ? "var(--green)" : undefined, fontWeight: pos.profit_taking && price != null && price >= parseFloat(pos.profit_taking) ? 700 : undefined }}
                              title="Click to edit profit taking target"
                            >
                              {pos.profit_taking ? formatValue(parseFloat(pos.profit_taking)) : <span style={{ color: "var(--c-muted)" }}>{"\u2014"}</span>}
                            </span>
                          )}
                        </td>
                        )}

                        {/* Allocation % — position value as percentage of section total */}
                        <td data-label="ALLOC %" className="right" style={{ fontVariantNumeric: "tabular-nums", fontSize: 11 }}>
                          {value != null && summary.totalValue > 0 && !excluded
                            ? fmtPct((value / summary.totalValue) * 100)
                            : <span style={{ color: "var(--c-muted)" }}>{"\u2014"}</span>}
                        </td>

                        <td data-label="CHG" className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                          {changePct != null
                            ? <span className={changePct >= 0 ? "green" : "red"}>
                                {formatValue(qty * price * changePct / (100 + changePct), { showSign: true })}
                                <span style={{ marginLeft: 4, fontSize: 10, opacity: .75 }}>({fmtPct(changePct)})</span>
                              </span>
                            : <span style={{ color: "var(--c-muted)", fontSize: 11 }}>...</span>}
                        </td>

                        <td data-label="VALUE" className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                          {value != null ? formatValue(value) : "\u2014"}
                        </td>

                        <td data-label="GAIN/LOSS" className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                          {gainLoss != null
                            ? <span className={gainLoss >= 0 ? "green" : "red"}>
                                {formatValue(gainLoss, { showSign: true })}
                                <span style={{ marginLeft: 4, fontSize: 10, opacity: .75 }}>({fmtPct(gainPct)})</span>
                              </span>
                            : "\u2014"}
                        </td>

                        {showGroupCol && (
                          <td data-label="GROUP" style={{ fontSize: 11, color: "var(--c-muted)" }}>
                            {pos.group_tag || "\u2014"}
                          </td>
                        )}

                        <td>
                          <div style={{ display: "flex", gap: 6 }}>
                            {/* Asset detail info button */}
                            <button
                              className="btn btn-ghost table-action-btn"
                              title="Asset details"
                              onClick={() => setDetailSymbol(pos.ticker)}
                              style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 15, padding: "3px 7px" }}
                            >{"\u24D8"}</button>
                            {/* Price alert button */}
                            <button
                              className="btn btn-ghost table-action-btn"
                              title="Set price alert"
                              onClick={() => { setAlertSymbol(pos.ticker); setAlertPrice(quotes[pos.ticker]?.price ?? null); }}
                              style={{ padding: "3px 7px", color: "#f59e0b" }}
                            ><Ic.bell /></button>
                            {onViewChart && (
                              <button
                                className="btn btn-ghost table-action-btn"
                                title="View chart"
                                onClick={() => onViewChart(pos.ticker)}
                                style={{ padding: "3px 7px" }}
                              ><Ic.charts /></button>
                            )}
                            {onViewNews && (
                              <button
                                className="btn btn-ghost table-action-btn"
                                title="View news"
                                onClick={() => onViewNews(pos.ticker)}
                                style={{ padding: "3px 7px" }}
                              ><Ic.newsSmall /></button>
                            )}
                            {onTradeAI && (
                              <button
                                className="btn btn-ghost table-action-btn"
                                title="Trade AI"
                                onClick={() => onTradeAI(pos.ticker)}
                                style={{ padding: "3px 7px", color: "var(--amber)" }}
                              ><Ic.trading /></button>
                            )}
                            <button
                              className="btn btn-ghost table-action-btn"
                              title="Modify"
                              onClick={() => setModifyPos(pos)}
                              style={{ padding: "3px 7px" }}
                            ><Ic.edit /></button>
                            <button
                              className="btn btn-ghost table-action-btn"
                              title="Sell"
                              onClick={() => setSellPos(pos)}
                              style={{ padding: "3px 7px", color: "var(--red)" }}
                            ><Ic.sell /></button>
                            <button
                              className="btn btn-ghost table-action-btn"
                              title="Delete"
                              onClick={() => handleDeletePosition(pos)}
                              style={{ padding: "3px 7px", color: "var(--red)" }}
                            ><Ic.trash /></button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          )}
        </>
      )}

      {/* Modals */}
      {showCreate && (
        <CreatePortfolioModal
          onClose={() => setShowCreate(false)}
          onCreated={handlePortfolioCreated}
          token={token}
        />
      )}
      {showAddModal === "stock" && activePortfolioId && (
        <AddStockModal
          portfolioId={activePortfolioId}
          portfolio={activePortfolio}
          onClose={() => setShowAddModal(null)}
          onAdded={handlePositionAdded}
          token={token}
        />
      )}
      {showAddModal === "crypto" && activePortfolioId && (
        <AddCryptoModal
          portfolioId={activePortfolioId}
          portfolio={activePortfolio}
          onClose={() => setShowAddModal(null)}
          onAdded={handlePositionAdded}
          token={token}
        />
      )}
      {showAddModal === "etf" && activePortfolioId && (
        <AddETFModal
          portfolioId={activePortfolioId}
          portfolio={activePortfolio}
          onClose={() => setShowAddModal(null)}
          onAdded={handlePositionAdded}
          token={token}
        />
      )}
      {showAddModal === "physical" && activePortfolioId && (
        <AddPhysicalModal
          portfolioId={activePortfolioId}
          portfolio={activePortfolio}
          onClose={() => setShowAddModal(null)}
          onAdded={handlePositionAdded}
          token={token}
        />
      )}
      {showImport && activePortfolioId && (
        <CSVImportModal
          portfolioId={activePortfolioId}
          onClose={() => setShowImport(false)}
          onImported={handleImported}
          token={token}
          assetType={activeSection}
          formatValue={formatValue}
        />
      )}
      {modifyPos && (
        <ModifyPositionModal
          position={modifyPos}
          onClose={() => setModifyPos(null)}
          onModified={handleModified}
          token={token}
        />
      )}
      {sellPos && (
        <SellPositionModal
          position={sellPos}
          portfolio={activePortfolio}
          onClose={() => setSellPos(null)}
          onSold={handleSold}
          onPortfolioRefresh={loadPortfolios}
          token={token}
        />
      )}
      {detailSymbol && (
        <AssetDetailPanel symbol={detailSymbol} token={token} onClose={() => setDetailSymbol(null)} />
      )}
      {alertSymbol && (
        <AlertModal
          symbol={alertSymbol}
          currentPrice={alertPrice}
          token={token}
          onClose={() => { setAlertSymbol(null); setAlertPrice(null); }}
          onCreated={() => {}}
        />
      )}

      {/* Score Results Modal */}
      {showScoreModal && scoreResults && (
        <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && setShowScoreModal(false)}>
          <div className="modal-box" style={{ maxWidth: 720, width: "95vw" }}>
            <div className="modal-top">
              <div className="modal-title">DETAILED PORTFOLIO SCORE</div>
              <button className="modal-close" onClick={() => setShowScoreModal(false)}><Ic.close /></button>
            </div>
            <div style={{ overflowX: "auto", maxHeight: "60vh", overflowY: "auto" }}>
              <table className="data-table" style={{ fontSize: 11 }}>
                <thead>
                  <tr>
                    <th>TICKER</th>
                    <th className="right">SCORE</th>
                    <th>SIGNAL</th>
                    <th className="right">UNREALIZED P&L</th>
                    <th className="right">P&L %</th>
                    <th>STOP STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {scoreResults.map(r => (
                    <tr key={r.symbol}>
                      <td><span className="amber" style={{ fontWeight: 700 }}>{r.symbol}</span></td>
                      <td className="right" style={{ fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>
                        <span style={{ color: r.score >= 70 ? "var(--green)" : r.score >= 40 ? "var(--c-accent)" : "var(--red)" }}>
                          {r.score != null ? r.score.toFixed(1) : "\u2014"}
                        </span>
                      </td>
                      <td style={{ fontSize: 10 }}>
                        <span style={{ color: r.signal === "BUY" ? "var(--green)" : r.signal === "SELL" ? "var(--red)" : "var(--c-muted)" }}>
                          {r.signal || "\u2014"}
                        </span>
                      </td>
                      <td className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                        {r.unrealized_pnl != null
                          ? <span className={r.unrealized_pnl >= 0 ? "green" : "red"}>
                              {r.unrealized_pnl >= 0 ? "+" : ""}{formatValue(r.unrealized_pnl)}
                            </span>
                          : <span style={{ color: "var(--c-muted)" }}>\u2014</span>}
                      </td>
                      <td className="right" style={{ fontVariantNumeric: "tabular-nums" }}>
                        {r.unrealized_pnl_pct != null
                          ? <span className={r.unrealized_pnl_pct >= 0 ? "green" : "red"}>
                              {fmtPct(r.unrealized_pnl_pct)}
                            </span>
                          : <span style={{ color: "var(--c-muted)" }}>\u2014</span>}
                      </td>
                      <td style={{ fontSize: 10, color: r.stop_loss_recommendation?.startsWith("TRIGGERED") ? "var(--red)" : r.stop_loss_recommendation?.startsWith("WARNING") ? "var(--amber)" : "var(--c-muted)" }}>
                        {r.stop_loss_recommendation || "\u2014"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setShowScoreModal(false)}>CLOSE</button>
            </div>
          </div>
        </div>
      )}

      {/* Cash Adjustment Modal */}
      {showCashModal && (
        <div className="modal-overlay" style={BDK} onClick={e => e.target === e.currentTarget && setShowCashModal(false)}>
          <div className="modal-box" style={{ maxWidth: 400 }}>
            <div className="modal-top">
              <div className="modal-title">ADJUST CASH BALANCE</div>
              <button className="modal-close" onClick={() => setShowCashModal(false)}><Ic.close /></button>
            </div>
            <div className="modal-body">
              <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--c-muted)", marginBottom: 12 }}>
                Current balance: <span style={{ color: "var(--c-accent)", fontWeight: 700 }}>
                  ${parseFloat(activePortfolio?.cash_balance ?? 0).toFixed(2)}
                </span>
                <br />Use positive value to deposit, negative to withdraw.
              </div>
              <div className="form-field">
                <label className="form-label">Amount *</label>
                <input className="form-control" type="number" step="any" placeholder="e.g. 1000 or -500"
                  value={cashAmount} onChange={e => setCashAmount(e.target.value)} autoFocus />
              </div>
              <div className="form-field">
                <label className="form-label">Notes (optional)</label>
                <textarea className="form-control" placeholder="e.g. Initial deposit, dividend, etc."
                  value={cashNotes} onChange={e => setCashNotes(e.target.value)} rows={2}
                  style={{ resize: "vertical", minHeight: 52, fontFamily: "var(--font-mono)", fontSize: 12 }} />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setShowCashModal(false)}>CANCEL</button>
              <button className="btn btn-amber" onClick={handleAdjustCash} disabled={cashLoading || !cashAmount}>
                {cashLoading ? <span className="loading-pulse">SAVING...</span> : "APPLY"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
