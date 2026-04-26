"""
risk_module.py
Layer      : Intelligence
Owns       : SKILL-I31
Description: Computes ATR-based stop-loss for each portfolio holding.
             ATR (Average True Range) adapts the stop-loss to each
             stock's actual volatility rather than a fixed percentage.
             Stop-Loss Price = Buy Price - (ATR Multiplier x 14-day ATR)
"""

from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd
from src.utils.logger import get_logger

log = get_logger(__name__)


def compute_atr(price_df: pd.DataFrame, period: int = 14) -> float | None:
    """
    Compute Average True Range using Wilder smoothing.
    True Range = MAX(High-Low, |High-PrevClose|, |Low-PrevClose|)
    """
    required = ["High", "Low", "Close"]
    if price_df is None or price_df.empty:
        return None
    if not all(c in price_df.columns for c in required):
        return None
    df = price_df[required].dropna()
    if len(df) < period + 1:
        return None
    high       = df["High"]
    low        = df["Low"]
    close      = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    val = atr.dropna().iloc[-1] if len(atr.dropna()) > 0 else None
    try:
        return round(float(val), 4) if val is not None else None
    except (TypeError, ValueError):
        return None


def compute_stop_loss_proximity(
    current_price: float,
    buy_price: float,
    price_df: pd.DataFrame | None = None,
    stop_loss_pct: float = 12.0,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I31: Compute ATR-based Stop-Loss Proximity.
    Primary: ATR stop = Buy Price - (ATR Multiplier x ATR)
    Fallback: fixed percentage if price data insufficient.
    ATR stop must be between 3% and 30% below buy price to be valid.
    """
    try:
        cp = float(current_price)
        bp = float(buy_price)
    except (TypeError, ValueError) as e:
        log.warning(f"[SKILL-I31] Invalid inputs: {e}")
        return _empty_result()

    if bp <= 0:
        return _empty_result()

    sys_cfg    = (config or {}).get("system", {})
    atr_period = int(sys_cfg.get("atr_period", 14))
    atr_mult   = float(sys_cfg.get("atr_multiplier", 2.0))
    warning_pct= float(sys_cfg.get("stop_loss_warning_proximity_pct", 3))

    # ATR-based stop
    atr_value   = None
    stop_method = "fixed_pct"
    stop_price  = round(bp * (1 - stop_loss_pct / 100), 4)

    if price_df is not None and not price_df.empty:
        atr_value = compute_atr(price_df, period=atr_period)
        if atr_value is not None and atr_value > 0:
            atr_stop = bp - (atr_mult * atr_value)
            atr_pct  = ((bp - atr_stop) / bp) * 100
            if 3.0 <= atr_pct <= 30.0:
                stop_price  = round(atr_stop, 4)
                stop_method = "atr"
                log.debug(
                    f"[SKILL-I31] ATR stop: buy={bp:.2f} "
                    f"atr={atr_value:.2f} stop={stop_price:.2f} ({atr_pct:.1f}%)"
                )

    equivalent_stop_pct  = round(((bp - stop_price) / bp) * 100, 4)
    current_drawdown_pct = round(((cp - bp) / bp) * 100, 4)
    proximity_to_stop    = round(((cp - stop_price) / stop_price) * 100, 4)

    if cp <= stop_price:
        signal = "breached"
    elif proximity_to_stop <= warning_pct:
        signal = "warning"
    else:
        signal = "safe"

    return {
        "stop_loss_price":       stop_price,
        "stop_loss_method":      stop_method,
        "atr_value":             atr_value,
        "atr_multiplier":        atr_mult,
        "equivalent_stop_pct":  equivalent_stop_pct,
        "current_drawdown_pct": current_drawdown_pct,
        "proximity_to_stop_pct": proximity_to_stop,
        "stop_loss_signal":      signal,
    }


def _empty_result() -> dict[str, Any]:
    return {
        "stop_loss_price":       None,
        "stop_loss_method":      "fixed_pct",
        "atr_value":             None,
        "atr_multiplier":        2.0,
        "equivalent_stop_pct":  None,
        "current_drawdown_pct": None,
        "proximity_to_stop_pct": None,
        "stop_loss_signal":      "safe",
    }
