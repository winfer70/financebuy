/**
 * Holdings Page
 * 
 * Displays portfolio holdings with performance metrics and sparklines.
 */

import { useState, useMemo } from "react";
import api, { useApi } from "../api/client";
import { Ic } from "../components/common/Icons";
import { SkeletonRow, ApiError } from "../components/common";
import { Sparkline, AllocationDonut } from "../components/charts";
import { HOLDINGS } from "../styles/globals";

export function HoldingsPage({ onNewTx, onViewChart, token, accountId, goBack }) {
  const { data: apiHoldings, loading, error, refetch } =
    useApi(() => token ? api.getPositions(token) : Promise.resolve(null), [token]);

  const rawHoldings = apiHoldings || [];
  // Normalise field names — API uses snake_case, mock uses short names
  const holdings = rawHoldings.map(h => ({
    ...h,
    qty:   parseFloat(h.quantity  ?? h.qty),
    avg:   parseFloat(h.average_cost  ?? h.avg),
    price: parseFloat(h.current_price ?? h.price),
    symbol: h.symbol ?? h.security_id,
    name:   h.name   ?? h.symbol ?? "",
    chgPct: h.chgPct ?? 0,
    chg:    h.chg    ?? 0,
  }));
  const total = holdings.reduce((s,h)=>s+h.qty*h.price,0);
  const cost  = holdings.reduce((s,h)=>s+h.qty*h.avg,0);

  return (
    <div className="page-scroll">
      <div className="page-header">
        <div>
          <div className="page-title"><button className="btn btn-ghost" onClick={goBack} style={{padding:"4px 6px",marginRight:8,verticalAlign:"middle"}}><Ic.back/></button>HOLDINGS</div>
          <div className="page-sub">{holdings.length} POSITIONS · {accountId ? `ACCOUNT ${String(accountId).slice(0,8).toUpperCase()}` : "DEMO"}</div>
        </div>
        <div className="page-actions">
          <button className="btn btn-outline"><Ic.file/> STATEMENTS</button>
          <button className="btn btn-amber" onClick={onNewTx}><Ic.plus/> NEW TRANSACTION</button>
        </div>
      </div>

      <div className="grid-stats stagger">
        {[
          {lbl:"Total Market Value", val:`$${(total/1000).toFixed(3)}K`,                    cls:"amber"},
          {lbl:"Total Cost Basis",   val:`$${(cost/1000).toFixed(3)}K`,                     cls:""},
          {lbl:"Unrealized Gain",    val:`${total>=cost?"+":""}$${((total-cost)/1000).toFixed(3)}K`,             cls:total>=cost?"green":"red"},
          {lbl:"Total Return",       val:`${total>=cost?"+":""}${cost>0?(((total-cost)/cost)*100).toFixed(2):"0.00"}%`,        cls:total>=cost?"green":"red"},
          {lbl:"Positions",          val:holdings.length,                                    cls:""},
        ].map((s,i)=>(
          <div key={i} className="stat-block">
            <div className="stat-lbl">{s.lbl}</div>
            <div className={`stat-val${s.cls?" "+s.cls:""}`}>{s.val}</div>
          </div>
        ))}
      </div>

      <div className="page-inner stagger">
        <div className="grid-main">
          {/* Holdings table */}
          <div className="panel">
            <div className="panel-header"><span className="panel-title">POSITIONS</span></div>
            <div style={{overflowX:"auto"}}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>SYMBOL</th>
                    <th className="right">QTY</th>
                    <th className="right">AVG COST</th>
                    <th className="right">LAST PRICE</th>
                    <th className="right">MKT VALUE</th>
                    <th className="right">UNRLZD P&L</th>
                    <th className="right">RETURN</th>
                    <th className="right">DAY CHG</th>
                    <th>TREND</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {loading && [0,1,2,3].map(i=><SkeletonRow key={i} cols={10}/>)}
                  {error   && <tr><td colSpan={10}><ApiError message={error} onRetry={refetch}/></td></tr>}
                  {!loading && !error && holdings.length === 0 && (
                    <tr><td colSpan={10} style={{textAlign:"center",padding:"32px 0",fontFamily:"var(--font-mono)",fontSize:12,color:"var(--muted)"}}>
                      No assets in portfolio
                    </td></tr>
                  )}
                  {holdings.map(h=>{
                    const val=(h.qty*h.price), pl=(h.price-h.avg)*h.qty, ret=((h.price-h.avg)/h.avg)*100;
                    const weight=(val/total)*100;
                    return (
                      <tr key={h.symbol} style={{cursor:"pointer"}} onClick={()=>onViewChart&&onViewChart(h.symbol)} title={`Open ${h.symbol} chart`}>
                        <td>
                          <div className="cell-symbol">
                            <div className="sym-badge">{h.symbol.slice(0,3)}</div>
                            <div>
                              <div className="cell-main">{h.symbol}</div>
                              <div className="sym-name">{h.name}</div>
                            </div>
                          </div>
                        </td>
                        <td className="right">{h.qty}</td>
                        <td className="right">${h.avg.toFixed(2)}</td>
                        <td className="right cell-main">${h.price.toFixed(2)}</td>
                        <td className="right">
                          <div>${val.toFixed(2)}</div>
                          <div style={{fontSize:9,color:"var(--muted)",marginTop:1}}>{weight.toFixed(1)}% PORTFOLIO</div>
                        </td>
                        <td className={`right ${pl>=0?"pnl-pos":"pnl-neg"}`}>
                          <div>{pl>=0?"+":""}${Math.abs(pl).toFixed(2)}</div>
                        </td>
                        <td className={`right ${ret>=0?"pnl-pos":"pnl-neg"}`}>{ret>=0?"+":""}{ret.toFixed(2)}%</td>
                        <td className={`right ${h.chgPct>=0?"pnl-pos":"pnl-neg"}`}>
                          {h.chgPct>=0?"+":""}{h.chgPct.toFixed(2)}%
                        </td>
                        <td><Sparkline positive={h.chgPct>=0} w={64} h={20}/></td>
                        <td>
                          <button onClick={e=>{e.stopPropagation();onViewChart&&onViewChart(h.symbol);}}
                            style={{background:"none",border:"1px solid #1e2535",cursor:"pointer",color:"#4a5568",padding:"3px 7px",fontFamily:"IBM Plex Mono",fontSize:9,letterSpacing:"0.5px",display:"flex",alignItems:"center",gap:4,transition:"all 0.1s",borderRadius:2}}
                            onMouseEnter={e=>{e.currentTarget.style.color="#0f7d40";e.currentTarget.style.borderColor="#0f7d40";}}
                            onMouseLeave={e=>{e.currentTarget.style.color="#4a5568";e.currentTarget.style.borderColor="#1e2535";}}>
                            <Ic.externalLink/> CHART
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Donut sidebar */}
          <div style={{display:"flex",flexDirection:"column",gap:16}}>
            <div className="panel">
              <div className="panel-header"><span className="panel-title">ALLOCATION</span></div>
              <div className="panel-body"><AllocationDonut holdings={holdings}/></div>
            </div>
            <div className="panel">
              <div className="panel-header"><span className="panel-title">PERFORMANCE</span></div>
              <div className="panel-body">
                {[
                  {lbl:"Best Performer",  sym:"NVDA",  val:"+50.26%", pos:true},
                  {lbl:"Worst Performer", sym:"TSLA",  val:"-15.00%", pos:false},
                  {lbl:"Largest Position",sym:"MSFT",  val:"$3,031",  pos:null},
                  {lbl:"Smallest Position",sym:"AMZN", val:"$1,178",  pos:null},
                ].map((r,i)=>(
                  <div key={i} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"8px 0",borderBottom:"1px solid var(--border)"}}>
                    <div>
                      <div style={{fontFamily:"var(--font-mono)",fontSize:10,color:"var(--muted)",marginBottom:2}}>{r.lbl}</div>
                      <div style={{fontFamily:"var(--font-mono)",fontSize:12,fontWeight:500,color:"var(--bright)"}}>{r.sym}</div>
                    </div>
                    <div style={{fontFamily:"var(--font-mono)",fontSize:12,fontWeight:500,color:r.pos===null?"var(--text)":r.pos?"var(--green)":"var(--red)"}}>
                      {r.val}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PAGE: ORDERS
───────────────────────────────────────────────────────────────────────────── */
