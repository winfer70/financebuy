/**
 * InsiderPage.jsx — Browse ingested Form 4 filings with sortable columns
 * and a per-person transaction breakdown panel.
 */

import { useState, useEffect, useCallback } from "react";
import api from "../api/client";
import { Ic } from "../components/common/Icons";
import Pagination from "../components/common/Pagination";

const PAGE_SIZES = [25, 50, 100];
const CODE_FILTERS = [
  { id: "all", label: "ALL" },
  { id: "P", label: "BUYS" },
  { id: "S", label: "SELLS" },
];
const DAY_FILTERS = [
  { id: 30, label: "30D" },
  { id: 90, label: "90D" },
  { id: 180, label: "180D" },
  { id: 365, label: "1Y" },
];

const COLUMNS = [
  { key: "transaction_date", label: "TRADE DATE" },
  { key: "ticker", label: "TICKER" },
  { key: "owner_name", label: "OWNER" },
  { key: "transaction_code", label: "CODE" },
  { key: "shares", label: "SHARES" },
  { key: "price", label: "PRICE" },
  { key: "notional", label: "NOTIONAL" },
  { key: "stake_pct", label: "STAKE %" },
];

// SEC Form 4 transaction codes — https://www.sec.gov/about/forms/form4data.pdf
const CODE_LABELS = {
  P: "Open market or private purchase",
  S: "Open market or private sale",
  A: "Grant, award, or other acquisition",
  D: "Sale or transfer to the issuer",
  F: "Tax withholding (shares withheld to pay tax on a vest)",
  M: "Exercise or conversion of a derivative security",
  G: "Gift",
  C: "Conversion of a derivative security",
  V: "Transaction voluntarily reported earlier than required",
  I: "Discretionary transaction under Rule 16b-3",
  J: "Other acquisition or disposition (see filing footnotes)",
  U: "Disposition pursuant to a tender offer",
  W: "Acquisition or disposition by will or the laws of descent",
  Z: "Deposit into or withdrawal from a voting trust",
  X: "Exercise of an in-the-money or at-the-money option",
  K: "Transaction in an equity swap or other derivative",
  H: "Expiration of a short derivative position",
  E: "Expiration of a long derivative position",
  O: "Exercise of an out-of-the-money option",
};
const CODE_LEGEND_TITLE = Object.entries(CODE_LABELS)
  .map(([code, label]) => `${code} — ${label}`)
  .join("\n");

function codeTitle(code) {
  const c = (code || "").toUpperCase();
  return CODE_LABELS[c] ? `${c} — ${CODE_LABELS[c]}` : code;
}

/** API dates arrive as "YYYY-MM-DD"; render as "DD-MM-YYYY". */
function fmtDate(v) {
  if (!v) return "—";
  const s = String(v).slice(0, 10);
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return s;
  const [, y, mo, d] = m;
  return `${d}-${mo}-${y}`;
}

function fmtNum(v, digits = 0) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits > 0 ? Math.min(2, digits) : 0,
  });
}

function fmtMoney(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function fmtPct(v) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  return (Number(v) * 100).toFixed(2) + "%";
}

function roleLabel(row) {
  const bits = [];
  if (row.is_officer) bits.push(row.officer_title || "Officer");
  if (row.is_director) bits.push("Director");
  return bits.join(" · ") || "—";
}

