"""
sentiment_module.py
Layer      : Intelligence
Owns       : SKILL-I18, SKILL-I19, SKILL-I20
Description: Scores news sentiment via Claude AI and extracts analyst
             signals (rating, target price, firm) from headlines.
             Uses purpose-specific lookback windows for accuracy.
             Source tracking: news_extraction > screener > yfinance.
"""

from __future__ import annotations
import json
import os
import time
from datetime import datetime, timedelta
from typing import Any

import anthropic
from dotenv import load_dotenv

from src.layers.data.cache_manager import cache_read, cache_write
from src.layers.configuration.config_manager import get_skill_ttl
from src.utils.logger import get_logger

load_dotenv()
log = get_logger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-5"
MAX_RETRIES  = 3
BACKOFF_BASE = 2

# Data source constants
SOURCE_NEWS      = "news_extraction"
SOURCE_SCREENER  = "screener"
SOURCE_YFINANCE  = "yfinance"
SOURCE_NONE      = None


# ── Utilities ─────────────────────────────────────────────────────────────────

def _safe_float(val) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not found in environment")
    return anthropic.Anthropic(api_key=api_key)


def _filter_by_days(
    headlines: list[dict],
    days: int,
) -> list[dict]:
    """Filter headlines to only those within the last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    result = []
    for h in headlines:
        pub = h.get("published_date")
        if pub is None:
            result.append(h)   # include if date unknown
            continue
        try:
            dt = datetime.fromisoformat(pub[:19])
            if dt >= cutoff:
                result.append(h)
        except Exception:
            result.append(h)   # include if date unparseable
    return result


def _call_claude_with_retry(
    client: anthropic.Anthropic,
    prompt: str,
) -> str:
    """Call Claude AI with exponential backoff retry on overload."""
    for attempt in range(MAX_RETRIES):
        try:
            msg = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < MAX_RETRIES - 1:
                wait = BACKOFF_BASE ** (attempt + 1)
                log.warning(f"[SKILL-I18] Overloaded — retry {attempt+1} in {wait}s")
                time.sleep(wait)
            else:
                raise
        except anthropic.APIConnectionError as e:
            if attempt < MAX_RETRIES - 1:
                wait = BACKOFF_BASE ** (attempt + 1)
                log.warning(f"[SKILL-I18] Connection error — retry in {wait}s")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"Claude API failed after {MAX_RETRIES} retries")


# ── Prompt Builder ────────────────────────────────────────────────────────────

def _build_combined_prompt(
    sentiment_headlines: list[dict],
    analyst_headlines: list[dict],
    company_name: str,
    ticker: str,
) -> str:
    """
    Build a single Claude prompt that extracts both:
    1. News sentiment score (from last 30 days)
    2. Analyst signals — rating, target price, firm (from last 90 days)
    Single API call — no extra cost.
    """
    sentiment_text = "\n".join(
        f"- [{h.get('source','?')}] {h.get('title','')}"
        for h in sentiment_headlines[:15]
    )
    analyst_text = "\n".join(
        f"- [{h.get('source','?')}] {h.get('title','')}"
        for h in analyst_headlines[:20]
    )

    return f"""You are a financial analyst for Indian stock markets.
Analyse the following headlines about {company_name} ({ticker}).

SECTION A — SENTIMENT (last 30 days headlines):
{sentiment_text if sentiment_text else "No recent headlines available."}

SECTION B — ANALYST SIGNALS (last 90 days headlines):
{analyst_text if analyst_text else "No analyst headlines available."}

Return ONLY a valid JSON object with exactly these fields — no other text:
{{
  "sentiment_score": <integer 0-100>,
  "sentiment_label": "<positive|neutral|negative>",
  "key_positive_themes": [<up to 3 short strings>],
  "key_negative_themes": [<up to 3 short strings>],
  "confidence": "<high|medium|low>",
  "analyst_ratings": [
    {{
      "firm": "<brokerage name or null>",
      "rating": "<Buy|Hold|Sell|Upgrade|Downgrade|Neutral or null>",
      "target_price": <number or null>,
      "action": "<initiates|upgrades|downgrades|maintains|cuts|raises or null>",
      "source_headline": "<brief excerpt or null>"
    }}
  ],
  "consensus_rating": "<Buy|Hold|Sell|null>",
  "latest_target_price": <number or null>,
  "target_price_currency": "INR"
}}

