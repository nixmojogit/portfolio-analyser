"""
macro_module.py
Layer      : Data
Owns       : SKILL-D11
Description: Fetches Indian macroeconomic indicators used as contextual
             inputs for portfolio-level decisions. Sources include
             yfinance (VIX, FX), World Bank open API (GDP, CPI),
             and RBI website scraping (repo rate).
             Weekly cache TTL is sufficient — macro data changes slowly.
"""

from __future__ import annotations
from typing import Any

import requests
import yfinance as yf

from src.layers.data.cache_manager import cache_read, cache_write
from src.layers.configuration.config_manager import get_skill_ttl
from src.utils.logger import get_logger

log = get_logger(__name__)

WORLD_BANK_BASE = "https://api.worldbank.org/v2/country/IN/indicator"
WORLD_BANK_PARAMS = "?format=json&mrv=1&per_page=1"

# World Bank indicator codes
WB_GDP_GROWTH = "NY.GDP.MKTP.KD.ZG"   # GDP growth rate (annual %)
WB_CPI        = "FP.CPI.TOTL.ZG"      # CPI inflation (annual %)

RBI_URL = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── SKILL-D11: Fetch Macro Indicators ────────────────────────────────────────

def fetch_macro_indicators(config: dict | None = None) -> dict[str, Any]:
    """
    SKILL-D11: Fetch Macro Indicators.
    Retrieves key Indian macroeconomic data in a single call.
    Weekly cache TTL — macro data changes slowly.
    Repo rate falls back to system.yaml risk_free_rate if RBI scrape fails.
    Args:
        config: merged config dict
    Returns: dict with keys:
        repo_rate     (float | None: RBI repo rate %)
        cpi_inflation (float | None: latest CPI %)
        gdp_growth    (float | None: latest GDP growth %)
        india_vix     (float | None: India VIX)
        usd_inr       (float | None: USD/INR rate)
        nifty_pe      (float | None: Nifty 50 P/E)
        data_notes    (dict: source and availability notes per indicator)
    """
    skill_id  = "SKILL-D11"
    ttl       = get_skill_ttl(config, skill_id) if config else 168
    cache_key = "macro_india_all"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        return cached["cached_data"]

    log.info(f"[{skill_id}] Fetching macro indicators ...")

    repo_rate = _fetch_rbi_repo_rate()
    # Fall back to config risk_free_rate if RBI scrape fails
    if repo_rate is None and config:
        rfr = config.get("system", {}).get("risk_free_rate")
        if rfr:
            repo_rate = round(rfr * 100, 2)
            log.info(f"[{skill_id}] Repo rate: using config fallback {repo_rate}%")

    india_vix     = _fetch_india_vix()
    usd_inr       = _fetch_usd_inr()
    gdp_growth    = _fetch_world_bank_indicator(WB_GDP_GROWTH)
    cpi_inflation = _fetch_world_bank_indicator(WB_CPI)
    nifty_pe      = _fetch_nifty_pe()

    result = {
        "repo_rate":     repo_rate,
        "cpi_inflation": cpi_inflation,
        "gdp_growth":    gdp_growth,
        "india_vix":     india_vix,
        "usd_inr":       usd_inr,
        "nifty_pe":      nifty_pe,
        "data_notes": {
            "repo_rate":     "RBI scrape with config fallback (risk_free_rate)",
            "cpi_inflation": "World Bank open API — annual figure, 1yr lag typical",
            "gdp_growth":    "World Bank open API — annual figure, 1yr lag typical",
            "india_vix":     "yfinance ^INDIAVIX",
            "usd_inr":       "yfinance USDINR=X",
            "nifty_pe":      "yfinance ^NSEI",
        },
    }

    log.info(
        f"[{skill_id}] Macro: repo={repo_rate}% | VIX={india_vix} | "
        f"USD/INR={usd_inr} | GDP={gdp_growth}% | CPI={cpi_inflation}%"
    )
    cache_write(skill_id, cache_key, result)
    return result


# ── Data Fetchers ─────────────────────────────────────────────────────────────

def _fetch_rbi_repo_rate() -> float | None:
    """
    Fetch current RBI repo rate from the RBI website.
    Parses the policy rates page for the current repo rate.
    Returns repo rate as float (e.g. 6.5) or None on failure.
    """
    try:
        url  = "https://www.rbi.org.in/Scripts/BS_ViewBulletin.aspx"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        # Look for repo rate pattern in page text
        text = resp.text.lower()
        # Search for pattern near "repo rate" text
        idx = text.find("repo rate")
        if idx == -1:
            idx = text.find("policy repo rate")

        if idx != -1:
            # Extract surrounding text and look for a percentage
            snippet = resp.text[max(0, idx - 50): idx + 200]
            import re
            matches = re.findall(r"\b(\d+\.\d+|\d+)\s*%?", snippet)
            for m in matches:
                val = float(m)
                if 4.0 <= val <= 10.0:   # reasonable repo rate range
                    log.debug(f"RBI repo rate found: {val}%")
                    return val

        log.debug("RBI repo rate not found in page — using config default")
        return None

    except Exception as e:
        log.debug(f"RBI repo rate fetch failed: {e}")
        return None


def _fetch_india_vix() -> float | None:
    """
    Fetch India VIX from Yahoo Finance (ticker: ^INDIAVIX).
    Returns current VIX value as float or None on failure.
    """
    try:
        info = yf.Ticker("^INDIAVIX").fast_info
        val  = getattr(info, "last_price", None)
        return round(float(val), 2) if val else None
    except Exception as e:
        log.debug(f"India VIX fetch failed: {e}")
        return None


def _fetch_usd_inr() -> float | None:
    """
    Fetch current USD/INR exchange rate from Yahoo Finance.
    Returns rate as float or None on failure.
    """
    try:
        info = yf.Ticker("USDINR=X").fast_info
        val  = getattr(info, "last_price", None)
        return round(float(val), 4) if val else None
    except Exception as e:
        log.debug(f"USD/INR fetch failed: {e}")
        return None


def _fetch_world_bank_indicator(indicator_code: str) -> float | None:
    """
    Fetch a macroeconomic indicator from the World Bank open API.
    No API key required. Returns latest available value as float.
    Note: World Bank data typically has a 1-year lag.
    Args:
        indicator_code: World Bank code e.g. 'NY.GDP.MKTP.KD.ZG'
    Returns: latest value as float or None on failure
    """
    try:
        url  = f"{WORLD_BANK_BASE}/{indicator_code}{WORLD_BANK_PARAMS}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # World Bank response: [metadata, [data_records]]
        if isinstance(data, list) and len(data) > 1:
            records = data[1]
            if records:
                val = records[0].get("value")
                if val is not None:
                    return round(float(val), 4)

        return None

    except Exception as e:
        log.debug(f"World Bank fetch failed ({indicator_code}): {e}")
        return None


def _fetch_nifty_pe() -> float | None:
    """
    Nifty 50 P/E ratio is not available via yfinance for index tickers.
    NSE India's official P/E data requires scraping an unstable endpoint.
    Returns None — excluded from scoring gracefully.
    Future: integrate NSE India's historical PE/PB data API when stable.
    """
    log.debug("Nifty P/E unavailable via free sources — returning None")
    return None