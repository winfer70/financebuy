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

function AssetTypeBadge({ type }) {
  const def = ASSET_TYPES.find(t => t.value === type) || ASSET_TYPES[0];
  return <span className={`asset-type-badge ${def.cls}`}>{def.label}</span>;
}

function ImportPage({ addToast, goBack }) {
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
