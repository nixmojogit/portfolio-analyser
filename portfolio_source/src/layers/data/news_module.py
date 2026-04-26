"""
news_module.py
Layer      : Data
Owns       : SKILL-D09, SKILL-D10
Description: Fetches financial news headlines from RSS feeds of Indian
             financial publications and official NSE/BSE corporate
             announcements. Uses a two-stage relevance filter:
             Stage 1 — Google News pre-filtered by ticker symbol query
             Stage 2 — Title must contain full company name OR ticker,
                        or at least two distinctive words simultaneously.
"""

from __future__ import annotations
import hashlib
import re
import time
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus

import feedparser
import requests

from src.layers.data.cache_manager import cache_read, cache_write
from src.layers.configuration.config_manager import get_skill_ttl
from src.utils.logger import get_logger

log = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# General market RSS feeds
RSS_FEEDS = {
    "economic_times":   "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "business_standard":"https://www.business-standard.com/rss/markets-106.rss",
    "moneycontrol":     "https://www.moneycontrol.com/rss/marketsnews.xml",
}

NSE_ANNOUNCEMENTS_URL = (
    "https://www.nseindia.com/api/corp-info"
    "?symbol={symbol}&corpType=announcements"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Legal suffixes — never meaningful identifiers on their own
LEGAL_SUFFIXES = {
    "limited", "ltd", "pvt", "private", "company", "corp",
    "corporation", "inds", "and", "the", "of", "for", "with",
}

# Patterns indicating a market-wide roundup rather than a stock-specific story
ROUNDUP_PATTERNS = [
    "stocks to watch", "top gainers", "top losers", "market wrap",
    "buzzing stocks", "stocks in news", "trading ideas", "multibagger",
    "penny stocks", "smallcap", "midcap", "sensex", "nifty today",
    "among others", "and others", ", others", "& others",
]


# ── Search Term Builder ───────────────────────────────────────────────────────

def _build_search_terms(company_name: str, ticker: str) -> dict[str, Any]:
    """
    Build structured search terms for a company.
    Returns a dict with:
        ticker_base   : NSE ticker without suffix e.g. 'HDFCBANK'
        full_name     : full company name lowercased
        words         : list of individual distinctive words (>2 chars, not legal suffix)
        all_terms     : flat list of all terms for simple matching
    Ticker is always the primary identifier — unique and unambiguous.
    """
    ticker_base = ticker.split(".")[0].upper()
    full_name   = company_name.lower().strip()

    # Individual distinctive words — skip legal suffixes only
    words = []
    for word in company_name.split():
        cleaned = re.sub(r"[^a-zA-Z0-9]", "", word).lower()
        if len(cleaned) > 2 and cleaned not in LEGAL_SUFFIXES:
            words.append(cleaned)

    all_terms = list({ticker_base.lower(), full_name} | set(words))

    return {
        "ticker_base": ticker_base,
        "full_name":   full_name,
        "words":       words,
        "all_terms":   all_terms,
    }


# ── Two-Stage Relevance Filter ────────────────────────────────────────────────

def _is_relevant(
    title: str,
    terms: dict,
    strict: bool = True,
) -> bool:
    """
    Two-stage relevance check.

    Stage 1 — Strong match (any of these passes immediately):
      a) Ticker base appears in title  e.g. 'HDFCBANK' in title
      b) Full company name appears in title  e.g. 'hdfc bank' in title

    Stage 2 — Weak match (requires two conditions):
      a) At least TWO distinctive words appear simultaneously in the title
      b) AND the headline is NOT a market roundup

    strict=True  : applies both stages (for general RSS feeds)
    strict=False : only requires Stage 1 (for Google News, pre-filtered by query)

    This prevents single generic words like 'bank', 'sun', 'tata'
    from triggering a false match when they appear alone.
    """
    title_lower  = title.lower()
    ticker_base  = terms["ticker_base"].lower()
    full_name    = terms["full_name"]
    words        = terms["words"]

    # ── Stage 1: Strong match ─────────────────────────────────────────────────
    # a) Ticker base in title (most reliable — always unique)
    if ticker_base in title_lower:
        return True

    # b) Full company name phrase in title
    if full_name in title_lower:
        return True

    # For Google News (strict=False), Stage 1 is sufficient
    if not strict:
        return False

    # ── Stage 2: Weak match (general feeds only) ──────────────────────────────
    # Count how many distinctive words appear in the title
    matched_words = [w for w in words if w in title_lower]

    if len(matched_words) < 2:
        return False

    # Reject market roundup headlines
    if any(p in title_lower for p in ROUNDUP_PATTERNS):
        return False

    return True


# ── URL Builders ──────────────────────────────────────────────────────────────

def _build_google_news_url(ticker_base: str, company_name: str) -> str:
    """
    Build Google News RSS URL using ticker as primary search term.
    Ticker-first ensures results are pre-filtered to this specific stock.
    """
    query = quote_plus(f"{ticker_base} NSE {company_name} share")
    return (
        f"https://news.google.com/rss/search"
        f"?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    )


# ── Feed Parser ───────────────────────────────────────────────────────────────

def _parse_feed_date(entry) -> datetime | None:
    """Parse a feedparser entry published date to datetime."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6])
        if hasattr(entry, "updated_parsed") and entry.updated_parsed:
            return datetime(*entry.updated_parsed[:6])
    except Exception:
        pass
    return None


def _headline_id(title: str, source: str) -> str:
    """Generate a deduplication hash for a headline."""
    raw = f"{source}:{title.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _deduplicate(headlines: list[dict]) -> list[dict]:
    """Remove duplicate headlines across sources."""
    seen:   set  = set()
    unique: list = []
    for h in headlines:
        hid = _headline_id(h["title"], h["source"])
        if hid not in seen:
            seen.add(hid)
            unique.append(h)
    return unique


def _parse_feed(
    feed_url: str,
    terms: dict,
    cutoff: datetime,
    source_name: str,
    strict: bool = True,
) -> list[dict]:
    """
    Parse a single RSS feed URL.
    strict=True  : two-stage filter (for general feeds)
    strict=False : stage-1 only (for Google News, pre-filtered by query)
    """
    results: list[dict] = []
    try:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            title   = getattr(entry, "title",   "") or ""
            summary = getattr(entry, "summary", "") or ""
            link    = getattr(entry, "link",    "") or ""
            pub_dt  = _parse_feed_date(entry)

            # Date filter
            if pub_dt and pub_dt < cutoff:
                continue

            # Relevance filter
            if not _is_relevant(title, terms, strict=strict):
                continue

            results.append({
                "title":          title.strip(),
                "summary":        summary[:300].strip(),
                "source":         source_name,
                "published_date": pub_dt.isoformat() if pub_dt else None,
                "url":            link,
            })
    except Exception as e:
        log.debug(f"[SKILL-D09] Feed parse error ({source_name}): {e}")
    return results


# ── SKILL-D09: Fetch RSS News Feeds ──────────────────────────────────────────

def fetch_rss_news_feeds(
    company_name: str,
    ticker: str,
    days_lookback: int = 90,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D09: Fetch RSS News Feeds.
    Two-stage relevance strategy:
    - Google News: ticker-first query (pre-filtered), relaxed check
    - General feeds (ET/BS/MC): strict two-stage filter
    """
    skill_id  = "SKILL-D09"
    base      = ticker.split(".")[0].upper()
    ttl       = get_skill_ttl(config, skill_id) if config else 6
    cache_key = f"{base}_rss_{days_lookback}d"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        return {"headlines": cached["cached_data"]["headlines"]}

    log.info(f"[{skill_id}] Fetching news for: {company_name} ({ticker})")

    terms  = _build_search_terms(company_name, ticker)
    cutoff = datetime.now() - timedelta(days=days_lookback)
    all_headlines: list[dict] = []

    # ── Google News (ticker-first query, stage-1 filter only) ────────────────
    google_url = _build_google_news_url(terms["ticker_base"], company_name)
    google_hl  = _parse_feed(google_url, terms, cutoff, "google_news", strict=False)
    all_headlines.extend(google_hl)
    log.debug(f"[{skill_id}] Google News: {len(google_hl)} headlines")

    # ── General RSS feeds (two-stage filter) ──────────────────────────────────
    general_count = 0
    for source_name, feed_url in RSS_FEEDS.items():
        parsed = _parse_feed(feed_url, terms, cutoff, source_name, strict=True)
        all_headlines.extend(parsed)
        general_count += len(parsed)
        time.sleep(0.3)
    log.debug(f"[{skill_id}] General feeds: {general_count} headlines")

    unique = _deduplicate(all_headlines)
    unique.sort(key=lambda h: h.get("published_date") or "", reverse=True)

    log.info(
        f"[{skill_id}] {company_name}: {len(unique)} headlines "
        f"(Google: {len(google_hl)}, General: {general_count})"
    )
    cache_write(skill_id, cache_key, {"headlines": unique})
    return {"headlines": unique}


# ── SKILL-D10: Fetch NSE/BSE Corporate Announcements ─────────────────────────

def fetch_corporate_announcements(
    ticker: str,
    days_lookback: int = 90,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D10: Fetch NSE/BSE Corporate Announcements.
    Official announcements are always stock-specific — no filter needed.
    """
    skill_id  = "SKILL-D10"
    base      = ticker.split(".")[0].upper()
    ttl       = get_skill_ttl(config, skill_id) if config else 6
    cache_key = f"{base}_announcements_{days_lookback}d"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        data = cached["cached_data"]
        return {
            "announcements":          data.get("announcements", []),
            "earnings_announcements": data.get("earnings_announcements", []),
            "insider_disclosures":    data.get("insider_disclosures", []),
        }

    log.info(f"[{skill_id}] Fetching NSE announcements: {base}")
    announcements = _fetch_nse_announcements(base, days_lookback)
    earnings      = _filter_announcements(announcements, [
        "financial result", "quarterly result", "annual result",
        "earnings", "q1", "q2", "q3", "q4",
    ])
    insider       = _filter_announcements(announcements, [
        "insider", "sast", "shareholding", "acquisition",
        "pledge", "encumber",
    ])

    result = {
        "announcements":          announcements,
        "earnings_announcements": earnings,
        "insider_disclosures":    insider,
    }
    cache_write(skill_id, cache_key, result)
    return result


def _fetch_nse_announcements(symbol: str, days_lookback: int) -> list[dict]:
    """Fetch corporate announcements from NSE India."""
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=HEADERS, timeout=10)
        time.sleep(1)
        url  = NSE_ANNOUNCEMENTS_URL.format(symbol=symbol)
        resp = session.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        cutoff  = datetime.now() - timedelta(days=days_lookback)
        records = data if isinstance(data, list) else data.get("data", [])
        results = []

        for rec in records:
            date_str = (
                rec.get("exchdisstime") or rec.get("date") or
                rec.get("bcastDate")   or ""
            )
            try:
                ann_dt = datetime.strptime(date_str[:10], "%d-%b-%Y")
            except ValueError:
                try:
                    ann_dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                except ValueError:
                    ann_dt = None

            if ann_dt and ann_dt < cutoff:
                continue

            results.append({
                "date":     date_str,
                "subject":  rec.get("subject") or rec.get("desc") or "",
                "category": rec.get("category") or "",
                "exchange": "NSE",
                "url":      rec.get("attchmntFile") or "",
            })

        log.info(f"[SKILL-D10] {len(results)} announcements for {symbol}")
        return results

    except Exception as e:
        log.debug(f"[SKILL-D10] NSE announcements unavailable for {symbol}: {e}")
        return []


def _filter_announcements(
    announcements: list[dict],
    keywords: list[str],
) -> list[dict]:
    """Filter announcements by keyword match on subject field."""
    return [
        a for a in announcements
        if any(kw in a.get("subject", "").lower() for kw in keywords)
    ]