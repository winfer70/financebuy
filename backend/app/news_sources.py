"""
news_sources.py — Multi-source financial news aggregation for TickerTap.

Fetches news from four sources:
  1. Yahoo Finance RSS   — per-ticker headline feeds
  2. Google News RSS     — per-ticker search results
  3. Finviz              — per-ticker news table (HTML scrape)
  4. MarketWatch RSS     — general top-stories feed

All fetchers are async and return a common article dict format.
`fetch_all_news()` orchestrates concurrent fetching, deduplication,
and returns a unified article list.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import aiohttp
import feedparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_FETCH_TIMEOUT = aiohttp.ClientTimeout(total=10)
_CONCURRENCY = asyncio.Semaphore(5)
_MAX_TICKERS_PER_SOURCE = 10
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Helper — normalise an article dict
# ---------------------------------------------------------------------------
def _make_article(
    title: str,
    url: str,
    source: str,
    published_at: Optional[datetime],
    tickers: List[str],
    summary: Optional[str] = None,
) -> Dict:
    """Build a normalised article dict.

    Args:
        title:        Headline text.
        url:          Full URL to the article.
        source:       Source identifier (yahoo, google, finviz, marketwatch).
        published_at: Publication datetime (UTC) or None.
        tickers:      List of associated ticker symbols.
        summary:      First ~200 characters of article body, if available.

    Returns:
        Dict with all article fields plus defaults for sentiment/portfolio.
    """
    return {
        "title": title.strip(),
        "url": url.strip(),
        "source": source,
        "published_at": published_at,
        "tickers": tickers,
        "in_portfolio": False,  # Populated later by the route handler.
        "sentiment": "neutral",
        "sentiment_score": 0.0,
        "summary": (summary or "")[:200].strip() or None,
    }


def _parse_rss_date(entry) -> Optional[datetime]:
    """Extract a timezone-aware datetime from a feedparser entry.

    Args:
        entry: A feedparser entry dict with optional published_parsed field.

    Returns:
        A UTC datetime, or None if the date cannot be parsed.
    """
    parsed = entry.get("published_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Source 1: Yahoo Finance RSS
# ---------------------------------------------------------------------------
async def _fetch_yahoo(
    ticker: str,
    session: aiohttp.ClientSession,
) -> List[Dict]:
    """Fetch news articles for a single ticker from Yahoo Finance RSS.

    Args:
        ticker:  Stock ticker symbol (e.g. "AAPL").
        session: Shared aiohttp client session.

    Returns:
        List of article dicts from Yahoo Finance.
    """
    url = f"https://finance.yahoo.com/rss/headline?s={ticker}"
    async with _CONCURRENCY:
        try:
            async with session.get(url, timeout=_FETCH_TIMEOUT) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
        except Exception as exc:
            logger.debug("Yahoo RSS fetch failed for %s: %s", ticker, exc)
            return []

    feed = feedparser.parse(text)
    articles = []
    for entry in feed.entries[:15]:
        articles.append(
            _make_article(
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                source="yahoo",
                published_at=_parse_rss_date(entry),
                tickers=[ticker],
                summary=entry.get("summary"),
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Source 2: Google News RSS
# ---------------------------------------------------------------------------
async def _fetch_google(
    ticker: str,
    session: aiohttp.ClientSession,
) -> List[Dict]:
    """Fetch news articles for a single ticker from Google News RSS search.

    Args:
        ticker:  Stock ticker symbol (e.g. "AAPL").
        session: Shared aiohttp client session.

    Returns:
        List of article dicts from Google News.
    """
    query = f"{ticker}+stock"
    url = (
        f"https://news.google.com/rss/search?q={query}"
        "&hl=en-US&gl=US&ceid=US:en"
    )
    async with _CONCURRENCY:
        try:
            async with session.get(url, timeout=_FETCH_TIMEOUT) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
        except Exception as exc:
            logger.debug("Google News fetch failed for %s: %s", ticker, exc)
            return []

    feed = feedparser.parse(text)
    articles = []
    for entry in feed.entries[:10]:
        articles.append(
            _make_article(
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                source="google",
                published_at=_parse_rss_date(entry),
                tickers=[ticker],
                summary=entry.get("summary"),
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Source 3: Finviz HTML scrape
# ---------------------------------------------------------------------------
async def _fetch_finviz(
    ticker: str,
    session: aiohttp.ClientSession,
) -> List[Dict]:
    """Scrape news articles for a single ticker from the Finviz quote page.

    Args:
        ticker:  Stock ticker symbol (e.g. "AAPL").
        session: Shared aiohttp client session.

    Returns:
        List of article dicts from Finviz.
    """
    url = f"https://finviz.com/quote.ashx?t={ticker}&p=d"
    headers = {"User-Agent": _USER_AGENT}
    async with _CONCURRENCY:
        try:
            async with session.get(
                url, timeout=_FETCH_TIMEOUT, headers=headers
            ) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
        except Exception as exc:
            logger.debug("Finviz fetch failed for %s: %s", ticker, exc)
            return []

    articles = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        # Finviz news table has id="news-table".
        news_table = soup.find("table", {"id": "news-table"})
        if not news_table:
            return []
        rows = news_table.find_all("tr")
        for row in rows[:15]:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            link_tag = cells[1].find("a")
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            href = link_tag.get("href", "")
            if not title or not href:
                continue
            articles.append(
                _make_article(
                    title=title,
                    url=href,
                    source="finviz",
                    published_at=None,  # Finviz dates are relative, skip parsing.
                    tickers=[ticker],
                )
            )
    except Exception as exc:
        logger.debug("Finviz HTML parse failed for %s: %s", ticker, exc)

    return articles


# ---------------------------------------------------------------------------
# Source 4: MarketWatch RSS (general, not per-ticker)
# ---------------------------------------------------------------------------
async def _fetch_marketwatch(
    portfolio_tickers: Set[str],
    session: aiohttp.ClientSession,
) -> List[Dict]:
    """Fetch general market news from MarketWatch top-stories RSS feed.

    Articles are scanned for known portfolio tickers in the headline text.

    Args:
        portfolio_tickers: Set of ticker symbols the user holds.
        session:           Shared aiohttp client session.

    Returns:
        List of article dicts from MarketWatch, with ticker associations.
    """
    url = "https://feeds.marketwatch.com/marketwatch/topstories"
    async with _CONCURRENCY:
        try:
            async with session.get(url, timeout=_FETCH_TIMEOUT) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()
        except Exception as exc:
            logger.debug("MarketWatch RSS fetch failed: %s", exc)
            return []

    feed = feedparser.parse(text)
    # Pre-compile a regex that matches any portfolio ticker as a whole word.
    if portfolio_tickers:
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(t) for t in portfolio_tickers) + r")\b",
            re.IGNORECASE,
        )
    else:
        pattern = None

    articles = []
    for entry in feed.entries[:20]:
        title = entry.get("title", "")
        matched: List[str] = []
        if pattern:
            matched = list(set(m.upper() for m in pattern.findall(title)))
        articles.append(
            _make_article(
                title=title,
                url=entry.get("link", ""),
                source="marketwatch",
                published_at=_parse_rss_date(entry),
                tickers=matched,
                summary=entry.get("summary"),
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Public aggregator
# ---------------------------------------------------------------------------
async def fetch_all_news(
    tickers: List[str],
    portfolio_tickers: Optional[Set[str]] = None,
) -> List[Dict]:
    """Fetch and aggregate news from all configured sources.

    Limits per-ticker requests to the first ``_MAX_TICKERS_PER_SOURCE``
    tickers to avoid excessive outbound traffic.

    Args:
        tickers:            Ordered list of tickers to fetch (top-N used).
        portfolio_tickers:  Full set of portfolio tickers for MarketWatch
                            headline scanning.  Defaults to the tickers list
                            converted to a set.

    Returns:
        Deduplicated list of article dicts sorted by published_at descending.
    """
    if portfolio_tickers is None:
        portfolio_tickers = set(tickers)

    # Limit to top N tickers per source.
    limited = tickers[:_MAX_TICKERS_PER_SOURCE]

    async with aiohttp.ClientSession(
        headers={"User-Agent": _USER_AGENT}
    ) as session:
        # Build coroutine list: per-ticker sources + MarketWatch general feed.
        tasks: List[asyncio.Task] = []
        for t in limited:
            tasks.append(asyncio.ensure_future(_fetch_yahoo(t, session)))
            tasks.append(asyncio.ensure_future(_fetch_google(t, session)))
            tasks.append(asyncio.ensure_future(_fetch_finviz(t, session)))
        tasks.append(
            asyncio.ensure_future(_fetch_marketwatch(portfolio_tickers, session))
        )

        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Flatten and deduplicate by URL.
    seen_urls: Set[str] = set()
    articles: List[Dict] = []
    for result in results:
        if isinstance(result, Exception):
            logger.debug("Source fetch raised: %s", result)
            continue
        for article in result:
            url = article.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                articles.append(article)

    # Sort by published_at descending (None dates sink to the bottom).
    articles.sort(
        key=lambda a: a["published_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return articles


async def fetch_ticker_news(ticker: str) -> List[Dict]:
    """Fetch news for a single ticker from all sources (on-demand deep fetch).

    Unlike fetch_all_news() this bypasses the top-10 limit and fetches
    from every source for exactly one ticker.

    Args:
        ticker: Stock ticker symbol to fetch news for.

    Returns:
        Deduplicated list of article dicts sorted by published_at descending.
    """
    async with aiohttp.ClientSession(
        headers={"User-Agent": _USER_AGENT}
    ) as session:
        results = await asyncio.gather(
            _fetch_yahoo(ticker, session),
            _fetch_google(ticker, session),
            _fetch_finviz(ticker, session),
            return_exceptions=True,
        )

    seen_urls: Set[str] = set()
    articles: List[Dict] = []
    for result in results:
        if isinstance(result, Exception):
            logger.debug("Ticker fetch raised for %s: %s", ticker, result)
            continue
        for article in result:
            url = article.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                articles.append(article)

    articles.sort(
        key=lambda a: a["published_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return articles
