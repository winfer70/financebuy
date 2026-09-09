# TickerTap — News Expansion Feasibility Research

**Date**: 2026-03-16  
**Status**: Research (source-expansion options). Live scoring path is already `server-b-worker/` → Ollama → `POST /api/v1/news/internal/news`. **Not FinBERT.**

**Shipped (2026-09-08)**: Fixed the "0 articles scored" bug — `server-b-worker/worker.py`
was slicing a flat, alphabetically-ordered watch-ticker list to `_MAX_WATCH_TICKERS_PER_CYCLE`
every cycle, so tickers late in the alphabet (or added later) were starved of per-ticker
search entirely. Fixed with two changes: `feedback.py::get_watch_tickers()` now orders
Form-4 filers by most-recent transaction date first (`func.max(InsiderFiling.transaction_date)`
GROUP BY, re-sorted in Python) instead of alphabetically, with held positions appended after
(capped at `_WATCH_TICKER_LIMIT = 60`); and `worker.py` added a `_TICKER_SEARCH_COOLDOWN_SECONDS
= 2 * 60 * 60` per-ticker cooldown (`_ticker_last_searched: dict`) so the slice rotates through
the full watch list over time instead of always hitting the same head-of-list tickers. No new
source, no schema change — purely a scheduling/ordering fix in the existing pipeline described
below.

---

## Current Setup

### Architecture Overview

TickerTap's news system is a two-server pipeline:

1. **Server B (remote worker host)** runs a single-threaded Python worker (`server-b-worker/worker.py`) that:
   - Fetches raw articles from 4 sources via `sources.py` (Yahoo Finance RSS, Google News RSS, Finviz HTML scrape, MarketWatch RSS)
   - Deduplicates by URL in-memory (capped at 10,000 URLs)
   - Scores each article through a local Ollama LLM (`llama3:8b-instruct-q4_K_M`) which produces a general market score (-5 to +5) and per-ticker scores with reasoning
   - POSTs scored articles in batches of 10 to Server A's internal ingestion endpoint
   - Falls back to a local SQLite queue (`article_queue.py`) when Server A is unreachable (max 5 retries)
   - Refreshes learned calibration rules from Server A every 6 cycles to improve scoring accuracy
   - Cycles every 10 minutes during US market hours, 30 minutes off-hours

2. **Server A (TickerTap backend)** receives scored articles via `POST /api/v1/news/internal/news` (authenticated with `X-Internal-Key` header + optional IP restriction), upserts into PostgreSQL (`news_articles` + `news_article_tickers` tables), and serves them through two read endpoints:
   - `GET /api/v1/news/feed` — paginated feed with server-side filtering (portfolio, sentiment, ticker search)
   - `GET /api/v1/news/tickers/{ticker}` — articles filtered by a single ticker

### Database Schema

- **`news_articles`**: `article_id` (UUID PK), `url` (unique), `title`, `summary`, `source` (varchar 20), `published_at`, `scored_at`, `general_score` (smallint, -5 to +5), `general_reasoning`, `created_at`
- **`news_article_tickers`**: `id` (UUID PK), `article_id` (FK cascade), `ticker` (varchar 20), `score` (smallint), `reasoning`
- **`score_outcomes`**: tracks LLM prediction accuracy against actual price movement (used by the learner)

### Current Sources (in `sources.py`)

| # | Source | Type | URL | Max per cycle |
|---|--------|------|-----|---------------|
| 1 | Yahoo Finance | RSS | `https://finance.yahoo.com/news/rssindex` | 20 |
| 2 | Google News | RSS | `https://news.google.com/rss/search?q=stock+market+OR+earnings+OR+finance` | 15 |
| 3 | Finviz | HTML scrape | `https://finviz.com/news.ashx` | 20 |
| 4 | MarketWatch | RSS | `https://feeds.marketwatch.com/marketwatch/topstories` | 25 |

Total: up to ~80 raw articles per cycle, capped at 50 after dedup for LLM scoring.

### Frontend Display

