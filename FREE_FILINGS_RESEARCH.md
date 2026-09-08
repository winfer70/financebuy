# TickerTap — Free Filings & Alt-Data Expansion Research

**Date**: 2026-09-08
**Status**: Research (candidate sources beyond Form 4), Form 144 now shipped.

**Shipped (2026-09-08)**: Form 144 — `form144_edgar.py` (parser), `cik_ticker_map.py`
(CIK→ticker resolution via SEC's company_tickers.json, since 144's XML has no
issuerTradingSymbol), `form144_monitor.py` (poller cron, every 15 min, no
direct alert per the "surface it, don't auto-alert" guidance below),
`Form144Notice` table (migration 0036). `insider_monitor.py`'s sell-gate path
correlates a Form 4 sell against a matching 144 by (owner_cik, ticker) within
a 90-day window and appends a "Pre-announced via Form 144 on <date> for
<shares> sh ... — not a surprise" line to the Telegram advice. Also surfaced
as `pending_144` in `GET /insider/owners/{cik}`.

---

## Current Setup

The insider-monitoring pipeline (`backend/app/trading/insider_monitor.py`) is a 5-minute
`arq` cron job (`poll_insider_filings`, registered in `worker.py`'s `cron_jobs`) that:

1. Fetches SEC EDGAR's "current filings" atom feed, hardcoded to Form 4 via
   `FORM4_ATOM_URL = ".../browse-edgar?action=getcurrent&type=4&owner=include&count=40&output=atom"`
   (`insider_edgar.py`).
2. Parses new `<entry>` accessions with `parse_atom_accessions()` — a generic
   atom-feed parser that doesn't know or care what `type=` was requested.
3. For each new accession, fetches and parses the filing's ownership XML with
   `parse_form4_xml()` — this part *is* Form-4-specific (non-derivative
   transaction table, reporting-owner relationship fields, etc.).
4. Runs the result through `insider_gate.evaluate_filing()` (materiality/BookSnapshot
   gating) and `notify_soft_stop()` for Telegram/ntfy/in-app delivery, and writes a row
   to `InsiderFiling` (`models.py`) — this is the table `routes/insider.py` now serves
   to the frontend (`/insider/filings`, `/insider/owners/{cik}`).
5. Caps itself at `_MAX_NEW_PER_CYCLE = 10` per tick, sleeping `_REQUEST_PAUSE_S = 0.25s`
   between EDGAR requests (rate-limit courtesy — see `SEC_USER_AGENT` requirement).

**The key reusable piece is step 1–2**: EDGAR's `getcurrent` atom feed accepts *any*
form type in its `type=` parameter, and `parse_atom_accessions()` has no Form-4-specific
logic. Adding a new filing type mostly means writing a new step-3 parser (the type-specific
XML/HTML shape) and a new table — the polling/dedup/rate-limit scaffolding around it is
already generic.

---

## Candidate Free Sources — Ranked

### 1. Form 144 — Notice of Proposed Sale (highest leverage, lowest new-code cost)

**What**: An insider/affiliate must file Form 144 *before or on the day of* selling
restricted/control stock above a threshold (greater of 5,000 shares or $50,000 in
any 3-month period). It states the exact ticker, share count, and *intended* sale date.

**Why it matters here**: It's a leading indicator for the Form 4 sells you already
gate — a Form 144 today often means a matching Form 4 sale within days. Correlating
the two (`owner_cik` + `ticker` match) turns your existing "12mo owner pattern" logic
into an early-warning signal instead of an after-the-fact one.

**Feed**: `action=getcurrent&type=144&output=atom` — same atom endpoint, same
`parse_atom_accessions()`. Only the per-filing parse differs, and Form 144's XML/HTML
is *simpler* than Form 4 (fewer transaction tables — one proposed sale per filing).

**Effort**: Small. New `parse_form144_xml()` (~40-60 lines, one flat record), a
`Form144Notice` table (ticker, owner_cik, owner_name, broker, shares, approx_sale_value,
approx_sale_date, filed_at), and a join in `insider.py`'s owner breakdown to show
"pending 144s" alongside historical Form 4s. No new gate logic needed initially — surface
it, don't auto-alert on it yet.

### 2. Form 13D / 13G — Beneficial Ownership >5%

**What**: Anyone acquiring >5% of a public company's shares must disclose it.
13D = "activist" intent (may seek control/board seats, includes a stated purpose).
13G = passive investor (index funds, most institutions) — same threshold, no intent language.

**Why it matters**: 13D filings are one of the highest-signal free events in
public markets — activist stakes routinely move price on the filing date itself.
13G is lower-signal individually but useful in aggregate ("which funds are
accumulating this name").

**Feed**: `type=SC 13D` / `type=SC 13G` on the same `getcurrent` atom endpoint.

**Effort**: Medium. The document is closer to a structured cover page + free-text
"Item 4: Purpose of Transaction" — worth extracting the cover-page fields (filer name,
CIK, subject company, % owned, shares) with regex/XML the way `insider_edgar.py`
already does, and just storing the Item 4 text as a blob for the Telegram digest
rather than trying to fully structure it. A `BeneficialOwnership` table
(ticker, filer_cik, filer_name, pct_owned, shares, is_13d, purpose_text, filed_at).

### 3. Form 8-K — Material Events

**What**: Real-time disclosure of anything "material" — M&A, executive
departures/appointments, bankruptcy, auditor changes, earnings releases (Item 2.02),
guidance changes. Filed within 4 business days of the triggering event, often same-day.

**Why it matters**: This is the most useful free "why did the stock just move" signal
that exists, and it's a natural complement to the news-scoring pipeline
(`server-b-worker/`) documented in `NEWS_RESEARCH.md` — 8-Ks are the primary-source
counterpart to the RSS/news-scraper articles you already ingest and score with Ollama.

**Feed**: `type=8-K` on `getcurrent`. High volume (dozens per 5-minute tick across
all US issuers) — **this one needs a ticker watchlist filter at ingest time**
(only process 8-Ks for tickers held in any user's portfolio, mirroring how
`insider_monitor.py`'s gate already scopes to `PortfolioPosition` tickers) or it will
dwarf Form 4 volume for no benefit.

**Effort**: Medium-large, mostly because of the filtering requirement, not the
parsing (8-K "item" codes are a fixed enumerated list — Item 5.02 = officer/director
changes, Item 2.02 = earnings, Item 1.03 = bankruptcy, etc. — trivial to extract from
the filing header, no deep XML parsing needed for a first pass that just captures
"which items were checked" + links to the full text).

### 4. Form 3 — Initial Statement of Beneficial Ownership

**What**: Filed when someone *becomes* an insider (new officer/director/10%+ owner) —
their starting position, before any Form 4 activity exists.

**Why it matters**: Cheap complement to what you already have — `insider_monitor.py`'s
"12mo owner pattern" logic has no baseline for a newly-appointed exec until they trade.
Form 3 gives you `shares_after`-equivalent day one, so a first Form 4 sale can be
contextualized ("sold 10% of initial grant" vs "sold 80%").

**Effort**: Small — same non-derivative-table XML shape as Form 4 minus the
transaction-specific fields (no transaction code/price, just an opening position).
Could realistically reuse most of `parse_form4_xml()`'s owner/relationship parsing.

### 5. Form N-PORT — Monthly Fund Holdings

**What**: Since 2019, registered funds (mutual funds, most ETFs) file monthly
portfolio holdings (way more current than the historical quarterly 13F below).

**Why it matters**: If you ever want a "which funds hold this ticker and did they
just add/trim" view, N-PORT is the freshest free source — but it's filed as large,
deeply nested XML per fund (not per-ticker), so building a ticker-indexed view means
ingesting and indexing whole fund filings, not just watching a feed for your held
tickers. This is the most data-engineering-heavy option here.

**Effort**: Large. Lower priority unless "smart money 13F-style" tracking becomes a
priority — see #6 below for the lower-effort quarterly version first.

### 6. Form 13F — Quarterly Institutional Holdings

**What**: Institutional managers with >$100M AUM disclose long equity positions
quarterly, 45 days after quarter-end.

**Why it matters**: The classic "what are the hedge funds buying" data source
(this is what sites like WhaleWisdom/13F trackers are built on) — free, but stale
by up to 45 days, so it's a *positioning* signal, not a *trading* signal. Good fit
for a slower-cadence job (daily or even weekly poll) rather than the 5-minute cron.

**Effort**: Medium. `type=13F-HR` on the same atom feed; the actual holdings are in
an "information table" XML attached to the filing (a flat list of CUSIP/shares/value
rows) — straightforward to parse, no nested ownership-relationship logic like Form 4.
Note CUSIP → ticker mapping isn't free/trivial from EDGAR alone; would need a
CUSIP↔ticker cross-reference (yfinance doesn't expose this; may need a secondary
lookup or accept CUSIP-only storage with manual/best-effort ticker resolution).

---

## Non-EDGAR Free Bonus Sources

These aren't SEC filings and need their own poller module (not a fit for
`insider_edgar.py`'s atom-feed pattern), but are genuinely free and complementary:

- **FINRA short interest** — biweekly (settlement dates mid/end of month), free,
  ticker-indexed CSV/API. Short interest % of float is a well-known input to squeeze
  and sentiment analysis; trivially joinable to your existing `ticker` column
  everywhere. Lowest-effort bonus item on this whole list — it's a flat file on a
  fixed twice-a-month schedule, no parsing complexity at all.
- **Congressional stock trading (STOCK Act)** — House and Senate members must file
  Periodic Transaction Reports within 45 days of a trade. Free, published as
  PDFs/structured data on `disclosures-clerk.house.gov` and `efdsearch.senate.gov`.
  Popular alt-data signal (several well-known trackers exist); PDF parsing is the
  main friction (House PDFs aren't uniformly structured), and the House site has no
  public bulk API — would need a scraper, more fragile than anything EDGAR-based.

---

## Suggested Build Order

1. ~~**Form 144**~~ — shipped 2026-09-08, see top of doc.
2. **FINRA short interest** — near-zero engineering cost, orthogonal signal, no EDGAR
   parsing needed at all; good "quick second win" alongside #1.
3. **Form 3** — small addition, mostly for owner-history context rather than a new
   alert type; do it opportunistically once #1 is in.
4. **Form 13D/13G** — highest per-filing signal value but more parsing/judgment
   work (free-text "Item 4"); worth it once the above are stable.
5. **Form 8-K** — valuable but only if the portfolio-ticker filter is built first;
   otherwise it's a firehose. Pair with the existing news-scoring pipeline rather
   than routing through the insider Telegram digest.
6. **Form 13F / N-PORT** — lowest priority; positioning data, not trading signals,
   and 13F's CUSIP↔ticker gap and N-PORT's per-fund-not-per-ticker shape both need
   real design work before they're useful in this UI.
