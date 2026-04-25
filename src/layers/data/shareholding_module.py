"""
shareholding_module.py
Layer      : Data
Owns       : SKILL-D06, SKILL-D07, SKILL-D08
Description: Fetches shareholding pattern from yfinance (primary source),
             bulk/block deal direction from NSE (best effort),
             and pledge data (unavailable via free sources — returns None).
             SKILL-D06 NSE API is best-effort only — returns neutral on failure.
             SKILL-D08 pledge data has no reliable free source — always None.
"""

from __future__ import annotations
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests
import yfinance as yf

from src.layers.data.cache_manager import cache_read, cache_write
from src.layers.configuration.config_manager import get_skill_ttl
from src.utils.logger import get_logger

log = get_logger(__name__)

NSE_BASE = "https://www.nseindia.com/api"


# ── Utilities ─────────────────────────────────────────────────────────────────

def _get_nse_session_headers() -> dict:
    """Return browser-like headers required for NSE India API calls."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer":         "https://www.nseindia.com/",
    }


def _safe_float(val) -> float | None:
    """Safely convert a value to float."""
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _determine_institutional_direction(
    bulk_df: pd.DataFrame,
    block_df: pd.DataFrame,
) -> str:
    """
    Determine net institutional direction from bulk and block deal data.
    Returns 'buying', 'selling', or 'neutral'.
    """
    try:
        all_deals = pd.concat([bulk_df, block_df], ignore_index=True)
        if all_deals.empty:
            return "neutral"
        buy_qty  = all_deals[all_deals["type"].str.upper() == "BUY"]["quantity"].sum()
        sell_qty = all_deals[all_deals["type"].str.upper() == "SELL"]["quantity"].sum()
        if buy_qty > sell_qty * 1.2:
            return "buying"
        if sell_qty > buy_qty * 1.2:
            return "selling"
        return "neutral"
    except Exception:
        return "neutral"


# ── SKILL-D06: Fetch NSE Bulk & Block Deals (best effort) ────────────────────

def fetch_bulk_block_deals(
    ticker: str,
    days_lookback: int = 30,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D06: Fetch NSE Bulk & Block Deals.
    Best-effort fetch from NSE India. Returns neutral direction on failure.
    NSE unofficial API is unstable — failure is handled gracefully.
    Args:
        ticker        : NSE ticker e.g. 'RELIANCE' or 'RELIANCE.NS'
        days_lookback : number of days to look back (default 30)
        config        : merged config dict
    Returns: dict with bulk_deals, block_deals DataFrames and direction string
    """
    skill_id  = "SKILL-D06"
    base      = ticker.split(".")[0].upper()
    ttl       = get_skill_ttl(config, skill_id) if config else 24
    cache_key = f"{base}_bulk_block_{days_lookback}d"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        data = cached["cached_data"]
        return {
            "bulk_deals":  pd.DataFrame(data.get("bulk_deals", [])),
            "block_deals": pd.DataFrame(data.get("block_deals", [])),
            "net_institutional_direction": data.get(
                "net_institutional_direction", "neutral"
            ),
        }

    log.info(f"[{skill_id}] Fetching bulk/block deals (best effort): {base}")
    bulk_df   = _fetch_nse_deals(base, "bulk-deals",  days_lookback)
    block_df  = _fetch_nse_deals(base, "block-deals", days_lookback)
    direction = _determine_institutional_direction(bulk_df, block_df)

    result = {
        "bulk_deals":  bulk_df.to_dict("records"),
        "block_deals": block_df.to_dict("records"),
        "net_institutional_direction": direction,
    }
    cache_write(skill_id, cache_key, result)

    return {
        "bulk_deals":  bulk_df,
        "block_deals": block_df,
        "net_institutional_direction": direction,
    }


