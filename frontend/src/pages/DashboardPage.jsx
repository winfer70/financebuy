/**
 * Dashboard Page
 * 
 * Main dashboard showing portfolio overview, stats, and performance charts.
 */

import { useState, useEffect, useMemo } from "react";
import api, { useApi } from "../api/client";
import { Ic } from "../components/common/Icons";
import { SkeletonRow, ApiError, useMarketStatus } from "../components/common";
import { Sparkline, PortfolioChart, AllocationDonut } from "../components/charts";
import { HOLDINGS, TRANSACTIONS } from "../styles/globals";

export function DashboardPage({ onNewTx, token, accountId, setPage }) {
  const mktStatus = useMarketStatus();
  const [chartPeriod, setChartPeriod] = useState("3M");
  const [showFilter, setShowFilter] = useState(false);
  const [dashFilter, setDashFilter] = useState("all");
  const [quotesMap, setQuotesMap] = useState({});

  // Fetch portfolio positions (includes symbol + name)
  const { data: apiPositions, loading: hLoading } =
    useApi(() => token ? api.getPositions(token) : Promise.resolve(null), [token]);
  const { data: apiTxns, loading: tLoading } =
    useApi(() => (token && accountId) ? api.listTransactions(accountId, token) : Promise.resolve(null), [token, accountId]);
  const { data: apiSummary } =
    useApi(() => token ? api.getPortfolioSummary(token) : Promise.resolve(null), [token]);
  const { data: apiOrders } =
    useApi(() => (token && accountId) ? api.listOrders(accountId, token) : Promise.resolve(null), [token, accountId]);

  // Fetch live quotes for each held symbol
  const dashPollMs = mktStatus.isOpen ? 3000 : 300000;
  useEffect(() => {
    if (!token || !apiPositions || apiPositions.length === 0) return;
    let cancelled = false;
    const symbols = [...new Set(apiPositions.map(p => p.symbol))];
    const fetchQuotes = () => {
      Promise.allSettled(symbols.map(s => api.getQuote(s, token)))
        .then(results => {
          if (cancelled) return;
          const map = {};
          results.forEach((r, i) => {
            if (r.status === "fulfilled") {
              map[symbols[i]] = { price: Number(r.value.price), change: Number(r.value.change), change_pct: Number(r.value.change_pct) };
            }
          });
          setQuotesMap(map);
        });
    };
    fetchQuotes();
    const id = setInterval(fetchQuotes, dashPollMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [token, apiPositions, dashPollMs]);

  // Merge API data — no mock fallback
  const holdings = (apiPositions || []).map(p => {
      const q = quotesMap[p.symbol];
      return {
        symbol: p.symbol, name: p.name,
        quantity: +p.quantity, average_cost: +(p.average_cost||0),
        current_price: q ? q.price : +(p.current_price||0),
        market_value: +(p.market_value||0),
        chg: q ? q.change : 0, chgPct: q ? q.change_pct : 0,
      };
  });
  // Unify transactions + orders into one activity feed
  const txItems = (apiTxns || []).map(t => ({
    id: t.transaction_id, transaction_type: t.transaction_type,
    symbol: null, amount: +t.amount, status: t.status,
    created_at: t.created_at, reference_number: t.reference_number,
  }));
  const orderItems = (apiOrders || []).map(o => ({
    id: o.order_id, transaction_type: o.side,
    symbol: o.symbol || null, amount: +(o.quantity||0) * +(o.price||0),
    status: o.status, created_at: o.placed_at || null,
    reference_number: null,
  }));
  const txns = [...txItems, ...orderItems]
    .sort((a,b) => (b.created_at||"").localeCompare(a.created_at||""));

  const total   = holdings.reduce((s,h)=>s+(h.quantity||0)*(h.current_price||0),0);
  const cost    = holdings.reduce((s,h)=>s+(h.quantity||0)*(h.average_cost||0),0);
  const pnl     = total - cost;
  const pnlPct  = cost > 0 ? (pnl/cost)*100 : 0;
  const dayChg  = holdings.reduce((s,h)=>s+(h.chg||0)*(h.quantity||0),0);

  const cashBalance = apiSummary && apiSummary.accounts && apiSummary.accounts.length > 0
    ? apiSummary.accounts.reduce((s,a) => s + Number(a.cash_balance||0), 0) : null;
  const pendingOrders = apiOrders ? apiOrders.filter(o => o.status === "pending").length : null;

  const filteredTxns = dashFilter === "all" ? txns : txns.filter(t => (t.transaction_type||t.type) === dashFilter);

  return (
    <div className="page-scroll">
      <div className="page-header">
        <div>
          <div className="page-title">DASHBOARD</div>
          <div className="page-sub">{mktStatus.dateStr} · {mktStatus.isOpen ? "MARKET OPEN" : "MARKET CLOSED"} · NYSE · NASDAQ</div>
        </div>
        <div className="page-actions">
          <div style={{position:"relative"}}>
            <button className="btn btn-outline" onClick={()=>setShowFilter(f=>!f)}>
              <Ic.filter/> FILTER{dashFilter !== "all" ? ` (${dashFilter.toUpperCase()})` : ""}
            </button>
            {showFilter && (
              <div style={{
                position:"absolute",top:"100%",right:0,marginTop:4,zIndex:10,
                background:"var(--panel)",border:"1px solid var(--border)",
                padding:8,display:"flex",flexDirection:"column",gap:4,
                minWidth:160,boxShadow:"0 4px 12px rgba(0,0,0,0.4)",
              }}>
                {["all","buy","sell","deposit","withdrawal"].map(f=>(
                  <button key={f} className={`filter-btn${dashFilter===f?" active":""}`}
                    style={{textAlign:"left",width:"100%"}}
                    onClick={()=>{setDashFilter(f);setShowFilter(false);}}
                  >{f.toUpperCase()}</button>
                ))}
              </div>
            )}
          </div>
          <button className="btn btn-amber" onClick={onNewTx}><Ic.plus/> NEW TRANSACTION</button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid-stats stagger">
        {[
          {lbl:"Portfolio Value",   val:`$${(total/1000).toFixed(2)}K`, cls:"amber"},
          {lbl:"Unrealized P&L",    val:`${pnl>=0?"+":""}$${(Math.abs(pnl)/1000).toFixed(2)}K`, cls:pnl>=0?"green":"red"},
          {lbl:"Day Change",        val:`${dayChg>=0?"+":""}$${Math.abs(dayChg).toFixed(2)}`,    cls:dayChg>=0?"green":"red"},
          {lbl:"Cash Balance",      val: cashBalance !== null ? `$${cashBalance.toLocaleString("en-US",{minimumFractionDigits:2})}` : "$14,320.50", cls:""},
          {lbl:"Open Orders",       val: pendingOrders !== null ? String(pendingOrders) : "—", cls:""},
        ].map((s,i)=>(
          <div key={i} className="stat-block">
            <div className="stat-lbl">{s.lbl}</div>
            <div className={`stat-val${s.cls?" "+s.cls:""}`}>{s.val}</div>
            {i===1&&<div className={`stat-badge ${pnl>=0?"badge-green":"badge-red"}`}>
              {pnl>=0?<Ic.up/>:<Ic.down/>} {Math.abs(pnlPct).toFixed(2)}% ALL TIME
            </div>}
            {i===2&&<div className={`stat-badge ${dayChg>=0?"badge-green":"badge-red"}`}>
              {dayChg>=0?<Ic.up/>:<Ic.down/>} {total>0?Math.abs(dayChg/total*100).toFixed(2):"0.00"}% TODAY
            </div>}
            {i===3&&<div className="stat-badge badge-mid">AVAILABLE MARGIN</div>}
            {i===4&&pendingOrders>0&&<div className="stat-badge badge-amber">{pendingOrders} PENDING</div>}
          </div>
        ))}
      </div>

      <div className="page-inner stagger">
        {/* Main chart + allocation */}
        <div className="grid-main">
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">PORTFOLIO PERFORMANCE · {chartPeriod}</span>
              <div style={{display:"flex",gap:1}}>
                {["1W","1M","3M","YTD","1Y","ALL"].map(p=>(
                  <button key={p} className={`filter-btn${p===chartPeriod?" active":""}`}
                    style={{padding:"4px 10px",fontSize:9}}
                    onClick={()=>setChartPeriod(p)}
                  >{p}</button>
                ))}
              </div>
            </div>
            <div className="panel-body" style={{paddingBottom:8}}>
              <PortfolioChart height={160} period={chartPeriod}/>
            </div>
          </div>
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">ALLOCATION</span>
              <span style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)"}}>{holdings.length} POSITIONS</span>
            </div>
            <div className="panel-body">
              <AllocationDonut holdings={holdings}/>
            </div>
          </div>
        </div>

        {/* Holdings snapshot */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">TOP POSITIONS</span>
            <button className="btn btn-ghost" style={{fontSize:9,padding:"3px 10px"}} onClick={()=>setPage("holdings")}>VIEW ALL →</button>
          </div>
          <div style={{overflowX:"auto"}}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>SYMBOL</th>
                  <th className="right">LAST</th>
                  <th className="right">CHG</th>
                  <th className="right">QTY</th>
                  <th className="right">MKT VALUE</th>
                  <th className="right">P&L</th>
                  <th className="right">RETURN</th>
                  <th>TREND</th>
                </tr>
              </thead>
              <tbody>
                {hLoading ? (
                  Array.from({length:3}).map((_,i)=><SkeletonRow key={i} cols={8}/>)
                ) : holdings.length === 0 ? (
                  <tr><td colSpan={8} style={{textAlign:"center",padding:"32px 0",fontFamily:"var(--font-mono)",fontSize:12,color:"var(--muted)"}}>
                    No assets in portfolio
                  </td></tr>
                ) : holdings.slice(0,5).map(h=>{
                  const qty = h.quantity||0, price = h.current_price||0, avg = h.average_cost||0;
                  const val=qty*price, pl=(price-avg)*qty, ret=avg>0?((price-avg)/avg)*100:0;
                  return (
                    <tr key={h.symbol}>
                      <td>
                        <div className="cell-symbol">
                          <div className="sym-badge">{(h.symbol||"?").slice(0,3)}</div>
                          <div><div className="cell-main">{h.symbol}</div><div className="sym-name">{h.name}</div></div>
                        </div>
                      </td>
                      <td className="right">${price.toFixed(2)}</td>
                      <td className={`right ${(h.chgPct||0)>=0?"pnl-pos":"pnl-neg"}`}>
                        {(h.chgPct||0)>=0?"+":""}{(h.chgPct||0).toFixed(2)}%
                      </td>
                      <td className="right">{qty}</td>
                      <td className="right cell-main">${val.toFixed(2)}</td>
                      <td className={`right ${pl>=0?"pnl-pos":"pnl-neg"}`}>
                        {pl>=0?"+":""}${pl.toFixed(2)}
                      </td>
                      <td className={`right ${ret>=0?"pnl-pos":"pnl-neg"}`}>{ret>=0?"+":""}{ret.toFixed(2)}%</td>
                      <td><Sparkline positive={(h.chgPct||0)>=0} w={72} h={22}/></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent transactions */}
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">RECENT TRANSACTIONS</span>
            <button className="btn btn-ghost" style={{fontSize:9,padding:"3px 10px"}} onClick={()=>setPage("transactions")}>VIEW ALL →</button>
          </div>
          <div style={{overflowX:"auto"}}>
            <table className="data-table">
              <thead>
                <tr><th>TXN ID</th><th>TYPE</th><th>SYMBOL</th><th className="right">AMOUNT</th><th>STATUS</th><th>DATE</th></tr>
              </thead>
              <tbody>
                {tLoading ? (
                  Array.from({length:3}).map((_,i)=><SkeletonRow key={i} cols={6}/>)
                ) : filteredTxns.length === 0 ? (
                  <tr><td colSpan={6} style={{textAlign:"center",padding:"32px 0",fontFamily:"var(--font-mono)",fontSize:12,color:"var(--muted)"}}>
                    No transactions
                  </td></tr>
                ) : filteredTxns.slice(0,5).map(tx=>(
                  <tr key={tx.transaction_id||tx.id}>
                    <td style={{color:"var(--muted)",fontSize:11}}>{tx.reference_number||tx.id||String(tx.transaction_id||"").slice(0,8)}</td>
                    <td><span className={`type-chip tc-${tx.transaction_type||tx.type}`}>{tx.transaction_type||tx.type}</span></td>
                    <td>{tx.symbol ? <span style={{color:"var(--bright)"}}>{tx.symbol}</span> : <span style={{color:"var(--muted)"}}>—</span>}</td>
                    <td className="right cell-main">${(+tx.amount||0).toLocaleString("en-US",{minimumFractionDigits:2})}</td>
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
   PAGE: TRANSACTIONS
───────────────────────────────────────────────────────────────────────────── */
