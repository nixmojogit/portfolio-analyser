"""
price_module.py
Layer      : Data
Owns       : SKILL-D01, SKILL-D02, SKILL-D12
Description: Fetches historical OHLCV price data, real-time price snapshots,
             and benchmark/sector index data from Yahoo Finance (yfinance).
             All calls check cache via SKILL-D13 before external fetch.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any

import pandas as pd
import yfinance as yf

from src.layers.data.cache_manager import cache_read, cache_write
from src.layers.configuration.config_manager import get_skill_ttl
from src.utils.logger import get_logger

log = get_logger(__name__)

# Default Nifty sector index tickers on Yahoo Finance
DEFAULT_INDICES = [
    "^NSEI",        # Nifty 50
    "^BSESN",       # Sensex
    "^NSEBANK",     # Nifty Bank
    "^CNXIT",       # Nifty IT
    "^CNXPHARMA",   # Nifty Pharma
    "^CNXFMCG",     # Nifty FMCG
    "^CNXAUTO",     # Nifty Auto
    "^CNXENERGY",   # Nifty Energy
]


# ── Utilities ─────────────────────────────────────────────────────────────────

def build_ticker(symbol: str, exchange: str = "NS") -> str:
    """
    Append exchange suffix to a ticker symbol if not already present.
    Args:
        symbol   : base ticker e.g. 'RELIANCE' or 'RELIANCE.NS'
        exchange : 'NS' for NSE (default) or 'BO' for BSE
    Returns: suffixed ticker e.g. 'RELIANCE.NS'
    """
    symbol = symbol.strip().upper()
    if "." in symbol:
        return symbol
    return f"{symbol}.{exchange}"


def _period_to_label(period: str, interval: str) -> str:
    """Build a cache key label from period and interval strings."""
    return f"{period}_{interval}"


# ── SKILL-D01: Fetch Historical Price Data ────────────────────────────────────

def fetch_historical_price_data(
    ticker: str,
    period: str = "2y",
    interval: str = "1d",
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D01: Fetch Historical Price Data.
    Fetches OHLCV price history from Yahoo Finance for a given NSE/BSE ticker.
    Checks cache before external call. Returns stale cache on fetch failure.
    Args:
        ticker   : NSE/BSE ticker e.g. 'RELIANCE.NS'
        period   : yfinance period string e.g. '2y', '1y', '6mo'
        interval : yfinance interval string e.g. '1d', '1wk'
        config   : merged config dict (for cache TTL lookup)
    Returns: dict with keys:
        price_df        (pd.DataFrame: Date, Open, High, Low, Close, Volume)
        cache_timestamp (str: ISO datetime of last fetch)
        is_stale        (bool: True if serving from expired cache)
    """
    ticker = build_ticker(ticker)
    skill_id = "SKILL-D01"
    ttl = get_skill_ttl(config, skill_id) if config else 24
    cache_key = f"{ticker}_price_{_period_to_label(period, interval)}"

    # ── Cache check ───────────────────────────────────────────────────────────
    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        df = pd.DataFrame(cached["cached_data"]["rows"],
                          columns=cached["cached_data"]["columns"])
        df.index = pd.to_datetime(cached["cached_data"]["index"])
        df.index.name = "Date"
        return {
            "price_df": df,
            "cache_timestamp": cached["cached_data"]["fetched_at"],
            "is_stale": False,
        }

    # ── External fetch ────────────────────────────────────────────────────────
    log.info(f"[{skill_id}] Fetching price history: {ticker} ({period}, {interval})")
    try:
        raw = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )

        if raw.empty:
            log.warning(f"[{skill_id}] No data returned for {ticker}")
            return {"price_df": pd.DataFrame(), "cache_timestamp": None, "is_stale": False}

        # Flatten MultiIndex columns if present (yfinance ≥ 0.2.x)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        # Keep only standard OHLCV columns
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in raw.columns]
        df = raw[keep].copy()
        df.index.name = "Date"

        # ── Cache write ───────────────────────────────────────────────────────
        fetched_at = datetime.now().isoformat()
        cache_write(skill_id, cache_key, {
            "columns": df.columns.tolist(),
            "index": df.index.strftime("%Y-%m-%d").tolist(),
            "rows": df.values.tolist(),
            "fetched_at": fetched_at,
        })

        return {"price_df": df, "cache_timestamp": fetched_at, "is_stale": False}

    except Exception as e:
        log.error(f"[{skill_id}] Fetch failed for {ticker}: {e}")
        # Serve stale cache if available
        stale = cache_read(skill_id, cache_key, ttl_hours=999999)
        if stale["cache_hit"]:
            log.warning(f"[{skill_id}] Serving stale cache for {ticker}")
            df = pd.DataFrame(stale["cached_data"]["rows"],
                              columns=stale["cached_data"]["columns"])
            df.index = pd.to_datetime(stale["cached_data"]["index"])
            df.index.name = "Date"
            return {
                "price_df": df,
                "cache_timestamp": stale["cached_data"]["fetched_at"],
                "is_stale": True,
            }
        return {"price_df": pd.DataFrame(), "cache_timestamp": None, "is_stale": False}


# ── SKILL-D02: Fetch Real-Time Price Snapshot ─────────────────────────────────