Rules for analyst_ratings:
- Only extract if a brokerage name, rating, or target price is explicitly mentioned
- Return empty list [] if no analyst signals found in headlines
- consensus_rating: derive from multiple ratings if available, else null
- latest_target_price: use the most recent target price mentioned, else null
- Do NOT invent ratings — only extract what is explicitly stated"""


# ── SKILL-I18: Score News Sentiment + Extract Analyst Signals ─────────────────

def score_news_sentiment(
    headlines: list[dict],
    company_name: str,
    ticker: str,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I18: Score News Sentiment via Claude AI + Extract Analyst Signals.
    Uses purpose-specific lookback windows:
    - Sentiment scoring: last 30 days (system.news_sentiment_lookback_days)
    - Analyst extraction: last 90 days (system.analyst_signal_lookback_days)
    Single Claude API call covers both — no extra cost.
    Args:
        headlines    : all fetched headlines (will be filtered internally)
        company_name : company name for context
        ticker       : ticker symbol
        config       : merged config dict
    Returns: dict with sentiment fields + analyst_data dict with source tracking
    """
    skill_id  = "SKILL-I18"
    base      = ticker.split(".")[0].upper()
    ttl       = get_skill_ttl(config, skill_id) if config else 12
    cache_key = f"{base}_sentiment"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        log.debug(f"[{skill_id}] Serving cached sentiment for {base}")
        return cached["cached_data"]

    # Purpose-specific lookback windows from config
    sys_cfg         = (config or {}).get("system", {})
    sentiment_days  = sys_cfg.get("news_sentiment_lookback_days", 30)
    analyst_days    = sys_cfg.get("analyst_signal_lookback_days", 90)

    # Filter headlines by purpose
    sentiment_headlines = _filter_by_days(headlines, sentiment_days)
    analyst_headlines   = _filter_by_days(headlines, analyst_days)

    log.info(
        f"[{skill_id}] {company_name}: "
        f"{len(sentiment_headlines)} sentiment headlines ({sentiment_days}d), "
        f"{len(analyst_headlines)} analyst headlines ({analyst_days}d)"
    )

    # No headlines at all → neutral result
    if not headlines:
        result = _neutral_sentiment("No headlines available for sentiment scoring.")
        cache_write(skill_id, cache_key, result)
        return result

    # Check skill enabled
    from src.layers.configuration.config_manager import is_skill_enabled
    if config and not is_skill_enabled(config, skill_id):
        result = _neutral_sentiment("SKILL-I18 disabled in skills.yaml")
        cache_write(skill_id, cache_key, result)
        return result

    try:
        client = _get_client()
        prompt = _build_combined_prompt(
            sentiment_headlines, analyst_headlines, company_name, ticker
        )
        raw   = _call_claude_with_retry(client, prompt)

        # Strip markdown fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()

        data = json.loads(clean)

        # ── Sentiment fields ──────────────────────────────────────────────────
        sentiment_score = int(data.get("sentiment_score", 50))
        if len(sentiment_headlines) < 3:
            confidence = "low"
        else:
            confidence = data.get("confidence", "medium")

        # ── Analyst signal extraction ─────────────────────────────────────────
        analyst_ratings   = data.get("analyst_ratings", [])
        consensus_rating  = data.get("consensus_rating")
        latest_target     = data.get("latest_target_price")

        # Build structured analyst_data with source tracking
        analyst_data = _build_analyst_data(
            analyst_ratings, consensus_rating, latest_target
        )

        result = {
            "sentiment_score":      sentiment_score,
            "sentiment_label":      data.get("sentiment_label", "neutral"),
            "key_positive_themes":  data.get("key_positive_themes", []),
            "key_negative_themes":  data.get("key_negative_themes", []),
            "confidence":           confidence,
            "analyst_data":         analyst_data,
        }

        log.info(
            f"[{skill_id}] {company_name}: "
            f"score={sentiment_score} label={result['sentiment_label']} "
            f"analyst_rating={analyst_data.get('rating',{}).get('value','N/A')} "
            f"target={analyst_data.get('target_price',{}).get('value','N/A')}"
        )

        cache_write(skill_id, cache_key, result)
        return result

    except json.JSONDecodeError as e:
        log.warning(f"[{skill_id}] JSON parse error: {e}")
        return _neutral_sentiment("JSON parse error from Claude response")
    except Exception as e:
        log.warning(f"[{skill_id}] Sentiment scoring failed: {e}")
        return _neutral_sentiment(str(e))


