"""
technical_module.py
Layer      : Intelligence
Owns       : SKILL-I01, SKILL-I02, SKILL-I03, SKILL-I04, SKILL-I05, SKILL-I06
Description: Computes all technical indicators from historical price data.
             Implemented using pandas and numpy — no external TA library.
             Pure computation: no data fetching, no UI logic.
"""

from __future__ import annotations
from typing import Any

import numpy as np
import pandas as pd

from src.utils.logger import get_logger

log = get_logger(__name__)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _compute_ema(series: pd.Series, span: int) -> pd.Series:
    """
    Compute Exponential Moving Average for a given span.
    Args:
        series : pandas price Series
        span   : EMA span (e.g. 12, 26, 9)
    Returns: pd.Series of EMA values
    """
    return series.ewm(span=span, adjust=False).mean()


def _safe_float(val) -> float | None:
    """Safely convert a value to Python float."""
    try:
        f = float(val)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _last(series: pd.Series) -> float | None:
    """Return last non-null value of a series as float."""
    try:
        return _safe_float(series.dropna().iloc[-1])
    except (IndexError, AttributeError):
        return None


# ── SKILL-I01: Compute Moving Averages ───────────────────────────────────────

def compute_moving_averages(price_df: pd.DataFrame) -> dict[str, Any]:
    """
    SKILL-I01: Compute Moving Averages (50D / 200D SMA).
    Computes 50-day and 200-day Simple Moving Averages from Close prices.
    Identifies Golden Cross and Death Cross within last 10 trading days.
    Args:
        price_df: DataFrame with at least 'Close' column (from SKILL-D01)
    Returns: dict with keys:
        sma_50, sma_200, price_vs_sma50_pct, price_vs_sma200_pct,
        trend_signal ('bullish'|'neutral'|'bearish'),
        golden_cross (bool), death_cross (bool)
    """
    empty = {
        "sma_50": None, "sma_200": None,
        "price_vs_sma50_pct": None, "price_vs_sma200_pct": None,
        "trend_signal": "neutral", "golden_cross": False, "death_cross": False,
    }

    if price_df is None or price_df.empty or "Close" not in price_df.columns:
        log.warning("[SKILL-I01] Empty or invalid price_df")
        return empty

    close = price_df["Close"].dropna()
    if len(close) < 50:
        log.warning(f"[SKILL-I01] Insufficient data: {len(close)} rows (need 50+)")
        return empty

    sma50  = close.rolling(window=50).mean()
    sma200 = close.rolling(window=200).mean() if len(close) >= 200 else None

    current_price = _last(close)
    sma50_val     = _last(sma50)
    sma200_val    = _last(sma200) if sma200 is not None else None

    # Price vs MA %
    pct_vs_50  = None
    pct_vs_200 = None
    if current_price and sma50_val:
        pct_vs_50  = round(((current_price - sma50_val)  / sma50_val)  * 100, 4)
    if current_price and sma200_val:
        pct_vs_200 = round(((current_price - sma200_val) / sma200_val) * 100, 4)

    # Trend signal — based on 200D MA primarily, fall back to 50D
    if pct_vs_200 is not None:
        trend = "bullish" if pct_vs_200 > 0 else "bearish"
    elif pct_vs_50 is not None:
        trend = "bullish" if pct_vs_50 > 3 else ("bearish" if pct_vs_50 < -3 else "neutral")
    else:
        trend = "neutral"

    # Golden / Death Cross — 50D crosses 200D within last 10 days
    golden = death = False
    if sma200 is not None and len(sma50.dropna()) >= 10 and len(sma200.dropna()) >= 10:
        window = 10
        s50_w  = sma50.iloc[-window:]
        s200_w = sma200.iloc[-window:]
        diff   = s50_w - s200_w
        signs  = np.sign(diff.dropna())
        if len(signs) >= 2:
            golden = bool(signs.iloc[-1] > 0 and signs.iloc[0] <= 0)
            death  = bool(signs.iloc[-1] < 0 and signs.iloc[0] >= 0)

    return {
        "sma_50":              sma50_val,
        "sma_200":             sma200_val,
        "price_vs_sma50_pct":  pct_vs_50,
        "price_vs_sma200_pct": pct_vs_200,
        "trend_signal":        trend,
        "golden_cross":        golden,
        "death_cross":         death,
    }


# ── SKILL-I02: Compute RSI ────────────────────────────────────────────────────