The `NewsPage.jsx` renders articles with score badges (colour-coded -5 red to +5 green), sentiment labels, LLM reasoning text, per-ticker drill-down badges, portfolio highlighting, and source badges. Server-side pagination with configurable page sizes (25/50/75/100). A staleness indicator appears when the newest article is older than 30 minutes.

### Key Technical Constraints

- The `source` column is `String(20)` — new source identifiers must be 20 chars or fewer.
- Articles are deduplicated by URL both in-memory on Server B and via unique constraint on Server A.
- The LLM scoring step is the bottleneck: at ~2-5 seconds per article through Ollama, 50 articles per cycle already takes 2-4 minutes.
- 30-day retention cleanup runs daily via background task.
- The `NewsArticleIngest` schema's `source` field description currently enumerates `'yahoo', 'google', 'finviz', 'marketwatch'` — this is documentation only and does not enforce validation, so adding new source strings requires no schema change.

---

## Option 1: Additional RSS Feeds

RSS feeds are the path of least resistance — the existing pipeline (`feedparser` + `_make_article` + `_parse_rss_date`) already handles them. Adding a new source means writing one function (~30 lines) following the exact pattern of `fetch_yahoo()` / `fetch_marketwatch()` and registering it in `fetch_all_news()`.

### Candidates

#### 1a. Seeking Alpha

- **URL**: `https://seekingalpha.com/feed.xml` (main feed) and `https://seekingalpha.com/feed/market-news.xml` (market news)
- **Content quality**: High — detailed equity analysis, earnings commentary, dividend coverage. Very relevant to TickerTap's portfolio-centric users.
- **Ticker tagging**: Seeking Alpha articles frequently mention tickers in titles (e.g., "NVDA: Why We're Bullish Ahead Of Earnings"), making LLM ticker extraction straightforward.
- **Rate limits / ToS**: Seeking Alpha's free RSS feed has been intermittently available. As of early 2025, they restrict programmatic access aggressively. They use Cloudflare bot protection which may block the worker's `requests` library. Their ToS prohibits scraping for commercial redistribution.
- **Implementation effort**: LOW if the feed responds. Same pattern as `fetch_yahoo()`. May need a Cloudflare-bypassing user agent or proxy. Risk of feed being discontinued.
- **Verdict**: HIGH VALUE but MEDIUM RISK of access issues.

#### 1b. Motley Fool RSS

- **URL**: `https://www.fool.com/feeds/index.aspx` (main), `https://www.fool.com/feeds/marketwatch.aspx` (market coverage)
- **Content quality**: Good for retail investors — stock picks, earnings analysis, educational content. Moderate noise from sponsored/promotional articles.
- **Ticker tagging**: Titles often include company names rather than symbols (e.g., "Why Amazon Stock Dropped Today"), so the LLM will handle extraction fine but direct symbol matching is less reliable.
- **Rate limits / ToS**: Feed has been publicly available. No known aggressive rate limiting. ToS prohibit full-article scraping but headline + link usage in an aggregator is standard RSS practice.
- **Implementation effort**: LOW. Standard feedparser pattern.
- **Verdict**: MEDIUM VALUE, LOW RISK.

#### 1c. CoinDesk (Crypto News)

- **URL**: `https://www.coindesk.com/arc/outboundfeeds/rss/` (current RSS endpoint)
- **Content quality**: Top-tier crypto news. Relevant only if TickerTap expands to crypto assets (currently focused on equities via yfinance).
- **Ticker tagging**: Crypto tickers (BTC, ETH, SOL) are different from equity symbols. The LLM would need context that these are crypto. Cross-contamination risk: a crypto article about "SOL" should not score Sunrun (SOL on NYSE).
- **Rate limits / ToS**: CoinDesk's RSS feed is publicly accessible. After CoinDesk's acquisition by Bullish, feed reliability is uncertain.
- **Implementation effort**: LOW technically but requires LLM prompt changes to handle crypto tickers correctly without confusing them with equity symbols.
- **Verdict**: LOW VALUE unless TickerTap adds crypto support. DEFER.

#### 1d. Yahoo Finance RSS (Ticker-Specific)