def _build_analyst_data(
    analyst_ratings: list[dict],
    consensus_rating: str | None,
    latest_target: float | None,
) -> dict[str, Any]:
    """
    Build structured analyst_data dict with source tracking.
    All values from news extraction are tagged SOURCE_NEWS.
    """
    # Latest rating from extracted signals
    rating_val  = None
    rating_firm = None
    rating_action = None

    if analyst_ratings:
        latest = analyst_ratings[0]
        rating_val    = latest.get("rating")
        rating_firm   = latest.get("firm")
        rating_action = latest.get("action")

    # Use consensus if available, else latest individual rating
    final_rating = consensus_rating or rating_val

    return {
        "rating": {
            "value":  final_rating,
            "firm":   rating_firm,
            "action": rating_action,
            "source": SOURCE_NEWS if final_rating else SOURCE_NONE,
        },
        "target_price": {
            "value":  latest_target,
            "source": SOURCE_NEWS if latest_target else SOURCE_NONE,
        },
        "target_mean":  {"value": None, "source": SOURCE_NONE},
        "target_low":   {"value": None, "source": SOURCE_NONE},
        "target_high":  {"value": None, "source": SOURCE_NONE},
        "all_ratings":  analyst_ratings,
    }


def _neutral_sentiment(note: str = "") -> dict[str, Any]:
    """Return a neutral sentiment result with empty analyst data."""
    return {
        "sentiment_score":     50,
        "sentiment_label":     "neutral",
        "key_positive_themes": [],
        "key_negative_themes": [],
        "confidence":          "low",
        "note":                note,
        "analyst_data": {
            "rating":       {"value": None, "firm": None, "action": None, "source": SOURCE_NONE},
            "target_price": {"value": None, "source": SOURCE_NONE},
            "target_mean":  {"value": None, "source": SOURCE_NONE},
            "target_low":   {"value": None, "source": SOURCE_NONE},
            "target_high":  {"value": None, "source": SOURCE_NONE},
            "all_ratings":  [],
        },
    }


# ── Analyst Data Priority Resolver ────────────────────────────────────────────

