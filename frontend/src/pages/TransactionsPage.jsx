/**
 * Transactions Page
 * 
 * Displays transaction history with filtering and detailed information.
 */

import { useState, useMemo } from "react";
import { useApi } from "../api/client";
import { Ic } from "../components/common/Icons";
import { SkeletonRow, ApiError } from "../components/common";
import { TRANSACTIONS } from "../styles/globals";

export function TransactionsPage({ onNewTx, token, accountId, goBack }) {
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");

  const { data: apiTxns, loading, error, refetch } =
    useApi(() => (token && accountId) ? api.listTransactions(accountId, token) : Promise.resolve(null), [token, accountId]);

  const allTxns = apiTxns || [];

  const filtered = useMemo(()=>{
    let r = allTxns;
    const type = t => t.transaction_type || t.type;
    if (filter!=="all") r = r.filter(t => type(t) === filter);
    if (search) r = r.filter(t => {
      const id = t.reference_number || t.id || String(t.transaction_id||"");
      return id.toLowerCase().includes(search.toLowerCase());
    });
    return r;
  },[filter, search, allTxns]);

  const totals = {
    total:    allTxns.reduce((s,t)=>s+(+t.amount||0),0),
    deposits: allTxns.filter(t=>(t.transaction_type||t.type)==="deposit").reduce((s,t)=>s+(+t.amount||0),0),
    buys:     allTxns.filter(t=>(t.transaction_type||t.type)==="buy").reduce((s,t)=>s+(+t.amount||0),0),
  };

  return (
    <div className="page-scroll">
      <div className="page-header">
        <div>
          <div className="page-title"><button className="btn btn-ghost" onClick={goBack} style={{padding:"4px 6px",marginRight:8,verticalAlign:"middle"}}><Ic.back/></button>TRANSACTIONS</div>
          <div className="page-sub">{allTxns.length} RECORDS · {accountId ? accountId.toString().slice(0,18) : "ACC-4821"}</div>
        </div>
        <div className="page-actions">
          <button className="btn btn-outline"><Ic.filter/> EXPORT CSV</button>
          <button className="btn btn-amber" onClick={onNewTx}><Ic.plus/> NEW TRANSACTION</button>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid-stats stagger">
        {[
          {lbl:"Total Volume",    val:`$${(totals.total/1000).toFixed(2)}K`,    cls:"amber"},
          {lbl:"Total Deposits",  val:`$${(totals.deposits/1000).toFixed(2)}K`, cls:""},
          {lbl:"Total Buys",      val:`$${(totals.buys/1000).toFixed(2)}K`,     cls:""},
          {lbl:"Completed",       val:allTxns.filter(t=>t.status==="completed").length, cls:"green"},
          {lbl:"Pending",         val:allTxns.filter(t=>t.status==="pending").length,   cls:"amber"},
        ].map((s,i)=>(
          <div key={i} className="stat-block">
            <div className="stat-lbl">{s.lbl}</div>
            <div className={`stat-val${s.cls?" "+s.cls:""}`}>{s.val}</div>
          </div>
        ))}
      </div>

      <div className="page-inner stagger">
        {error && <ApiError message={error} onRetry={refetch}/>}
        {/* Filter + search bar */}
        <div style={{display:"flex",gap:12,alignItems:"center"}}>
          <div className="filter-bar">
            {["all","deposit","withdrawal","buy","sell"].map(f=>(
              <button key={f} className={`filter-btn${filter===f?" active":""}`} onClick={()=>setFilter(f)}>
                {f}
              </button>
            ))}
          </div>
          <div style={{marginLeft:"auto",display:"flex",alignItems:"center",gap:8}}>
            <Ic.search/>
            <input className="search-input" placeholder="Search by ID or symbol..." value={search} onChange={e=>setSearch(e.target.value)}/>
          </div>
        </div>

        {/* Table */}
        <div className="panel">
          <div style={{overflowX:"auto"}}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>TXN ID</th>
                  <th>TYPE</th>
                  <th>SYMBOL</th>
                  <th className="right">AMOUNT</th>
                  <th>CURRENCY</th>
                  <th>ACCOUNT</th>
                  <th>STATUS</th>
                  <th>DATE</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  Array.from({length:5}).map((_,i)=><SkeletonRow key={i} cols={8}/>)
                ) : filtered.length === 0 ? (
                  <tr><td colSpan={8} style={{textAlign:"center",color:"var(--muted)",padding:"32px"}}>
                    NO TRANSACTIONS FOUND
                  </td></tr>
                ) : filtered.map(tx=>(
                  <tr key={tx.transaction_id||tx.id}>
                    <td style={{fontWeight:500,color:"var(--amber)",fontSize:11}}>{tx.reference_number||tx.id||String(tx.transaction_id||"").slice(0,8)}</td>
                    <td><span className={`type-chip tc-${tx.transaction_type||tx.type}`}>{tx.transaction_type||tx.type}</span></td>
                    <td><span style={{color:"var(--muted)"}}>—</span></td>
                    <td className="right">
                      <span style={{color:"var(--bright)",fontWeight:500}}>
                        ${(+tx.amount||0).toLocaleString("en-US",{minimumFractionDigits:2})}
                      </span>
                    </td>
                    <td style={{color:"var(--muted)"}}>{tx.currency||"USD"}</td>
                    <td style={{color:"var(--muted)",fontSize:11}}>{tx.acct||String(tx.account_id||"").slice(0,8)}</td>
                    <td><span className={`status-pill sp-${tx.status}`}>{tx.status}</span></td>
                    <td style={{color:"var(--muted)"}}>{tx.created_at?tx.created_at.slice(0,10):tx.date||""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: HOLDINGS
───────────────────────────────────────────────────────────────────────────── */