- **URL pattern**: `https://finance.yahoo.com/rss/headline?s=AAPL` (per-ticker), `https://finance.yahoo.com/rss/industry?s=AAPL` (industry news)
- **Content quality**: Same quality as the existing general Yahoo feed but targeted. Particularly valuable for portfolio-relevant articles.
- **Ticker tagging**: Built-in — the feed is already filtered by ticker, so we know exactly which ticker is relevant before LLM scoring.
- **Rate limits / ToS**: Same as the existing Yahoo source. Adding per-ticker feeds for, say, 20 portfolio tickers would mean 20 additional HTTP requests per cycle (possibly throttled).
- **Implementation effort**: MEDIUM. Requires building a dynamic list of tickers to fetch (could pull from active user portfolios via Server A's internal API). More HTTP requests and dedup complexity.
- **Verdict**: HIGH VALUE for portfolio users. Worth exploring after a batch of popular tickers is identified.

#### 1e. MarketWatch (Additional Feeds)

- **URLs**:
  - `https://feeds.marketwatch.com/marketwatch/marketpulse` (Market Pulse)
  - `https://feeds.marketwatch.com/marketwatch/StockstoWatch` (Stocks to Watch)
  - `https://feeds.marketwatch.com/marketwatch/financial` (Financial sector)
  - `https://feeds.marketwatch.com/marketwatch/Edesktopheadlines` (Breaking)
- **Content quality**: Already proven with the existing top-stories feed. Additional feeds add sector-specific and breaking news.
- **Ticker tagging**: Same as existing — LLM handles extraction.
- **Rate limits / ToS**: MarketWatch feeds are publicly hosted on `feeds.marketwatch.com`. Adding 2-3 more feeds from the same domain is likely fine.
- **Implementation effort**: VERY LOW. Duplicate the `fetch_marketwatch()` function with different URLs and source identifiers (e.g., `"mw-pulse"`, `"mw-stocks"`).
- **Verdict**: LOW-HANGING FRUIT. Easy to add alongside the existing MarketWatch source.

#### 1f. Bloomberg

- **URL**: No public RSS feed available. Bloomberg Terminal data is behind a paywall. The Bloomberg API (B-PIPE, BLPAPI) requires a Bloomberg Terminal subscription (~$24,000/year).
- **Content quality**: Best-in-class financial news. Irrelevant if we cannot access it.
- **Implementation effort**: N/A — no free access path.
- **Verdict**: NOT FEASIBLE for TickerTap.

#### 1g. Reuters

- **URL**: Reuters discontinued their public RSS feeds in 2020. The Reuters Connect API requires a commercial license.
- **Alternatives**: Reuters content appears in Google News and other aggregators, which TickerTap already captures indirectly.
- **Verdict**: NOT FEASIBLE directly. Already captured indirectly via Google News.

#### 1h. Benzinga

- **URL**: `https://www.benzinga.com/feed` (main RSS)
- **Content quality**: Strong on earnings, pre-market movers, analyst ratings. High relevance for active traders.
- **Ticker tagging**: Benzinga articles frequently include ticker symbols in titles and categories, making LLM extraction highly accurate.
- **Rate limits / ToS**: Feed is publicly available. Benzinga offers a paid API for higher-volume access, but the RSS feed works for headline-level aggregation.
- **Implementation effort**: LOW. Standard feedparser pattern.
- **Verdict**: HIGH VALUE, LOW RISK. Strong candidate.

#### 1i. Investopedia

- **URL**: `https://www.investopedia.com/feedbuilder/feed/getfeed?feedName=rss_headline` (main RSS)
- **Content quality**: Educational and market commentary. Less breaking-news, more explainer content. Lower urgency but good for context.
- **Ticker tagging**: Mixed — some articles are ticker-specific, many are educational.
- **Implementation effort**: LOW.
- **Verdict**: LOW VALUE for real-time news scoring. DEFER.

### RSS Recommendation — Priority Order

| Priority | Source | Effort | Value | Risk | Rationale |
|----------|--------|--------|-------|------|-----------|
| 1 | Benzinga RSS | Very Low | High | Low | Best-in-class for active traders. Ticker-rich headlines. |
| 2 | MarketWatch additional feeds | Very Low | Medium | Very Low | Already have the pattern; just add more endpoints. |
| 3 | Seeking Alpha | Low | High | Medium | Excellent analysis, but Cloudflare blocking risk. |
| 4 | Motley Fool | Low | Medium | Low | Solid retail coverage, low risk. |
| 5 | Yahoo Finance per-ticker | Medium | High | Low | Requires dynamic ticker list; highly targeted content. |
| 6 | CoinDesk | Low | Low* | Low | Only valuable if crypto support is added. |

*Value conditional on crypto feature roadmap.

---

## Option 2: Telegram Group Integration

### AppREDACTED

Use the **Telethon** library (Python async Telegram client) to monitor public and private Telegram channels for financial news and signals. Messages would be parsed, tickers extracted, and fed into the existing LLM scoring pipeline.

### Popular Finance Channels

- **Coin Bureau** — crypto market analysis (800k+ subscribers)
- **WallStreetBets** — meme stock signals and DD (various unofficial mirrors)
- **Stock Signals / Trading Alerts** channels — numerous small channels with varying quality
- **Bloomberg Markets / Reuters Breaking** — unofficial repost channels
- **Unusual Whales** — options flow alerts

### Technical Considerations

**Authentication**:
- Telethon requires a **real Telegram account** (phone number for OTP verification) and Telegram API keys (`api_id`, `api_hash` from `my.telegram.org`).
- This means creating a dedicated Telegram account for the worker, which ties the service to a phone number and introduces a single point of failure.
- Telegram periodically requires re-authentication (phone verification), which cannot be automated without a real SIM card or VoIP number.

**Message Parsing / Ticker Extraction**:
- Telegram messages are unstructured text — no consistent format across channels.
- Would need a parsing layer that extracts potential ticker mentions from free-form text (regex for `$AAPL` cashtag patterns, plus LLM fallback for ambiguous mentions).
- Signal-to-noise ratio varies wildly between channels. A single "AAPL to the moon" message from a meme channel has very different informational value than a Bloomberg repost.
- Messages often contain emojis, images, and forwarded content that complicate parsing.

**Integration with Existing Pipeline**:
- Telethon is async-native (`asyncio`), while the current worker (`worker.py`) is synchronous single-threaded using `requests` and `time.sleep()`.
- Two integration appREDACTEDes:
  1. Run a separate async Telethon listener process that feeds articles into the same SQLite queue or directly to Server A's internal API.
  2. Refactor the worker to use `asyncio` + `aiohttp` throughout, then integrate Telethon as another source.
- AppREDACTED 1 is simpler but adds operational complexity (another process to manage). AppREDACTED 2 is a significant refactor of the worker.

**Legal Considerations**:
- Many Telegram channels explicitly prohibit redistribution of their content.
- Forwarding or displaying content from private/paid channels in TickerTap's news feed could constitute copyright infringement.
- Telegram's ToS allows personal use of client API but prohibits mass data collection.
- Even public channels may contain copyrighted content (e.g., Bloomberg article reposts).

**Rate Limits and Bot Restrictions**:
- Telegram aggressively rate-limits API calls: approximately 30 messages/second for reading, with flood-wait penalties (forced waits of 30-600 seconds) for exceeding limits.
- Accounts that join too many channels or read too aggressively get flagged and temporarily or permanently banned.
- Using a "userbot" (Telethon) rather than a Bot API client avoids some restrictions but introduces the phone-number dependency.

**Operational Burden**:
- Must maintain a list of monitored channels and update it as channels emerge or die.
- Must handle channel reorganizations, name changes, and access revocations.
- The Telethon session file must be persisted and secured (it grants full account access).

### Recommendation

**Not recommended at this time.** The complexity-to-value ratio is poor:

- The authentication requirement (real phone number, periodic re-verification) makes this fragile in production.
- Legal risk of content redistribution is non-trivial.
- Signal-to-noise ratio from Telegram channels is low compared to curated financial RSS feeds that already exist.
- The async/sync impedance mismatch with the current worker requires either a separate process or a significant refactor.
- The operational burden of managing channel lists and session persistence is ongoing.

If revisited in the future, the best appREDACTED would be to monitor only 2-3 high-quality public channels (e.g., Unusual Whales, a single reputable analyst) as a supplementary signal, not a primary news source.

---

## Option 3: Email Subscription Scraping

### AppREDACTED

Subscribe a dedicated email address to financial newsletters, then use Python's `imaplib` or `imap_tools` library to periodically poll the inbox, parse email HTML, extract article text and ticker references, and feed them into the LLM scoring pipeline.

### Newsletter Candidates

- **Morning Brew** — daily market summary, broad coverage
- **Barron's Daily** — market analysis and stock picks
- **The Motley Fool Stock Advisor** — stock recommendations (paid, $99/year)
- **Seeking Alpha Wall Street Breakfast** — pre-market summary
- **MarketBeat Daily** — earnings, analyst ratings
- **CNBC Newsletters** — various free daily digests

### Technical Considerations

**Email Parsing Complexity**:
- Financial newsletters use complex HTML templates with images, tables, embedded CSS, and tracking pixels.
- Each newsletter has a unique layout that requires a dedicated parser or robust HTML-to-text conversion.
- Email formatting changes frequently (redesigns, A/B testing different templates), breaking parsers without notice.
- Libraries like `BeautifulSoup` or `mail-parser` can extract text, but extracting structured article-level data (separate headlines, per-article summaries) from newsletter HTML is significantly harder than parsing RSS XML.

**Integration with Existing Pipeline**:
- Would run as a polling loop (check inbox every N minutes), similar to the worker's cycle pattern.
- Parsed articles would be fed into the same `_make_article()` -> LLM scoring -> Server A ingestion pipeline.
- Source identifier could be `"email-brew"`, `"email-barrons"`, etc.
- IMAP polling is synchronous and fits the current worker pattern.

**Legal / Copyright Considerations**:
- Newsletters are copyrighted content sent to individual subscribers.
- Redistributing newsletter content (even as summaries) in TickerTap's feed likely violates the subscription ToS.
- Some newsletters (Morning Brew, MarketBeat) are free and ad-supported — using their content commercially still requires permission.
- Paid newsletters (Barron's, Motley Fool) explicitly prohibit sharing subscriber content.

**Privacy Concerns**:
- The IMAP credentials for the email inbox must be stored as environment variables on Server B.
- If the email address is compromised, the attacker gains access to all subscribed newsletters (minor risk) and potentially any other services linked to that email (if reused).
- Email headers may leak server IP information.

**Maintenance Burden**:
- Newsletter formats change without notice, requiring parser updates.
- Subscription management (confirm emails, handle unsubscribes, manage newsletter frequency settings) is manual.
- Spam filtering and deduplication (some newsletters send duplicate or cross-promoted content) add complexity.

### Recommendation

**Not recommended.** The effort-to-value ratio is poor:

- The core content from major newsletters (Morning Brew, Barron's) is already captured by the existing RSS sources (Yahoo, Google News, MarketWatch) since newsletters largely aggregate the same underlying news stories.
- Incremental value over RSS is minimal — newsletters add editorial commentary, not new information.
- Parsing reliability is low due to HTML template variability.
- Legal exposure is high, especially for paid newsletter content.
- Maintenance cost is ongoing and disproportionate to the marginal content gain.

If a specific newsletter offers unique content not available via RSS (e.g., proprietary analyst ratings), it would be more practical to check whether that source offers an API or RSS feed directly.

---

## Option 4: Reddit / Social Media

### AppREDACTED

Use the Reddit API (via `praw` or `asyncpraw`) to monitor financial subreddits, extract posts and comments, and score them through the LLM pipeline as a supplementary sentiment signal.

### Relevant Subreddits

- **r/wallstreetbets** (~16M members) — meme stocks, options plays, YOLO posts. Very high noise, occasional signal.
- **r/stocks** (~7M members) — general stock discussion, DD posts. Better signal-to-noise than WSB.
- **r/investing** (~2.5M members) — long-term investing discussion. High quality but lower frequency.
- **r/options** (~1M members) — options-specific discussion.
- **r/SecurityAnalysis** (~200K members) — deep fundamental analysis. High quality, low volume.
- **r/StockMarket** (~3M members) — general market discussion.

### Technical Considerations

**Reddit API Limits and Authentication**:
- Reddit requires OAuth2 authentication via a registered application (`client_id`, `client_secret`, `user_agent`).
- Free-tier API limits: 100 requests per minute (per OAuth2 client), 1000 items per listing.
- As of 2024, Reddit's API pricing changes mean the free tier is still available for non-commercial use, but commercial applications require a paid API plan (unspecified pricing, applied individually).
- TickerTap may qualify as a commercial application, requiring a paid API agreement.

**Signal-to-Noise Ratio**:
- r/wallstreetbets is overwhelmingly memes, loss/gain porn, and low-quality speculation. Extracting actionable news from WSB requires heavy filtering.
- Even r/stocks and r/investing have significant noise (repetitive questions, vague sentiment posts, off-topic discussions).
- Useful content is typically long-form DD (due diligence) posts, which are rare (a few per day on r/stocks).
- Comments are even noisier — extracting signal from comments requires sentiment aggregation at scale.

**Content Quality Filtering**:
- Reddit posts would need a pre-filter before LLM scoring to avoid wasting Ollama cycles on low-value content.
- Possible filters: minimum upvote threshold (e.g., 50+ upvotes), minimum post length, flair filtering (e.g., "DD" flair only), exclude meme/image posts.
- Even with filtering, the content type is fundamentally different from news articles — Reddit posts are opinions, not reporting. The LLM scoring prompt would need adaptation to score sentiment/opinion rather than news impact.

**Integration with Existing Pipeline**:
- `praw` (synchronous) fits the current worker. `asyncpraw` fits an async refactor.
- Reddit posts have titles and self-text (for text posts) or URLs (for link posts). Link posts point to external articles that may already be captured by RSS sources.
- Would need special handling: extract the post as a "pseudo-article" with the Reddit post title as the headline and the self-text (or top comment) as the summary.
- Source identifier: `"reddit-stocks"`, `"reddit-wsb"`, etc.

**Ticker Extraction**:
- Reddit uses `$AAPL` cashtag convention inconsistently. Many posts mention company names without symbols.
- The existing LLM scoring handles ticker extraction, but Reddit post titles are often informal ("Why I'm going all in on Tesla") and may confuse the scorer.

**Legal / ToS**:
- Reddit API ToS allows data access for display purposes but prohibits bulk data redistribution.
- Displaying Reddit post titles and LLM-generated scores in TickerTap's feed is likely permissible if linked back to the original post.
- Cannot display Reddit post content verbatim without attribution.

### Sentiment Analysis Addition

Rather than treating Reddit posts as news articles, a more natural integration would be as a **sentiment signal**:

- Aggregate mention counts and upvote-weighted sentiment per ticker across subreddits.
- Display as a "Social Sentiment" indicator alongside the news feed (e.g., "NVDA: Reddit sentiment +3.2, 47 mentions in 24h").
- This avoids the noise problem (aggregation smooths out individual post quality) and provides genuinely new information not captured by RSS feeds.
- Would require a separate UI component and backend model, not just another source in `sources.py`.

### Recommendation

**Defer as a news source. Consider later as a separate sentiment signal.**

Reddit posts are not news — they are community opinions. Forcing them through the existing news article pipeline produces misleading results (a Reddit opinion scored as +4 bullish looks identical to a Reuters report scored as +4 bullish, but carries vastly less informational weight).

If Reddit integration is pursued, build it as a **standalone social sentiment feature** with its own data model, UI section, and aggregation logic, rather than injecting posts into the news feed.

---

## Summary & Prioritized Roadmap

| Priority | Source | Effort | Value | Risk | Notes |
|----------|--------|--------|-------|------|-------|
| 1 | Benzinga RSS | Very Low | High | Low | New function in `sources.py`, ~30 lines. Active trader content. |
| 2 | MarketWatch additional feeds (Pulse, Stocks to Watch) | Very Low | Medium | Very Low | Duplicate existing function, change URL. 10 minutes of work. |
| 3 | Seeking Alpha RSS | Low | High | Medium | Cloudflare blocking may require retry/fallback logic. |
| 4 | Motley Fool RSS | Low | Medium | Low | Standard feed, good retail coverage. |
| 5 | Yahoo Finance per-ticker feeds | Medium | High | Low | Requires dynamic ticker list from Server A. |
| 6 | Reddit (as sentiment signal) | High | Medium | Medium | Separate feature, not a news source. Needs own UI/model. |
| 7 | CoinDesk RSS | Low | Low | Low | Only if crypto support is on the roadmap. |
| 8 | Telegram integration | High | Low | High | Fragile auth, legal risk, poor signal-to-noise. |
| 9 | Email scraping | High | Very Low | High | Redundant content, high maintenance, legal exposure. |

---

## Recommended Implementation Order

### Phase 1 — Quick Wins (1-2 hours total)

1. **Benzinga RSS** — Add `fetch_benzinga()` to `sources.py` using the exact pattern of `fetch_marketwatch()`. Register in `fetch_all_news()`. Set `_MAX_BENZINGA_ENTRIES = 20`. Source identifier: `"benzinga"`.

2. **MarketWatch Pulse + Stocks to Watch** — Add `fetch_mw_pulse()` and `fetch_mw_stocks()` using the MarketWatch RSS URL variants. Source identifiers: `"mw-pulse"`, `"mw-stocks"`. Consider bumping `_MAX_ARTICLES_PER_CYCLE` from 50 to 70 to accommodate the increased feed volume, if Ollama throughput permits.

### Phase 2 — Moderate Effort (half day)

3. **Seeking Alpha RSS** — Add `fetch_seeking_alpha()` with Cloudflare-aware retry logic (check for 403 status, add `Accept`, `Accept-Language`, and referrer headers). If the feed is consistently blocked, skip or fall back to Google News results mentioning "seekingalpha.com".

4. **Motley Fool RSS** — Add `fetch_motley_fool()`. Standard pattern. Source identifier: `"fool"`.

### Phase 3 — Targeted Feeds (1-2 days)

5. **Yahoo Finance per-ticker RSS** — Add a new function `fetch_yahoo_tickers(ticker_list: List[str])` that iterates over a list of popular tickers (initially hardcoded top 20-30: AAPL, MSFT, NVDA, GOOGL, AMZN, TSLA, META, etc.) and fetches `https://finance.yahoo.com/rss/headline?s={TICKER}` for each. Later, make this dynamic by querying Server A for the most-held tickers across all user portfolios (would require a new internal endpoint).

### Phase 4 — New Feature Track (separate project)

6. **Reddit Social Sentiment** — Design as a standalone feature with its own data model (`social_sentiment` table), API endpoints, and UI panel. Not part of the news feed. Requires product design work before implementation.

### Not Recommended

7. **Telegram** — Skip unless a specific, high-value public channel is identified that provides content not available through any other source.

8. **Email scraping** — Skip entirely. Any newsletter content worth capturing is available via the publisher's RSS feed or through existing aggregator sources.

---

## Impact on Existing Infrastructure

Adding 2-4 new RSS sources (Phase 1-2) has minimal infrastructure impact:

- **LLM throughput**: Adding ~40-60 more raw articles per cycle increases Ollama processing time from ~2-4 min to ~4-7 min. Still well within the 10-minute market-hours cycle. Monitor and bump `_MAX_ARTICLES_PER_CYCLE` as needed.
- **Database**: Marginal increase in `news_articles` row count. At ~100 articles/day retained for 30 days, the table stays under 5,000 rows — trivial for PostgreSQL.
- **Network**: Each additional RSS source adds one HTTP request (~200ms) per cycle. Negligible.
- **Frontend**: The `NewsPage.jsx` source badge mapping needs new entries for any new source identifiers. The existing filtering and pagination logic handles new sources automatically.
- **Schema**: No migration needed. The `source` column is `String(20)` and accepts any value. The `NewsArticleIngest` schema's source field description is documentation, not validation.