export function InsiderPage({ token, onViewChart }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [ticker, setTicker] = useState("");
  const [code, setCode] = useState("all");
  const [days, setDays] = useState(90);
  const [sort, setSort] = useState("transaction_date");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const [owner, setOwner] = useState(null);
  const [ownerLoading, setOwnerLoading] = useState(false);
  const [ownerError, setOwnerError] = useState(null);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getInsiderFilings(token, {
        ticker: ticker.trim() || null,
        code: code === "all" ? null : code,
        days,
        sort,
        order,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(e.message || "Failed to load Form 4 filings");
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [token, ticker, code, days, sort, order, page, pageSize]);

  useEffect(() => { load(); }, [load]);

  const onSort = (key) => {
    if (sort === key) {
      setOrder((o) => (o === "asc" ? "desc" : "asc"));
    } else {
      setSort(key);
      setOrder(key === "owner_name" || key === "ticker" ? "asc" : "desc");
    }
    setPage(1);
  };

  const openOwner = async (row) => {
    if (!row.owner_cik) return;
    setOwnerLoading(true);
    setOwnerError(null);
    try {
      const data = await api.getInsiderOwner(row.owner_cik, token, {
        ticker: row.ticker,
        days: Math.max(days, 365),
      });
      setOwner(data);
    } catch (e) {
      setOwnerError(e.message || "Owner breakdown unavailable");
      setOwner(null);
    } finally {
      setOwnerLoading(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="page-content" style={{ display: "flex", flexDirection: "column", gap: 14, height: "100%", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ margin: 0, fontFamily: "'Bebas Neue',sans-serif", fontSize: 28, letterSpacing: 2, color: "var(--text)" }}>
          FORM 4
        </h1>
        <span style={{ fontFamily: "'IBM Plex Mono',monospace", fontSize: 11, color: "var(--mid)" }}>
          {total.toLocaleString()} filings · ingested EDGAR
        </span>
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 4, padding: "4px 8px" }}>
          <Ic.search />
          <input
            value={ticker}
            onChange={(e) => { setTicker(e.target.value.toUpperCase()); setPage(1); }}
            placeholder="TICKER"
            style={{
              background: "transparent", border: "none", outline: "none",
              color: "var(--text)", fontFamily: "'IBM Plex Mono',monospace", fontSize: 12, width: 80,
            }}
          />
        </div>

        <div style={{ display: "flex", gap: 4 }}>
          {CODE_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => { setCode(f.id); setPage(1); }}
              style={{
                fontFamily: "'IBM Plex Mono',monospace", fontSize: 10, letterSpacing: 0.8,
                padding: "5px 10px", borderRadius: 3, cursor: "pointer",
                border: "1px solid var(--border)",
                background: code === f.id ? "rgba(15,125,64,0.15)" : "var(--bg3)",
                color: code === f.id ? "var(--green)" : "var(--mid)",
              }}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: 4 }}>
          {DAY_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => { setDays(f.id); setPage(1); }}
              style={{
                fontFamily: "'IBM Plex Mono',monospace", fontSize: 10, letterSpacing: 0.8,
                padding: "5px 10px", borderRadius: 3, cursor: "pointer",
                border: "1px solid var(--border)",
                background: days === f.id ? "rgba(61,126,245,0.15)" : "var(--bg3)",
                color: days === f.id ? "#3d7ef5" : "var(--mid)",
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: 14, flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", border: "1px solid var(--border)", borderRadius: 4, overflow: "hidden", background: "var(--bg2)" }}>
          {error && (
            <div style={{ padding: 12, color: "var(--red)", fontFamily: "'IBM Plex Mono',monospace", fontSize: 12 }}>{error}</div>
          )}
          <div style={{ overflow: "auto", flex: 1 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono',monospace", fontSize: 11 }}>
              <thead>
                <tr style={{ position: "sticky", top: 0, background: "var(--bg3)", zIndex: 1 }}>
                  {COLUMNS.map((c) => (
                    <th
                      key={c.key}
                      onClick={() => onSort(c.key)}
                      title={c.key === "transaction_code" ? `Transaction codes:\n${CODE_LEGEND_TITLE}` : undefined}
                      style={{
                        textAlign: "left", padding: "8px 10px", cursor: "pointer",
                        color: sort === c.key ? "var(--green)" : "var(--mid)",
                        borderBottom: "1px solid var(--border)", letterSpacing: 0.6, whiteSpace: "nowrap",
                      }}
                    >
                      {c.label}{c.key === "transaction_code" ? " ⓘ" : ""}{sort === c.key ? (order === "asc" ? " ↑" : " ↓") : ""}
                    </th>
                  ))}
                  <th style={{ padding: "8px 10px", borderBottom: "1px solid var(--border)", color: "var(--mid)" }}>10b5-1</th>
                  <th style={{ padding: "8px 10px", borderBottom: "1px solid var(--border)", color: "var(--mid)" }} />
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={10} style={{ padding: 20, color: "var(--mid)" }}>Loading…</td></tr>
                )}
                {!loading && items.length === 0 && (
                  <tr><td colSpan={10} style={{ padding: 20, color: "var(--mid)" }}>No Form 4 rows in this window.</td></tr>
                )}
                {!loading && items.map((row) => {
                  const sell = (row.transaction_code || "").toUpperCase() === "S";
                  return (
                    <tr
                      key={row.filing_id}
                      style={{ borderBottom: "1px solid var(--border)", cursor: row.owner_cik ? "pointer" : "default" }}
                      onClick={() => openOwner(row)}
                    >
                      <td style={{ padding: "7px 10px", color: "var(--text)" }}>{fmtDate(row.transaction_date)}</td>
                      <td style={{ padding: "7px 10px" }}>
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); onViewChart?.(row.ticker); }}
                          style={{
                            background: "none", border: "none", cursor: "pointer", padding: 0,
                            color: "var(--green)", fontFamily: "inherit", fontSize: "inherit", fontWeight: 600,
                          }}
                        >
                          {row.ticker}
                        </button>
                      </td>
                      <td style={{ padding: "7px 10px", color: "var(--text)", maxWidth: 180 }}>
                        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.owner_name || "—"}</div>
                        <div style={{ color: "var(--mid)", fontSize: 10 }}>{roleLabel(row)}</div>
                      </td>
                      <td
                        title={codeTitle(row.transaction_code)}
                        style={{ padding: "7px 10px", color: sell ? "var(--red)" : "var(--green)", fontWeight: 600, cursor: "help" }}
                      >
                        {row.transaction_code}
                      </td>
                      <td style={{ padding: "7px 10px", color: "var(--text)" }}>{fmtNum(row.shares, 0)}</td>
                      <td style={{ padding: "7px 10px", color: "var(--text)" }}>{row.price != null ? "$" + fmtNum(row.price, 2) : "—"}</td>
                      <td style={{ padding: "7px 10px", color: "var(--text)" }}>{fmtMoney(row.notional)}</td>
                      <td style={{ padding: "7px 10px", color: "var(--text)" }}>{fmtPct(row.stake_pct)}</td>
                      <td style={{ padding: "7px 10px", color: "var(--mid)" }}>
                        {row.is_10b5_1 === true ? "Y" : row.is_10b5_1 === false ? "N" : "—"}
                      </td>
                      <td style={{ padding: "7px 10px" }}>
                        {row.filing_url && (
                          <a
                            href={row.filing_url}
                            target="_blank"
                            rel="noreferrer"
                            onClick={(e) => e.stopPropagation()}
                            style={{ color: "#3d7ef5", textDecoration: "none" }}
                          >
                            SEC
                          </a>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div style={{ borderTop: "1px solid var(--border)", padding: "6px 10px" }}>
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPrev={() => setPage((p) => Math.max(1, p - 1))}
              onNext={() => setPage((p) => Math.min(totalPages, p + 1))}
              perPage={pageSize}
              perPageOptions={PAGE_SIZES}
              onPerPageChange={(s) => { setPageSize(s); setPage(1); }}
            />
          </div>
        </div>

        <aside style={{
          width: 340, flexShrink: 0, border: "1px solid var(--border)", borderRadius: 4,
          background: "var(--bg2)", padding: 14, overflow: "auto",
          fontFamily: "'IBM Plex Mono',monospace", fontSize: 11,
        }}>
          <div style={{ color: "var(--mid)", letterSpacing: 1, marginBottom: 10 }}>PERSON BREAKDOWN</div>
          {ownerLoading && <div style={{ color: "var(--mid)" }}>Loading…</div>}
          {ownerError && <div style={{ color: "var(--red)" }}>{ownerError}</div>}
          {!ownerLoading && !owner && !ownerError && (
            <div style={{ color: "var(--mid)", lineHeight: 1.5 }}>
              Click a filing row to see that insider&apos;s buy/sell mix, cadence, and 10b5-1 share over the window.
            </div>
          )}
          {owner && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div>
                <div style={{ color: "var(--text)", fontSize: 13, fontWeight: 600 }}>{owner.owner_name || owner.owner_cik}</div>
                <div style={{ color: "var(--mid)" }}>{owner.officer_title || "—"} · CIK {owner.owner_cik}</div>
                {owner.ticker && <div style={{ color: "var(--green)", marginTop: 4 }}>{owner.ticker}</div>}
              </div>
              <div style={{ color: "var(--mid)", fontSize: 10, lineHeight: 1.4 }}>
                Acquired/disposed across all filing types (grants, exercises, withholding — not just open-market trades).
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <Stat label="ACQUIRED" value={`${owner.buy_count} / ${fmtNum(owner.buy_shares)} sh`} color="var(--green)" />
                <Stat label="DISPOSED" value={`${owner.sell_count} / ${fmtNum(owner.sell_shares)} sh`} color="var(--red)" />
                <Stat label="ACQ $" value={fmtMoney(owner.buy_notional)} />
                <Stat label="DISP $" value={fmtMoney(owner.sell_notional)} />
                <Stat label="NET SH" value={fmtNum(owner.net_shares)} color={owner.net_shares >= 0 ? "var(--green)" : "var(--red)"} />
                <Stat label="10b5-1" value={owner.pct_10b5_1 != null ? `${(owner.pct_10b5_1 * 100).toFixed(0)}%` : "—"} />
                <Stat label="SELL GAP" value={owner.avg_sell_interval_days != null ? `${owner.avg_sell_interval_days.toFixed(0)}d` : "—"} />
                <Stat label="WINDOW" value={`${owner.window_days}d`} />
              </div>
              {owner.track_record && (
                <div style={{
                  background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 4,
                  padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6,
                }}>
                  <div style={{ color: "var(--mid)", letterSpacing: 1, fontSize: 10 }}>TRACK RECORD &amp; OUTLOOK</div>
                  {owner.track_record.win_rate != null && (
                    <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                      <span style={{
                        fontWeight: 600, fontSize: 13,
                        color: owner.track_record.win_rate >= 0.65 ? "var(--green)"
                          : owner.track_record.win_rate <= 0.35 ? "var(--red)" : "var(--text)",
                      }}>
                        {(owner.track_record.win_rate * 100).toFixed(0)}% hit rate
                      </span>
                      <span style={{ color: "var(--mid)" }}>
                        avg {owner.track_record.avg_aligned_return_pct >= 0 ? "+" : ""}
                        {owner.track_record.avg_aligned_return_pct.toFixed(1)}% / {owner.track_record.horizon_days}d
                        {" "}({owner.track_record.evaluated} trade{owner.track_record.evaluated === 1 ? "" : "s"} scored)
                      </span>
                    </div>
                  )}
                  <div style={{ color: "var(--text)", lineHeight: 1.5 }}>{owner.track_record.label}</div>
                  <div style={{ color: "var(--mid)", fontSize: 9, fontStyle: "italic" }}>
                    {owner.track_record.basis} Historical pattern, not a guarantee of future performance.
                  </div>
                </div>
              )}
              <div style={{ color: "var(--mid)", letterSpacing: 1, marginTop: 4 }}>TRANSACTIONS</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {(owner.transactions || []).slice().reverse().map((t, i) => (
                  <div key={`${t.accession}-${i}`} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 6 }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <span
                        title={codeTitle(t.transaction_code)}
                        style={{ color: (t.transaction_code || "").toUpperCase() === "S" ? "var(--red)" : "var(--green)", cursor: "help" }}
                      >
                        {t.transaction_code} {t.ticker}
                      </span>
                      <span style={{ color: "var(--mid)" }}>{fmtDate(t.transaction_date)}</span>
                    </div>
                    <div style={{ color: "var(--text)" }}>
                      {fmtNum(t.shares)} sh @ {t.price != null ? "$" + fmtNum(t.price, 2) : "—"} · {fmtMoney(t.notional)}
                    </div>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setOwner(null)}
                style={{
                  marginTop: 8, background: "var(--bg3)", border: "1px solid var(--border)",
                  color: "var(--mid)", padding: "6px 10px", cursor: "pointer", borderRadius: 3,
                  fontFamily: "inherit", fontSize: 11,
                }}
              >
                CLOSE
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={{ background: "var(--bg3)", border: "1px solid var(--border)", borderRadius: 3, padding: "6px 8px" }}>
      <div style={{ color: "var(--mid)", fontSize: 9, letterSpacing: 0.8 }}>{label}</div>
      <div style={{ color: color || "var(--text)", marginTop: 2 }}>{value}</div>
    </div>
  );
}