def compute_rsi(price_df: pd.DataFrame, period: int = 14) -> dict[str, Any]:
    """
    SKILL-I02: Compute RSI (14-day).
    Uses Wilder smoothing method (exponential moving average of gains/losses).
    Args:
        price_df : DataFrame with 'Close' column (from SKILL-D01)
        period   : RSI period (default 14)
    Returns: dict with keys:
        rsi_value (float 0-100),
        rsi_signal ('oversold'|'neutral'|'overbought'),
        rsi_trend  ('rising'|'falling'|'flat')
    """
    empty = {"rsi_value": None, "rsi_signal": "neutral", "rsi_trend": "flat"}

    if price_df is None or price_df.empty or "Close" not in price_df.columns:
        return empty

    close = price_df["Close"].dropna()
    if len(close) < period + 1:
        log.warning(f"[SKILL-I02] Insufficient data for RSI: {len(close)} rows")
        return empty

    delta  = close.diff()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)

    # Wilder smoothing = EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    rsi_val = _last(rsi)
    if rsi_val is None:
        return empty

    # Signal
    if rsi_val < 30:
        signal = "oversold"
    elif rsi_val > 70:
        signal = "overbought"
    else:
        signal = "neutral"

    # Trend — compare last value to 5 days ago
    rsi_trend = "flat"
    try:
        rsi_clean = rsi.dropna()
        if len(rsi_clean) >= 5:
            diff = rsi_clean.iloc[-1] - rsi_clean.iloc[-5]
            if diff > 2:
                rsi_trend = "rising"
            elif diff < -2:
                rsi_trend = "falling"
    except Exception:
        pass

    return {
        "rsi_value":  round(rsi_val, 2),
        "rsi_signal": signal,
        "rsi_trend":  rsi_trend,
    }


# ── SKILL-I03: Compute MACD ───────────────────────────────────────────────────

def compute_macd(price_df: pd.DataFrame) -> dict[str, Any]:
    """
    SKILL-I03: Compute MACD & Signal Line.
    MACD = 12-day EMA - 26-day EMA
    Signal = 9-day EMA of MACD
    Histogram = MACD - Signal
    Detects bullish/bearish crossovers within last 5 trading days.
    Args:
        price_df: DataFrame with 'Close' column (from SKILL-D01)
    Returns: dict with keys:
        macd_line, signal_line, histogram,
        macd_signal ('bullish_crossover'|'bearish_crossover'|'neutral'),
        crossover_date (str | None)
    """
    empty = {
        "macd_line": None, "signal_line": None, "histogram": None,
        "macd_signal": "neutral", "crossover_date": None,
    }

    if price_df is None or price_df.empty or "Close" not in price_df.columns:
        return empty

    close = price_df["Close"].dropna()
    if len(close) < 26:
        log.warning(f"[SKILL-I03] Insufficient data for MACD: {len(close)} rows")
        return empty

    ema12  = _compute_ema(close, 12)
    ema26  = _compute_ema(close, 26)
    macd   = ema12 - ema26
    signal = _compute_ema(macd, 9)
    hist   = macd - signal

    macd_val   = _last(macd)
    signal_val = _last(signal)
    hist_val   = _last(hist)

    # Crossover detection — last 5 days
    macd_signal_str  = "neutral"
    crossover_date   = None
    try:
        macd_c   = macd.dropna()
        signal_c = signal.dropna()
        common   = macd_c.index.intersection(signal_c.index)
        if len(common) >= 5:
            m  = macd_c.loc[common].iloc[-5:]
            s  = signal_c.loc[common].iloc[-5:]
            diff  = m - s
            signs = np.sign(diff)
            for i in range(1, len(signs)):
                if signs.iloc[i] > 0 and signs.iloc[i - 1] <= 0:
                    macd_signal_str = "bullish_crossover"
                    crossover_date  = str(signs.index[i].date())
                elif signs.iloc[i] < 0 and signs.iloc[i - 1] >= 0:
                    macd_signal_str = "bearish_crossover"
                    crossover_date  = str(signs.index[i].date())
    except Exception:
        pass

    return {
        "macd_line":      round(macd_val, 4)   if macd_val   is not None else None,
        "signal_line":    round(signal_val, 4) if signal_val is not None else None,
        "histogram":      round(hist_val, 4)   if hist_val   is not None else None,
        "macd_signal":    macd_signal_str,
        "crossover_date": crossover_date,
    }


# ── SKILL-I04: Compute Beta ───────────────────────────────────────────────────

def compute_beta(
    price_df: pd.DataFrame,
    index_df: pd.DataFrame,
) -> dict[str, Any]:
    """
    SKILL-I04: Compute Beta relative to Nifty 50.
    Formula: Cov(stock_returns, index_returns) / Var(index_returns)
    Uses up to 252 trading days (1 year) of daily returns.
    Args:
        price_df : stock OHLCV DataFrame (from SKILL-D01)
        index_df : Nifty 50 DataFrame (from SKILL-D12)
    Returns: dict with keys:
        beta (float),
        beta_signal ('low'|'moderate'|'high')
    """
    empty = {"beta": None, "beta_signal": "moderate"}

    try:
        stock_close = price_df["Close"].dropna()
        index_close = index_df["Close"].dropna()

        # Align on common dates
        common = stock_close.index.intersection(index_close.index)
        if len(common) < 30:
            log.warning(f"[SKILL-I04] Insufficient aligned data: {len(common)} days")
            return empty

        # Use last 252 days
        common = common[-252:]
        s_ret  = stock_close.loc[common].pct_change().dropna()
        i_ret  = index_close.loc[common].pct_change().dropna()

        # Align after pct_change
        common2 = s_ret.index.intersection(i_ret.index)
        s_ret   = s_ret.loc[common2].values
        i_ret   = i_ret.loc[common2].values

        if len(s_ret) < 20:
            return empty

        cov    = np.cov(s_ret, i_ret)
        beta   = cov[0, 1] / cov[1, 1]
        beta   = round(float(beta), 4)

        if beta < 0.8:
            signal = "low"
        elif beta <= 1.2:
            signal = "moderate"
        else:
            signal = "high"

        return {"beta": beta, "beta_signal": signal}

    except Exception as e:
        log.warning(f"[SKILL-I04] Beta computation failed: {e}")
        return empty


