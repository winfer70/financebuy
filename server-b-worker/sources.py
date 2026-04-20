"""
sources.py — Synchronous multi-source financial news fetcher for the TickerTap worker.

Fetches news from four sources:
  1. Yahoo Finance RSS   — general financial headlines
  2. Google News RSS     — market-related search results
  3. Finviz              — front-page news table (HTML scrape)
  4. MarketWatch RSS     — general top-stories feed

Each fetcher returns a list of article dicts with a common schema:
    {
        "title":        str,
        "url":          str,
        "source":       str,   # "yahoo" | "google" | "finviz" | "marketwatch"
        "published_at": str | None,  # ISO 8601 datetime string or None
        "summary":      str | None,  # First ~200 chars of article body
    }

The public entry point is ``fetch_all_news()`` which aggregates, deduplicates,
and returns a unified article list sorted by publication date descending.

This module uses synchronous ``requests`` (not aiohttp) because the worker
runs sequentially in a single-threaded loop on Server B.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import feedparser
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_FETCH_TIMEOUT = 15  # seconds per HTTP request
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _USER_AGENT}

# Maximum entries to extract from each source per call.
_MAX_YAHOO_ENTRIES = 20
_MAX_GOOGLE_ENTRIES = 15
_MAX_FINVIZ_ENTRIES = 20
_MAX_MARKETWATCH_ENTRIES = 25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_article(
    title: str,
    url: str,
    source: str,
    published_at: Optional[str],
    summary: Optional[str] = None,
) -> Dict:
    """Build a normalised article dict.

    Args:
        title:        Headline text.
        url:          Full URL to the article.
        source:       Source identifier (yahoo, google, finviz, marketwatch).
        published_at: ISO 8601 datetime string or None.
        summary:      First ~200 characters of article body, if available.

    Returns:
        Dict with all required article fields.
    """
    return {
        "title": title.strip(),
        "url": url.strip(),
        "source": source,
        "published_at": published_at,
        "summary": (summary or "")[:200].strip() or None,
    }


def _parse_rss_date(entry) -> Optional[str]:
    """Extract an ISO 8601 datetime string from a feedparser entry.

    Args:
        entry: A feedparser entry dict with optional ``published_parsed`` field.

    Returns:
        ISO 8601 UTC datetime string, or None if the date cannot be parsed.
    """
    parsed = entry.get("published_parsed")
    if parsed:
        try:
            dt = datetime(*parsed[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Source 1: Yahoo Finance RSS
# ---------------------------------------------------------------------------

def fetch_yahoo() -> List[Dict]:
    """Fetch general financial news headlines from Yahoo Finance RSS.

    Returns:
        List of article dicts from Yahoo Finance.
    """
    url = "https://finance.yahoo.com/news/rssindex"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_FETCH_TIMEOUT)
        if resp.status_code != 200:
            logger.debug("Yahoo RSS returned status %d", resp.status_code)
            return []
    except Exception as exc:
        logger.debug("Yahoo RSS fetch failed: %s", exc)
        return []

    feed = feedparser.parse(resp.text)
    articles = []
    for entry in feed.entries[:_MAX_YAHOO_ENTRIES]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        articles.append(
            _make_article(
                title=title,
                url=link,
                source="yahoo",
                published_at=_parse_rss_date(entry),
                summary=entry.get("summary"),
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Source 2: Google News RSS
# ---------------------------------------------------------------------------

def fetch_google() -> List[Dict]:
    """Fetch financial market news from Google News RSS search.

    Uses a broad "stock market" query to capture general financial headlines
    rather than per-ticker searches (the LLM identifies affected tickers).

    Returns:
        List of article dicts from Google News.
    """
    url = (
        "https://news.google.com/rss/search?"
        "q=stock+market+OR+earnings+OR+finance"
        "&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_FETCH_TIMEOUT)
        if resp.status_code != 200:
            logger.debug("Google News RSS returned status %d", resp.status_code)
            return []
    except Exception as exc:
        logger.debug("Google News RSS fetch failed: %s", exc)
        return []

    feed = feedparser.parse(resp.text)
    articles = []
    for entry in feed.entries[:_MAX_GOOGLE_ENTRIES]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        articles.append(
            _make_article(
                title=title,
                url=link,
                source="google",
                published_at=_parse_rss_date(entry),
                summary=entry.get("summary"),
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Source 3: Finviz HTML scrape
# ---------------------------------------------------------------------------

def fetch_finviz() -> List[Dict]:
    """Scrape the Finviz front-page news table for financial headlines.

    Parses the news table from Finviz's main page rather than per-ticker
    quote pages, capturing broad market headlines.

    Returns:
        List of article dicts from Finviz.
    """
    url = "https://finviz.com/news.ashx"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_FETCH_TIMEOUT)
        if resp.status_code != 200:
            logger.debug("Finviz returned status %d", resp.status_code)
            return []
    except Exception as exc:
        logger.debug("Finviz fetch failed: %s", exc)
        return []

    articles = []
    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        # Finviz news page contains tables with class "news-table" or
        # rows within the "news" content area.
        news_tables = soup.find_all("table", class_="t-home-table")
        if not news_tables:
            # Fallback: try the news-table id used on quote pages.
            news_tables = soup.find_all("table", {"id": "news-table"})
        for table in news_tables:
            rows = table.find_all("tr")
            for row in rows[:_MAX_FINVIZ_ENTRIES]:
                link_tag = row.find("a", class_="tab-link-news")
                if not link_tag:
                    link_tag = row.find("a")
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
                        published_at=None,  # Finviz shows relative dates, skip parsing
                    )
                )
    except Exception as exc:
        logger.debug("Finviz HTML parse failed: %s", exc)

    return articles


# ---------------------------------------------------------------------------
# Source 4: MarketWatch RSS
# ---------------------------------------------------------------------------

def fetch_marketwatch() -> List[Dict]:
    """Fetch general market news from MarketWatch top-stories RSS feed.

    Returns:
        List of article dicts from MarketWatch.
    """
    url = "https://feeds.marketwatch.com/marketwatch/topstories"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_FETCH_TIMEOUT)
        if resp.status_code != 200:
            logger.debug("MarketWatch RSS returned status %d", resp.status_code)
            return []
    except Exception as exc:
        logger.debug("MarketWatch RSS fetch failed: %s", exc)
        return []

    feed = feedparser.parse(resp.text)
    articles = []
    for entry in feed.entries[:_MAX_MARKETWATCH_ENTRIES]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        articles.append(
            _make_article(
                title=title,
                url=link,
                source="marketwatch",
                published_at=_parse_rss_date(entry),
                summary=entry.get("summary"),
            )
        )
    return articles


# ---------------------------------------------------------------------------
# Public aggregator
# ---------------------------------------------------------------------------

def fetch_all_news() -> List[Dict]:
    """Fetch and aggregate news from all four configured sources.

    Calls each source fetcher sequentially (worker runs as a single-threaded
    loop), deduplicates by URL, and returns a unified list sorted by
    published_at descending (articles without dates sink to the bottom).

    Returns:
        Deduplicated list of article dicts sorted by publication date.
    """
    all_articles: List[Dict] = []

    # Fetch from each source; catch per-source exceptions so one failure
    # doesn't block the others.
    for fetcher_name, fetcher_fn in [
        ("Yahoo", fetch_yahoo),
        ("Google", fetch_google),
        ("Finviz", fetch_finviz),
        ("MarketWatch", fetch_marketwatch),
    ]:
        try:
            results = fetcher_fn()
            logger.info("Fetched %d articles from %s", len(results), fetcher_name)
            all_articles.extend(results)
        except Exception as exc:
            logger.error("Source %s raised an unexpected error: %s", fetcher_name, exc)

    # Deduplicate by URL.
    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        url = article.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_articles.append(article)

    # Sort by published_at descending; None dates sink to the bottom.
    def _sort_key(a):
        dt_str = a.get("published_at")
        if dt_str:
            try:
                return datetime.fromisoformat(dt_str)
            except (ValueError, TypeError):
                pass
        return datetime.min.replace(tzinfo=timezone.utc)

    unique_articles.sort(key=_sort_key, reverse=True)

    logger.info(
        "Total unique articles after dedup: %d (from %d raw)",
        len(unique_articles),
        len(all_articles),
    )
    return unique_articles