def resolve_analyst_data(
    sentiment_result: dict,
    ratios: dict,
    screener_data: dict | None = None,
) -> dict[str, Any]:
    """
    Apply priority stack for analyst data:
    Priority 1: news_extraction (Claude AI from headlines)
    Priority 2: screener (Screener.in)
    Priority 3: yfinance (ratios dict — fallback)

    Returns resolved analyst_data dict with source tags on every field.
    """
    news_analyst = sentiment_result.get("analyst_data", {})
    screener     = screener_data or {}

    def _resolve(field: str, yf_key: str, yf_key2: str | None = None) -> dict:
        """Resolve a single field through the priority stack."""
        # Priority 1 — news extraction
        news_val = news_analyst.get(field, {}).get("value")
        if news_val is not None:
            return {
                "value":  news_val,
                "source": SOURCE_NEWS,
                "note":   None,
            }
        # Priority 2 — screener
        scr_val = screener.get(field)
        if scr_val is not None:
            return {
                "value":  scr_val,
                "source": SOURCE_SCREENER,
                "note":   None,
            }
        # Priority 3 — yfinance fallback
        yf_val = ratios.get(yf_key)
        if yf_val is None and yf_key2:
            yf_val = ratios.get(yf_key2)
        if yf_val is not None:
            return {
                "value":  yf_val,
                "source": SOURCE_YFINANCE,
                "note":   "Fallback — may not reflect latest analyst views",
            }
        return {"value": None, "source": SOURCE_NONE, "note": None}

    # Resolve rating separately (string not float)
    news_rating = news_analyst.get("rating", {})
    rating_val  = news_rating.get("value")
    if rating_val:
        resolved_rating = {
            "value":  rating_val,
            "firm":   news_rating.get("firm"),
            "action": news_rating.get("action"),
            "source": SOURCE_NEWS,
            "note":   None,
        }
    else:
        yf_rating = ratios.get("analyst_recommendation")
        if yf_rating:
            resolved_rating = {
                "value":  yf_rating,
                "firm":   None,
                "action": None,
                "source": SOURCE_YFINANCE,
                "note":   "Fallback — may not reflect latest analyst views",
            }
        else:
            resolved_rating = {
                "value": None, "firm": None,
                "action": None, "source": SOURCE_NONE, "note": None,
            }

    return {
        "rating":       resolved_rating,
        "target_price": _resolve("target_price", "analyst_target_price"),
        "target_mean":  _resolve("target_mean",  "analyst_target_price"),
        "target_low":   _resolve("target_low",   "analyst_target_low"),
        "target_high":  _resolve("target_high",  "analyst_target_high"),
        "all_ratings":  news_analyst.get("all_ratings", []),
    }


# ── SKILL-I19 & I20 (unchanged) ───────────────────────────────────────────────

def compute_insider_activity_signal(
    insider_disclosures: list[dict],
    days_lookback: int = 90,
) -> dict[str, Any]:
    """SKILL-I19: Compute Insider Activity Signal."""
    if not insider_disclosures:
        return {
            "net_insider_direction": "neutral",
            "insider_buy_value":     0,
            "insider_sell_value":    0,
            "insider_signal":        "amber",
            "note":                  "No insider disclosure data available.",
        }

    buy_value = sell_value = 0.0
    for disc in insider_disclosures:
        subject = disc.get("subject", "").lower()
        if "esop" in subject or "employee stock" in subject:
            continue
        qty   = _safe_float(disc.get("quantity", 0)) or 0
        price = _safe_float(disc.get("price",    0)) or 0
        value = qty * price
        if any(k in subject for k in ("buy", "acqui", "purchase")):
            buy_value  += value
        elif any(k in subject for k in ("sell", "disposal", "transfer")):
            sell_value += value

    if buy_value > sell_value * 1.2:
        direction, signal = "buying",  "green"
    elif sell_value > buy_value * 1.2:
        direction, signal = "selling", "red"
    else:
        direction, signal = "neutral", "amber"

    return {
        "net_insider_direction": direction,
        "insider_buy_value":     round(buy_value,  2),
        "insider_sell_value":    round(sell_value, 2),
        "insider_signal":        signal,
    }


def compute_institutional_ownership_change(
    fii_change_qoq: float | None,
    dii_change_qoq: float | None,
) -> dict[str, Any]:
    """SKILL-I20: Compute Institutional Ownership Change."""
    if fii_change_qoq is None and dii_change_qoq is None:
        return {
            "institutional_direction": "neutral",
            "institutional_signal":    "amber",
            "note": "QoQ institutional data unavailable via free sources.",
        }

    fii = fii_change_qoq or 0.0
    dii = dii_change_qoq or 0.0
    net = fii + dii

    if net >= 1.0:
        direction, signal = "accumulating", "green"
    elif net <= -1.0:
        direction, signal = "distributing",  "red"
    else:
        direction, signal = "stable",        "amber"

    return {
        "institutional_direction":  direction,
        "institutional_signal":     signal,
        "fii_change_qoq":           fii_change_qoq,
        "dii_change_qoq":           dii_change_qoq,
        "net_institutional_change": round(net, 4),
    }