def fetch_realtime_price_snapshot(
    ticker: str | list[str],
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D02: Fetch Real-Time Price Snapshot.
    Fetches current price, day change %, 52W high/low, avg volume,
    and market cap using yfinance fast_info.
    Args:
        ticker : single ticker string or list of tickers
        config : merged config dict
    Returns: dict (single ticker) or dict of dicts (list of tickers) with keys:
        current_price, day_change_pct, week_52_high, week_52_low,
        avg_volume, market_cap
    """
    skill_id = "SKILL-D02"
    ttl = get_skill_ttl(config, skill_id) if config else 1

    if isinstance(ticker, list):
        return {t: _fetch_single_snapshot(t, skill_id, ttl) for t in ticker}
    return _fetch_single_snapshot(ticker, skill_id, ttl)


def _fetch_single_snapshot(
    ticker: str,
    skill_id: str,
    ttl: float,
) -> dict[str, Any]:
    """Fetch and cache a real-time snapshot for a single ticker."""
    ticker = build_ticker(ticker)
    cache_key = f"{ticker}_snapshot"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        return cached["cached_data"]

    log.info(f"[{skill_id}] Fetching snapshot: {ticker}")
    try:
        info = yf.Ticker(ticker).fast_info
        result = {
            "current_price":  _safe_attr(info, "last_price"),
            "day_change_pct": _compute_day_change(info),
            "week_52_high":   _safe_attr(info, "year_high"),
            "week_52_low":    _safe_attr(info, "year_low"),
            "avg_volume":     _safe_attr(info, "three_month_average_volume"),
            "market_cap":     _safe_attr(info, "market_cap"),
        }
        cache_write(skill_id, cache_key, result)
        return result

    except Exception as e:
        log.error(f"[{skill_id}] Snapshot failed for {ticker}: {e}")
        return {
            "current_price": None, "day_change_pct": None,
            "week_52_high": None,  "week_52_low": None,
            "avg_volume": None,    "market_cap": None,
        }


def _safe_attr(obj: Any, attr: str) -> float | None:
    """Safely retrieve a float attribute, returning None on error."""
    try:
        val = getattr(obj, attr, None)
        return float(val) if val is not None else None
    except Exception:
        return None


def _compute_day_change(info: Any) -> float | None:
    """Compute day change % from last_price and previous_close."""
    try:
        last = getattr(info, "last_price", None)
        prev = getattr(info, "previous_close", None)
        if last and prev and prev != 0:
            return round(((last - prev) / prev) * 100, 4)
    except Exception:
        pass
    return None


# ── SKILL-D12: Fetch Index & Sector Index Data ────────────────────────────────

def fetch_index_and_sector_data(
    indices: list[str] | None = None,
    period: str = "1y",
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D12: Fetch Index & Sector Index Data.
    Fetches price history for Nifty 50 and all Nifty sector indices.
    Computes 1M, 3M, 6M, 1Y returns for each index.
    Args:
        indices : list of yfinance index tickers; uses DEFAULT_INDICES if None
        period  : lookback period string (default '1y')
        config  : merged config dict
    Returns: dict with keys:
        index_data     (dict of pd.DataFrames keyed by ticker)
        sector_returns (dict: ticker -> {1M, 3M, 6M, 1Y returns})
    """
    skill_id = "SKILL-D12"
    ttl = get_skill_ttl(config, skill_id) if config else 24
    indices = indices or DEFAULT_INDICES
    cache_key = f"indices_{period}_{'_'.join(sorted(indices))}"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        raw = cached["cached_data"]
        index_data = {}
        for tkr, payload in raw["index_data"].items():
            df = pd.DataFrame(payload["rows"], columns=payload["columns"])
            df.index = pd.to_datetime(payload["index"])
            df.index.name = "Date"
            index_data[tkr] = df
        return {"index_data": index_data, "sector_returns": raw["sector_returns"]}

    log.info(f"[{skill_id}] Fetching {len(indices)} indices ({period})")
    index_data: dict[str, pd.DataFrame] = {}
    sector_returns: dict[str, dict] = {}

    for idx_ticker in indices:
        try:
            raw = yf.download(
                idx_ticker, period=period, interval="1d",
                progress=False, auto_adjust=True,
            )
            if raw.empty:
                log.warning(f"[{skill_id}] No data for index {idx_ticker}")
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            df = raw[["Close"]].copy()
            df.index.name = "Date"
            index_data[idx_ticker] = df
            sector_returns[idx_ticker] = _compute_index_returns(df)

        except Exception as e:
            log.warning(f"[{skill_id}] Failed fetching {idx_ticker}: {e}")

    # Cache serialisable form
    cache_payload = {
        "index_data": {
            tkr: {
                "columns": df.columns.tolist(),
                "index": df.index.strftime("%Y-%m-%d").tolist(),
                "rows": df.values.tolist(),
            }
            for tkr, df in index_data.items()
        },
        "sector_returns": sector_returns,
    }
    cache_write(skill_id, cache_key, cache_payload)

    return {"index_data": index_data, "sector_returns": sector_returns}


def _compute_index_returns(df: pd.DataFrame) -> dict[str, float | None]:
    """
    Compute 1M, 3M, 6M, 1Y price returns for an index Close series.
    Returns dict with keys: return_1m, return_3m, return_6m, return_1y
    """
    def _ret(days: int) -> float | None:
        try:
            if len(df) < days:
                return None
            end = df["Close"].iloc[-1]
            start = df["Close"].iloc[-days]
            if start and start != 0:
                return round(((end - start) / start) * 100, 4)
        except Exception:
            pass
        return None

    return {
        "return_1m":  _ret(21),
        "return_3m":  _ret(63),
        "return_6m":  _ret(126),
        "return_1y":  _ret(252),
    }