# ── SKILL-I05: Compute 52-Week Momentum Score ─────────────────────────────────

def compute_52w_momentum(
    price_df: pd.DataFrame,
    current_price: float,
) -> dict[str, Any]:
    """
    SKILL-I05: Compute 52-Week Momentum Score (0-100).
    Combines 52W high/low proximity and 1-year price return.
    Args:
        price_df      : OHLCV DataFrame (from SKILL-D01)
        current_price : current market price (from SKILL-D02)
    Returns: dict with keys:
        week_52_high, week_52_low, pct_from_52w_high,
        pct_from_52w_low, return_1y, momentum_score (0-100)
    """
    empty = {
        "week_52_high": None, "week_52_low": None,
        "pct_from_52w_high": None, "pct_from_52w_low": None,
        "return_1y": None, "momentum_score": 50,
    }

    if price_df is None or price_df.empty or "Close" not in price_df.columns:
        return empty

    close = price_df["Close"].dropna()
    if len(close) < 50:
        return empty

    # Use last 252 trading days for 52W
    window = close.iloc[-252:] if len(close) >= 252 else close

    high_52w = float(window.max())
    low_52w  = float(window.min())

    pct_from_high = round(((current_price - high_52w) / high_52w) * 100, 4)
    pct_from_low  = round(((current_price - low_52w)  / low_52w)  * 100, 4)

    # 1-year return
    return_1y = None
    if len(close) >= 252:
        start = float(close.iloc[-252])
        if start > 0:
            return_1y = round(((current_price - start) / start) * 100, 4)

    # Momentum score (0-100)
    # Proximity to 52W high: within 10% = strong (score 70-100)
    high_score = max(0, min(100, 100 + pct_from_high * 3))

    # 1Y return contribution
    ret_score = 50.0
    if return_1y is not None:
        ret_score = min(100, max(0, 50 + return_1y * 0.5))

    momentum_score = round(high_score * 0.6 + ret_score * 0.4, 2)

    return {
        "week_52_high":      high_52w,
        "week_52_low":       low_52w,
        "pct_from_52w_high": pct_from_high,
        "pct_from_52w_low":  pct_from_low,
        "return_1y":         return_1y,
        "momentum_score":    momentum_score,
    }


# ── SKILL-I06: Compute Volume Signal ─────────────────────────────────────────

def compute_volume_signal(price_df: pd.DataFrame) -> dict[str, Any]:
    """
    SKILL-I06: Compute Volume Signal.
    Compares current volume to 30-day average volume to determine
    whether price moves are supported by conviction.
    Args:
        price_df: DataFrame with 'Close' and 'Volume' columns (from SKILL-D01)
    Returns: dict with keys:
        avg_volume_30d, current_volume, volume_ratio,
        volume_signal ('high_conviction'|'normal'|'low_conviction'),
        volume_price_signal ('confirmed_breakout'|'confirmed_breakdown'
                            |'unconfirmed'|'neutral')
    """
    empty = {
        "avg_volume_30d": None, "current_volume": None,
        "volume_ratio": None,   "volume_signal": "normal",
        "volume_price_signal": "neutral",
    }

    if price_df is None or price_df.empty:
        return empty
    if "Volume" not in price_df.columns or "Close" not in price_df.columns:
        return empty

    df = price_df[["Close", "Volume"]].dropna()
    if len(df) < 31:
        return empty

    current_vol  = float(df["Volume"].iloc[-1])
    avg_vol_30d  = float(df["Volume"].iloc[-31:-1].mean())

    if avg_vol_30d == 0:
        return empty

    ratio = round(current_vol / avg_vol_30d, 4)

    # Volume signal
    if ratio >= 1.5:
        vol_signal = "high_conviction"
    elif ratio <= 0.5:
        vol_signal = "low_conviction"
    else:
        vol_signal = "normal"

    # Price direction today
    price_change = float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-2])
    rising = price_change > 0

    # Volume-price confirmation
    if ratio >= 1.5 and rising:
        vp_signal = "confirmed_breakout"
    elif ratio >= 1.5 and not rising:
        vp_signal = "confirmed_breakdown"
    elif ratio < 1.5 and rising:
        vp_signal = "unconfirmed"
    else:
        vp_signal = "neutral"

    return {
        "avg_volume_30d":     round(avg_vol_30d, 0),
        "current_volume":     current_vol,
        "volume_ratio":       ratio,
        "volume_signal":      vol_signal,
        "volume_price_signal": vp_signal,
    }