/**
 * Import Page
 * 
 * Allows users to import transaction/holding data from CSV files.
 * Includes data validation and preview before submission.
 */

import { useState, useRef, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";

const EMPTY_ENTRY = () => ({
  id: Date.now() + Math.random(),
  type: "Stock",
  identifier: "",
  qty: "",
  purchasePrice: "",
  datePurchased: "",
});

const IMPORT_CSS = `
/* ── Import page layout ── */
.import-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.import-subnav {
  background: var(--bg2); border-bottom: 1px solid var(--border);
  padding: 0 24px; display: flex; gap: 0;
}
.import-tab {
  padding: 12px 20px; font-family: var(--font-mono); font-size: 11px;
  font-weight: 500; color: var(--muted); cursor: pointer; border: none;
  background: none; letter-spacing: 0.8px; text-transform: uppercase;
  border-bottom: 2px solid transparent; margin-bottom: -1px;
  transition: all 0.12s;
}
.import-tab:hover { color: var(--text); }
.import-tab.active { color: var(--amber); border-bottom-color: var(--amber); }

/* ── Broker cards ── */
.broker-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px; padding: 24px;
}
.broker-card {
  background: var(--panel); border: 1px solid var(--border);
  padding: 20px; cursor: pointer;
  transition: all 0.15s; position: relative; overflow: hidden;
}
.broker-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0;
  width: 2px; background: var(--border); transition: background 0.15s;
}
.broker-card:hover { border-color: var(--border2); }
.broker-card:hover::before { background: var(--amber); }
.broker-card.selected { border-color: var(--amber); background: rgba(15,125,64,0.04); }
.broker-card.selected::before { background: var(--amber); }
.broker-logo-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.broker-logo {
  width: 40px; height: 40px; border-radius: 2px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-disp); font-size: 14px; font-weight: 700;
  flex-shrink: 0; letter-spacing: 0.5px;
}
.broker-name { font-family: var(--font-sans); font-size: 15px; font-weight: 600; color: var(--bright); }
.broker-type { font-family: var(--font-mono); font-size: 10px; color: var(--muted); margin-top: 2px; letter-spacing: 0.5px; }
.broker-desc { font-family: var(--font-mono); font-size: 11px; color: var(--mid); line-height: 1.5; margin-bottom: 12px; }
.broker-formats { display: flex; gap: 6px; flex-wrap: wrap; }
.format-chip {
  font-family: var(--font-mono); font-size: 9px; font-weight: 600;
  padding: 2px 7px; letter-spacing: 0.8px; text-transform: uppercase;
  border: 1px solid var(--border2); color: var(--mid); border-radius: 1px;
}
.broker-download-area {
  background: var(--bg2); border: 1px solid var(--border);
  margin: 0 24px 24px;
}
.broker-dl-header {
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.broker-dl-title { font-family: var(--font-disp); font-size: 20px; color: var(--amber); letter-spacing: 1px; }
.broker-dl-body { padding: 20px 18px; display: flex; flex-direction: column; gap: 16px; }
.dl-step {
  display: flex; gap: 14px; align-items: flex-start;
}
.dl-step-num {
  width: 24px; height: 24px; border-radius: 1px;
  background: rgba(15,125,64,0.1); border: 1px solid rgba(15,125,64,0.25);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-mono); font-size: 11px; font-weight: 600; color: var(--amber);
  flex-shrink: 0; margin-top: 1px;
}
.dl-step-text { font-family: var(--font-mono); font-size: 12px; color: var(--text); line-height: 1.6; }
.dl-step-text a { color: var(--amber); text-decoration: none; }
.dl-step-text code {
  background: var(--bg3); border: 1px solid var(--border);
  padding: 1px 5px; font-size: 11px; color: var(--cyan);
}
.drop-zone {
  border: 1px dashed var(--border2); padding: 28px;
  text-align: center; cursor: pointer; transition: all 0.15s;
  background: var(--bg3);
}
.drop-zone:hover, .drop-zone.drag-over {
  border-color: var(--amber); background: rgba(15,125,64,0.04);
}
.drop-zone-icon { font-family: var(--font-mono); font-size: 11px; color: var(--muted); margin-top: 8px; }
.drop-zone-sub { font-family: var(--font-mono); font-size: 10px; color: var(--muted); margin-top: 4px; }
.upload-progress { height: 2px; background: var(--border); margin-top: 8px; overflow: hidden; }
.upload-progress-bar { height: 100%; background: var(--amber); transition: width 0.3s; }
.file-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; background: var(--bg3); border: 1px solid var(--border);
  font-family: var(--font-mono); font-size: 11px;
}
.file-name { flex: 1; color: var(--text); }
.file-size { color: var(--muted); }
.file-status-ok { color: var(--green); display: flex; align-items: center; gap: 4px; }
.file-status-err { color: var(--red); }

/* ── Manual import form ── */
.manual-form-wrap { padding: 24px; display: flex; flex-direction: column; gap: 20px; max-width: 900px; }
.manual-entries-table {
  background: var(--panel); border: 1px solid var(--border);
}
.manual-entries-header {
  padding: 10px 16px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
}
.entry-row-form {
  display: grid;
  grid-template-columns: 140px 1fr 80px 120px 120px 140px 40px;
  gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--border);
  align-items: center;
}
.entry-row-form:last-child { border-bottom: none; }
.entry-data-row {
  display: grid;
  grid-template-columns: 140px 1fr 80px 120px 120px 140px 40px;
  gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--border);
  align-items: center; font-family: var(--font-mono); font-size: 12px;
  transition: background 0.08s;
}
.entry-data-row:hover { background: rgba(255,255,255,0.02); }
.entry-data-row:last-child { border-bottom: none; }
.entry-th {
  font-family: var(--font-mono); font-size: 9px; font-weight: 500;
  color: var(--muted); letter-spacing: 1px; text-transform: uppercase;
}
.entry-form-input {
  background: var(--bg3); border: 1px solid var(--border);
  padding: 6px 8px; font-family: var(--font-mono); font-size: 11px;
  color: var(--bright); outline: none; width: 100%; border-radius: 2px;
  transition: border-color 0.1s;
}
.entry-form-input:focus { border-color: var(--amber); }
.entry-form-input::placeholder { color: var(--muted); }
select.entry-form-input {
  appearance: none; cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg width='8' height='5' viewBox='0 0 8 5' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l3 3 3-3' stroke='%234a5568' strokeWidth='1.2'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 7px center;
  padding-right: 20px;
}
select.entry-form-input option { background: var(--bg3); }
.asset-type-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-family: var(--font-mono); font-size: 10px; font-weight: 600;
  padding: 2px 7px; border-radius: 1px; text-transform: uppercase; letter-spacing: 0.5px;
}
.at-stock   { color: #3d7ef5; background: rgba(61,126,245,0.08); border: 1px solid rgba(61,126,245,0.2); }
.at-crypto  { color: #0f7d40; background: rgba(15,125,64,0.08); border: 1px solid rgba(15,125,64,0.2); }
.at-metalsphisical  { color: #fbbf24; background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.2); }
.at-metalsetf { color: #0fc0d0; background: rgba(15,192,208,0.08); border: 1px solid rgba(15,192,208,0.2); }
.delete-row-btn {
  background: none; border: none; cursor: pointer; color: var(--muted);
  display: flex; align-items: center; justify-content: center;
  transition: color 0.1s; width: 28px; height: 28px;
  border-radius: 2px;
}
.delete-row-btn:hover { color: var(--red); background: rgba(240,68,56,0.08); }
.import-summary-bar {
  background: var(--bg2); border: 1px solid var(--border);
  padding: 16px 18px; display: flex; gap: 24px; align-items: center;
}
.summary-stat { display: flex; flex-direction: column; gap: 3px; }
.summary-lbl { font-family: var(--font-mono); font-size: 9px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; }
.summary-val { font-family: var(--font-mono); font-size: 16px; font-weight: 600; color: var(--bright); }
.confirm-actions { display: flex; gap: 10px; margin-left: auto; align-items: center; }

/* ── Portfolio review ── */
.review-wrap { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.review-section-title {
  font-family: var(--font-mono); font-size: 10px; font-weight: 500;
  color: var(--muted); letter-spacing: 1.5px; text-transform: uppercase;
  padding-bottom: 8px; border-bottom: 1px solid var(--border);
}
.review-empty {
  text-align: center; padding: 48px; color: var(--muted);
  font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.5px;
}
.review-empty-title {
  font-family: var(--font-disp); font-size: 28px; color: var(--muted);
  letter-spacing: 2px; margin-bottom: 8px;
}
`;

const BROKER_LIST = [
  {
    id: "robinhood", name: "Robinhood", short: "RH", color: "#00c805", bg: "#003d01",
    type: "US Equities & Crypto", formats: ["CSV"],
    desc: "Export account history from Settings → Account → History & Statements",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Robinhood Web</a>' },
      { text: 'Go to <code>Account → Statements & History</code>' },
      { text: 'Select date range and click <code>Download CSV</code>' },
      { text: 'Upload the downloaded file below' },
    ],
    cols: "Date, Type, Symbol, Shares, Price, Amount",
  },
  {
    id: "ibkr", name: "IBKR", short: "IB", color: "#c8282a", bg: "#3d0a0b",
    type: "Multi-asset Global Broker", formats: ["CSV", "XML", "PDF"],
    desc: "Interactive Brokers Flex Query exports detailed trade history",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">IBKR Client Portal</a>' },
      { text: 'Go to <code>Reports → Statements → Flex Queries</code>' },
      { text: 'Create a new Flex Query or use the default <code>Activity Statement</code>' },
      { text: 'Run query, select CSV format, and download' },
    ],
    cols: "TradeDate, Symbol, Quantity, TradePrice, IBCommission, AssetClass",
  },
  {
    id: "etrade", name: "E*TRADE", short: "ET", color: "#6633cc", bg: "#1a0d33",
    type: "US Equities & Options", formats: ["CSV", "OFX"],
    desc: "E*TRADE provides full trade history exports from the Brokerage account section",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">E*TRADE</a> and go to <code>Accounts</code>' },
      { text: 'Select <code>Documents → Brokerage Tax Documents</code>' },
      { text: 'Choose <code>Trade Confirmations</code> and date range' },
      { text: 'Click <code>Export to CSV</code> and upload below' },
    ],
    cols: "TransactionDate, SecurityType, Symbol, Quantity, Price, Amount",
  },
  {
    id: "td", name: "TD Ameritrade", short: "TD", color: "#00a651", bg: "#003118",
    type: "US Full-Service Broker", formats: ["CSV", "OFX", "QFX"],
    desc: "Schwab (formerly TD Ameritrade) exports trade history with full OHLCV data",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Schwab/TDA</a>' },
      { text: 'Navigate to <code>History & Statements → Transactions</code>' },
      { text: 'Set date range and select <code>Export to Spreadsheet (.csv)</code>' },
      { text: 'Upload the downloaded CSV file below' },
    ],
    cols: "DATE, TRANSACTION TYPE, SECURITY, QUANTITY, PRICE, AMOUNT",
  },
  {
    id: "coinbase", name: "Coinbase", short: "CB", color: "#0052ff", bg: "#000f3d",
    type: "Cryptocurrency Exchange", formats: ["CSV"],
    desc: "Full transaction history including buys, sells, transfers, staking rewards",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Coinbase</a>' },
      { text: 'Go to <code>Profile → Statements</code>' },
      { text: 'Under <code>Transaction History</code>, select date range' },
      { text: 'Click <code>Generate Report</code> then download CSV' },
    ],
    cols: "Timestamp, Transaction Type, Asset, Quantity Transacted, Spot Price, Subtotal",
  },
  {
    id: "binance", name: "Binance", short: "BN", color: "#f0b90b", bg: "#2d2200",
    type: "Global Crypto Exchange", formats: ["CSV", "XLSX"],
    desc: "Export full order history, P&L reports, and tax statements from Binance",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Binance</a>' },
      { text: 'Go to <code>Orders → Trade History</code>' },
      { text: 'Select date range (max 3 months per export)' },
      { text: 'Click <code>Export Complete Trade History</code> → CSV' },
    ],
    cols: "Date, Pair, Side, Price, Executed, Amount, Fee",
  },
  {
    id: "schwab", name: "Charles Schwab", short: "CS", color: "#1b7ee0", bg: "#051d35",
    type: "US Full-Service Broker", formats: ["CSV", "OFX", "QFX"],
    desc: "Download detailed position history and trade confirmations from Schwab",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Schwab</a>' },
      { text: 'Go to <code>Accounts → History</code>' },
      { text: 'Filter transactions by date range and type' },
      { text: 'Click <code>Export</code> and choose CSV format' },
    ],
    cols: "Date, Action, Symbol, Description, Quantity, Price, Amount",
  },
  {
    id: "fidelity", name: "Fidelity", short: "FD", color: "#009b49", bg: "#002d15",
    type: "US Full-Service Broker", formats: ["CSV", "OFX"],
    desc: "Download account history and tax documents directly from Fidelity NetBenefits",
    steps: [
      { text: 'Log into <a href="#" onClick="return false">Fidelity</a>' },
      { text: 'Go to <code>Accounts & Trade → Portfolio</code>' },
      { text: 'Select <code>Activity & Orders → History</code>' },
      { text: 'Click <code>Download</code> and select CSV format' },
    ],
    cols: "Run Date, Action, Symbol, Description, Type, Quantity, Price, Amount",
  },
];