def _fetch_nse_deals(symbol: str, deal_type: str, days_lookback: int) -> pd.DataFrame:
    """Fetch bulk or block deal data from NSE. Returns empty DataFrame on failure."""
    try:
        session = requests.Session()
        session.get(
            "https://www.nseindia.com",
            headers=_get_nse_session_headers(),
            timeout=10,
        )
        time.sleep(1)

        from_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%d-%m-%Y")
        to_date   = datetime.now().strftime("%d-%m-%Y")
        url = (
            f"{NSE_BASE}/{deal_type}?"
            f"symbol={symbol}&series=EQ"
            f"&dateRange=custom&fromDate={from_date}&toDate={to_date}"
        )
        resp = session.get(url, headers=_get_nse_session_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()

        records = data.get("data", [])
        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        rename_map = {
            "symbol": "ticker", "clientName": "client",
            "buySell": "type",  "quantityTraded": "quantity",
            "tradePrice": "price",
        }
        df = df.rename(
            columns={k: v for k, v in rename_map.items() if k in df.columns}
        )
        return df

    except Exception as e:
        log.debug(f"[SKILL-D06] {deal_type} unavailable for {symbol}: {e}")
        return pd.DataFrame()


# ── SKILL-D07: Fetch Shareholding Pattern (yfinance primary) ─────────────────

def fetch_shareholding_pattern(
    ticker: str,
    quarters: int = 4,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D07: Fetch Shareholding Pattern.
    Uses yfinance as primary source via heldPercentInsiders and
    heldPercentInstitutions from the info dict.
    For Indian stocks, insiders ≈ promoters.
    Args:
        ticker   : company ticker e.g. 'RELIANCE' or 'RELIANCE.NS'
        quarters : informational only — history not available via yfinance
        config   : merged config dict
    Returns: dict with current holdings % and data source note
    """
    from src.layers.data.price_module import build_ticker
    skill_id  = "SKILL-D07"
    full      = build_ticker(ticker)
    base      = full.split(".")[0].upper()
    ttl       = get_skill_ttl(config, skill_id) if config else 720
    cache_key = f"{base}_shareholding_yf"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        data = cached["cached_data"]
        return {
            **data,
            "shareholding_history": pd.DataFrame(
                data.get("shareholding_history", [])
            ),
        }

    log.info(f"[{skill_id}] Fetching shareholding via yfinance: {full}")
    try:
        info = yf.Ticker(full).info

        # yfinance returns decimals (0–1) — convert to %
        insider_pct = _safe_float(info.get("heldPercentInsiders"))
        inst_pct    = _safe_float(info.get("heldPercentInstitutions"))

        if insider_pct is not None:
            insider_pct = round(insider_pct * 100, 2)
        if inst_pct is not None:
            inst_pct = round(inst_pct * 100, 2)

        public_pct = None
        if insider_pct is not None and inst_pct is not None:
            public_pct = round(max(0, 100 - insider_pct - inst_pct), 2)

        result = {
            "promoter_holding_pct": insider_pct,
            "fii_holding_pct":      inst_pct,
            "dii_holding_pct":      None,
            "public_holding_pct":   public_pct,
            "promoter_change_qoq":  None,
            "fii_change_qoq":       None,
            "dii_change_qoq":       None,
            "shareholding_history": [],
            "data_source":          "yfinance",
            "note": (
                "Promoter % approximated from insiders held. "
                "DII and QoQ changes unavailable via free sources."
            ),
        }

        cache_write(skill_id, cache_key, result)
        return {
            **result,
            "shareholding_history": pd.DataFrame(result["shareholding_history"]),
        }

    except Exception as e:
        log.warning(f"[{skill_id}] yfinance fetch failed for {full}: {e}")
        return _empty_shareholding()


def _empty_shareholding() -> dict[str, Any]:
    """Return an empty shareholding result dict."""
    return {
        "promoter_holding_pct": None, "fii_holding_pct": None,
        "dii_holding_pct": None,      "public_holding_pct": None,
        "promoter_change_qoq": None,  "fii_change_qoq": None,
        "dii_change_qoq": None,
        "shareholding_history": pd.DataFrame(),
        "data_source": "unavailable",
        "note": "Shareholding data unavailable.",
    }


# ── SKILL-D08: Fetch Promoter Pledge Data ────────────────────────────────────

def fetch_promoter_pledge_data(
    ticker: str,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D08: Fetch Promoter Pledge Data.
    Promoter pledge data has no reliable free API source.
    Returns None for all fields — excluded from scoring gracefully.
    Retained as a skill stub for future integration if a paid source
    becomes available (e.g. BSE data feed).
    Args:
        ticker : company ticker
        config : merged config dict
    Returns: dict with pledge_pct=None, pledge_change_qoq=None,
             pledge_trend='unavailable'
    """
    base = ticker.split(".")[0].upper()
    log.debug(f"[SKILL-D08] Pledge data unavailable via free sources for {base}")
    return {
        "pledge_pct":        None,
        "pledge_change_qoq": None,
        "pledge_trend":      "unavailable",
        "note": (
            "Promoter pledge data has no reliable free API source. "
            "Excluded from scoring. Integrate a paid BSE data feed to enable."
        ),
    }