const ASSET_TYPES = [
  { value: "Stock",           label: "STOCK",            cls: "at-stock" },
  { value: "Crypto",          label: "CRYPTO",           cls: "at-crypto" },
  { value: "MetalsPhisical",  label: "METALS PHYSICAL",  cls: "at-metalsphisical" },
  { value: "MetalsETF",       label: "METALS ETF",       cls: "at-metalsetf" },
];

function AssetTypeBadge({ type }) {
  const def = ASSET_TYPES.find(t => t.value === type) || ASSET_TYPES[0];
  return <span className={`asset-type-badge ${def.cls}`}>{def.label}</span>;
}

export function ImportPage({ addToast, goBack }) {
  const [subpage, setSubpage] = useState("brokers");
  const [selectedBroker, setSelectedBroker] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [entries, setEntries] = useState([EMPTY_ENTRY()]);
  const [savedEntries, setSavedEntries] = useState([]);
  const [importedFromBroker, setImportedFromBroker] = useState([]);
  const fileRef = useRef(null);

  // ── File upload simulation ──────────────────────────────────────────────
  const simulateUpload = (fileName, fileSize) => {
    setUploading(true);
    setUploadProgress(0);
    const interval = setInterval(() => {
      setUploadProgress(p => {
        if (p >= 100) {
          clearInterval(interval);
          setUploading(false);
          const rows = Math.floor(Math.random() * 200) + 40;
          setUploadedFiles(prev => [...prev, {
            name: fileName, size: fileSize,
            rows, broker: selectedBroker?.name || "Unknown", ok: true,
          }]);
          addToast && addToast(`FILE PARSED · ${rows} TRANSACTIONS IMPORTED FROM ${fileName.toUpperCase()}`);
          // Simulate broker-imported portfolio entries
          const mockImported = [
            { id: Date.now()+1, type:"Stock", identifier:"AAPL", qty:"10", purchasePrice:"142.30", datePurchased:"2024-03-15", source: selectedBroker?.name },
            { id: Date.now()+2, type:"Stock", identifier:"NVDA", qty:"5",  purchasePrice:"480.00", datePurchased:"2024-06-20", source: selectedBroker?.name },
            { id: Date.now()+3, type:"Crypto", identifier:"BTC",  qty:"0.25",purchasePrice:"42000", datePurchased:"2024-01-10", source: selectedBroker?.name },
          ];
          setImportedFromBroker(prev => [...prev, ...mockImported]);
          return 100;
        }
        return p + 12;
      });
    }, 150);
  };

  const handleDrop = e => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) simulateUpload(file.name, `${(file.size / 1024).toFixed(1)} KB`);
  };

  const handleFileInput = e => {
    const file = e.target.files[0];
    if (file) simulateUpload(file.name, `${(file.size / 1024).toFixed(1)} KB`);
  };

  // ── Manual entries management ───────────────────────────────────────────
  const updateEntry = (id, field, value) => {
    setEntries(es => es.map(e => e.id === id ? { ...e, [field]: value } : e));
  };
  const addEntry = () => setEntries(es => [...es, EMPTY_ENTRY()]);
  const deleteEntry = id => setEntries(es => es.filter(e => e.id !== id));

  const isEntryValid = e => e.identifier.trim() && e.qty && e.purchasePrice && e.datePurchased;
  const validEntries = entries.filter(isEntryValid);

  const saveEntries = () => {
    if (validEntries.length === 0) return;
    setSavedEntries(prev => [...prev, ...validEntries.map(e => ({...e, source:"Manual"}))]);
    setEntries([EMPTY_ENTRY()]);
    addToast && addToast(`${validEntries.length} POSITION${validEntries.length > 1 ? "S" : ""} ADDED TO PORTFOLIO`);
    setSubpage("review");
  };

  const totalSaved = savedEntries.length + importedFromBroker.length;
  const totalValue = [...savedEntries, ...importedFromBroker].reduce((s, e) => {
    return s + (parseFloat(e.qty) || 0) * (parseFloat(e.purchasePrice) || 0);
  }, 0);

  const fmtCurrency = v => "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div className="page-scroll">
      <style>{IMPORT_CSS}</style>

      {/* Page header */}
      <div className="page-header">
        <div>
          <div className="page-title"><button className="btn btn-ghost" onClick={goBack} style={{padding:"4px 6px",marginRight:8,verticalAlign:"middle"}}><Ic.back/></button>IMPORT PORTFOLIO</div>
          <div className="page-sub">DOWNLOAD BROKER STATEMENTS · MANUAL ENTRY · PORTFOLIO REVIEW</div>
        </div>
        <div className="page-actions">
          {totalSaved > 0 && (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--amber)", display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--amber)", display: "inline-block" }} />
              {totalSaved} POSITIONS STAGED
            </div>
          )}
          <button className="btn btn-outline" onClick={() => setSubpage("manual")}>
            <Ic.file /> MANUAL ENTRY
          </button>
          <button className="btn btn-amber" onClick={() => setSubpage("review")}>
            <Ic.import /> REVIEW & COMMIT
          </button>
        </div>
      </div>

      {/* Sub-navigation */}
      <div className="import-subnav">
        {[
          { id: "brokers", label: "Broker Statements" },
          { id: "manual",  label: "Manual Import" },
          { id: "review",  label: `Portfolio Review${totalSaved > 0 ? ` (${totalSaved})` : ""}` },
        ].map(t => (
          <button key={t.id} className={`import-tab${subpage === t.id ? " active" : ""}`}
            onClick={() => setSubpage(t.id)}>{t.label}</button>
        ))}
      </div>

      {/* ── BROKERS SUBPAGE ── */}
      {subpage === "brokers" && (
        <div style={{ flex: 1, overflow: "auto" }}>
          <div style={{ padding: "16px 24px 0", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
            SELECT YOUR BROKER TO SEE EXPORT INSTRUCTIONS AND UPLOAD YOUR STATEMENT FILE
          </div>

          {/* Broker grid */}
          <div className="broker-grid">
            {BROKER_LIST.map(b => (
              <div key={b.id}
                className={`broker-card${selectedBroker?.id === b.id ? " selected" : ""}`}
                onClick={() => setSelectedBroker(b)}>
                <div className="broker-logo-row">
                  <div className="broker-logo" style={{ background: b.bg, color: b.color }}>
                    {b.short}
                  </div>
                  <div>
                    <div className="broker-name">{b.name}</div>
                    <div className="broker-type">{b.type}</div>
                  </div>
                  {selectedBroker?.id === b.id && (
                    <div style={{ marginLeft: "auto", color: "var(--amber)", display: "flex" }}>
                      <Ic.check />
                    </div>
                  )}
                </div>
                <div className="broker-desc">{b.desc}</div>
                <div className="broker-formats">
                  {b.formats.map(f => <div key={f} className="format-chip">{f}</div>)}
                </div>
              </div>
            ))}
          </div>

          {/* Selected broker instructions + upload */}
          {selectedBroker && (
            <div className="broker-download-area">
              <div className="broker-dl-header">
                <div>
                  <div className="broker-dl-title">{selectedBroker.name.toUpperCase()} · EXPORT GUIDE</div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", marginTop: 3 }}>
                    SUPPORTED COLUMNS: {selectedBroker.cols}
                  </div>
                </div>
                <button className="btn btn-ghost" onClick={() => setSelectedBroker(null)}
                  style={{ fontSize: 9, padding: "4px 10px" }}>CLOSE</button>
              </div>
              <div className="broker-dl-body">
                {/* Steps */}
                {selectedBroker.steps.map((step, i) => (
                  <div key={i} className="dl-step">
                    <div className="dl-step-num">{i + 1}</div>
                    <div className="dl-step-text" dangerouslySetInnerHTML={{ __html: step.text }} />
                  </div>
                ))}

                {/* Drop zone */}
                <div className="drop-zone"
                  onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleDrop}
                  onClick={() => fileRef.current?.click()}
                  style={{ borderColor: dragOver ? "var(--amber)" : undefined }}>
                  <div style={{ fontSize: 28 }}>
                    <Ic.upload />
                  </div>
                  <div className="drop-zone-icon">
                    DROP {selectedBroker.formats.join(" / ")} FILE HERE OR CLICK TO BROWSE
                  </div>
                  <div className="drop-zone-sub">Max 50MB · {selectedBroker.formats.join(", ")} formats accepted</div>
                  {uploading && (
                    <div className="upload-progress">
                      <div className="upload-progress-bar" style={{ width: `${uploadProgress}%` }} />
                    </div>
                  )}
                </div>
                <input ref={fileRef} type="file" accept=".csv,.xlsx,.xml,.ofx,.qfx"
                  style={{ display: "none" }} onChange={handleFileInput} />

                {/* Uploaded files */}
                {uploadedFiles.map((f, i) => (
                  <div key={i} className="file-row">
                    <div style={{ color: "var(--amber)", display: "flex" }}><Ic.file /></div>
                    <div className="file-name">{f.name}</div>
                    <div className="file-size">{f.size}</div>
                    <div className="file-status-ok"><Ic.check /> {f.rows} transactions</div>
                    <button
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--muted)", marginLeft: "auto", display: "flex" }}
                      onClick={() => setUploadedFiles(p => p.filter((_, j) => j !== i))}>
                      <Ic.trash />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── MANUAL IMPORT SUBPAGE ── */}
      {subpage === "manual" && (
        <div style={{ flex: 1, overflow: "auto" }}>
          <div className="manual-form-wrap">
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
              MANUALLY ENTER POSITIONS. REQUIRED FIELDS: TYPE · IDENTIFIER · QTY · PURCHASE PRICE · DATE PURCHASED
            </div>

            {/* Entries table */}
            <div className="manual-entries-table">
              <div className="manual-entries-header">
                <span className="panel-title">POSITION ENTRIES</span>
                <button className="btn btn-ghost" style={{ fontSize: 9, padding: "4px 10px" }} onClick={addEntry}>
                  <Ic.plus /> ADD ROW
                </button>
              </div>

              {/* Header row */}
              <div className="entry-row-form" style={{ background: "var(--bg2)", paddingTop: 8, paddingBottom: 8 }}>
                {["ASSET TYPE", "IDENTIFIER / SYMBOL", "QUANTITY", "PURCHASE PRICE", "DATE PURCHASED", "NOTES", ""].map((h, i) => (
                  <div key={i} className="entry-th">{h}</div>
                ))}
              </div>

              {/* Entry rows */}
              {entries.map((entry) => (
                <div key={entry.id} className="entry-row-form">
                  {/* Type */}
                  <select className="entry-form-input" value={entry.type}
                    onChange={e => updateEntry(entry.id, "type", e.target.value)}>
                    {ASSET_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>

                  {/* Identifier */}
                  <input className="entry-form-input" placeholder={
                    entry.type === "Crypto" ? "BTC, ETH, SOL…" :
                    entry.type === "MetalsPhisical" ? "Gold 1oz Bar, Silver Coin…" :
                    entry.type === "MetalsETF" ? "GLD, SLV, GOLD…" :
                    "AAPL, MSFT, TSLA…"
                  }
                    value={entry.identifier}
                    onChange={e => updateEntry(entry.id, "identifier", e.target.value.toUpperCase())} />

                  {/* Quantity */}
                  <input className="entry-form-input" type="number" placeholder="0.00"
                    min="0" step="any" value={entry.qty}
                    onChange={e => updateEntry(entry.id, "qty", e.target.value)} />

                  {/* Purchase price */}
                  <div style={{ position: "relative" }}>
                    <span style={{ position: "absolute", left: 8, top: "50%", transform: "translateY(-50%)", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)", pointerEvents: "none" }}>$</span>
                    <input className="entry-form-input" type="number" placeholder="0.00"
                      style={{ paddingLeft: 18 }} min="0" step="any"
                      value={entry.purchasePrice}
                      onChange={e => updateEntry(entry.id, "purchasePrice", e.target.value)} />
                  </div>

                  {/* Date */}
                  <input className="entry-form-input" type="date"
                    value={entry.datePurchased}
                    max={new Date().toISOString().split("T")[0]}
                    onChange={e => updateEntry(entry.id, "datePurchased", e.target.value)} />

                  {/* Notes (optional) */}
                  <input className="entry-form-input" placeholder="Optional notes…"
                    value={entry.notes || ""}
                    onChange={e => updateEntry(entry.id, "notes", e.target.value)} />

                  {/* Delete */}
                  <button className="delete-row-btn" onClick={() => deleteEntry(entry.id)}>
                    <Ic.trash />
                  </button>
                </div>
              ))}
            </div>

            {/* Summary + save */}
            <div className="import-summary-bar">
              <div className="summary-stat">
                <div className="summary-lbl">TOTAL ROWS</div>
                <div className="summary-val">{entries.length}</div>
              </div>
              <div className="summary-stat">
                <div className="summary-lbl">VALID ROWS</div>
                <div className="summary-val" style={{ color: validEntries.length > 0 ? "var(--green)" : "var(--muted)" }}>
                  {validEntries.length}
                </div>
              </div>
              <div className="summary-stat">
                <div className="summary-lbl">STAGED COST BASIS</div>
                <div className="summary-val" style={{ color: "var(--amber)" }}>
                  {fmtCurrency(validEntries.reduce((s, e) =>
                    s + (parseFloat(e.qty) || 0) * (parseFloat(e.purchasePrice) || 0), 0))}
                </div>
              </div>
              <div className="confirm-actions">
                <button className="btn btn-ghost" onClick={addEntry}><Ic.plus /> ADD ROW</button>
                <button className="btn btn-outline" onClick={() => setEntries([EMPTY_ENTRY()])}>
                  CLEAR ALL
                </button>
                <button className="btn btn-amber"
                  disabled={validEntries.length === 0}
                  onClick={saveEntries}
                  style={{ opacity: validEntries.length === 0 ? 0.4 : 1, cursor: validEntries.length === 0 ? "not-allowed" : "pointer" }}>
                  <Ic.check /> SAVE {validEntries.length > 0 ? `${validEntries.length} ` : ""}POSITIONS
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── REVIEW SUBPAGE ── */}
      {subpage === "review" && (
        <div style={{ flex: 1, overflow: "auto" }}>
          <div className="review-wrap">
            {/* Summary stats */}
            <div className="grid-stats stagger" style={{ margin: 0 }}>
              {[
                { lbl: "Total Positions",  val: totalSaved,               cls: totalSaved > 0 ? "amber" : "" },
                { lbl: "Cost Basis",       val: fmtCurrency(totalValue),  cls: "" },
                { lbl: "Stocks",           val: [...savedEntries, ...importedFromBroker].filter(e => e.type === "Stock").length, cls: "" },
                { lbl: "Crypto",           val: [...savedEntries, ...importedFromBroker].filter(e => e.type === "Crypto").length, cls: "" },
                { lbl: "Metals",           val: [...savedEntries, ...importedFromBroker].filter(e => e.type === "MetalsPhisical" || e.type === "MetalsETF").length, cls: "" },
              ].map((s, i) => (
                <div key={i} className="stat-block">
                  <div className="stat-lbl">{s.lbl}</div>
                  <div className={`stat-val${s.cls ? " " + s.cls : ""}`}>{s.val}</div>
                </div>
              ))}
            </div>

            {totalSaved === 0 ? (
              <div className="review-empty">
                <div className="review-empty-title">NO POSITIONS STAGED</div>
                Import from a broker or add positions manually
              </div>
            ) : (
              <>
                {/* Broker imported */}
                {importedFromBroker.length > 0 && (
                  <div className="panel">
                    <div className="panel-header">
                      <span className="panel-title">IMPORTED FROM BROKER STATEMENTS</span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                        {importedFromBroker.length} POSITIONS
                      </span>
                    </div>
                    <ReviewTable
                      entries={importedFromBroker}
                      onDelete={id => setImportedFromBroker(p => p.filter(e => e.id !== id))}
                    />
                  </div>
                )}

                {/* Manually entered */}
                {savedEntries.length > 0 && (
                  <div className="panel">
                    <div className="panel-header">
                      <span className="panel-title">MANUALLY ENTERED POSITIONS</span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
                        {savedEntries.length} POSITIONS
                      </span>
                    </div>
                    <ReviewTable
                      entries={savedEntries}
                      onDelete={id => setSavedEntries(p => p.filter(e => e.id !== id))}
                    />
                  </div>
                )}

                {/* Commit button */}
                <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, paddingBottom: 24 }}>
                  <button className="btn btn-outline" onClick={() => {
                    setSavedEntries([]); setImportedFromBroker([]);
                    addToast && addToast("PORTFOLIO CLEARED");
                  }}>CLEAR ALL</button>
                  <button className="btn btn-amber" onClick={() => {
                    addToast && addToast(`${totalSaved} POSITIONS COMMITTED TO PORTFOLIO · SYNC COMPLETE`);
                  }}>
                    <Ic.check /> COMMIT {totalSaved} POSITIONS TO PORTFOLIO
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewTable({ entries, onDelete }) {
  const fmtCurrency = v => "$" + parseFloat(v || 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="data-table">
        <thead>
          <tr>
            <th>TYPE</th>
            <th>IDENTIFIER</th>
            <th className="right">QUANTITY</th>
            <th className="right">PURCHASE PRICE</th>
            <th className="right">COST BASIS</th>
            <th>DATE</th>
            <th>SOURCE</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {entries.map(e => {
            const cost = (parseFloat(e.qty) || 0) * (parseFloat(e.purchasePrice) || 0);
            return (
              <tr key={e.id}>
                <td><AssetTypeBadge type={e.type} /></td>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div className="sym-badge">{(e.identifier || "?").slice(0, 3)}</div>
                    <span style={{ fontWeight: 600, color: "var(--bright)" }}>{e.identifier || "—"}</span>
                  </div>
                </td>
                <td className="right">{parseFloat(e.qty || 0).toLocaleString()}</td>
                <td className="right">{fmtCurrency(e.purchasePrice)}</td>
                <td className="right" style={{ color: "var(--amber)", fontWeight: 600 }}>{fmtCurrency(cost)}</td>
                <td style={{ color: "var(--muted)" }}>{e.datePurchased || "—"}</td>
                <td>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--mid)" }}>
                    {e.source || "Manual"}
                  </span>
                </td>
                <td>
                  <button className="delete-row-btn" onClick={() => onDelete(e.id)}><Ic.trash /></button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
