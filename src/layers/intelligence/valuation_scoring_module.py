"""
valuation_scoring_module.py
Layer      : Intelligence
Owns       : SKILL-I10, SKILL-I11, SKILL-I12
Description: Computes valuation metric scores — PEG ratio, P/E vs sector
             median, and EV/EBITDA. Returns signals used by the Valuation
             Scorecard aggregator (SKILL-I23).
"""

from __future__ import annotations
from typing import Any

import numpy as np
import pandas as pd

from src.utils.logger import get_logger

log = get_logger(__name__)


def _safe_float(val) -> float | None:
    """Safely convert a value to float."""
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except (TypeError, ValueError):
        return None


# ── SKILL-I10: Compute PEG Ratio ─────────────────────────────────────────────

def compute_peg_ratio(
    pe_ratio: float | None,
    eps_growth_rate: float | None,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I10: Compute PEG Ratio.
    PEG = P/E divided by earnings growth rate (%).
    Returns N/A if growth is zero/negative or P/E is unavailable.
    Args:
        pe_ratio       : trailing P/E ratio (from SKILL-D04)
        eps_growth_rate: EPS or revenue growth rate % (from SKILL-I07)
        config         : merged config dict
    Returns: dict with peg_ratio, peg_signal
    """
    pe  = _safe_float(pe_ratio)
    grw = _safe_float(eps_growth_rate)

    if pe is None or grw is None or grw <= 0:
        log.debug(f"[SKILL-I10] PEG N/A — PE={pe}, growth={grw}")
        return {"peg_ratio": None, "peg_signal": "na"}

    peg = round(pe / grw, 4)

    t = (config or {}).get("thresholds", {}).get("peg_ratio", {})
    green_below = t.get("green_below", 1.0)
    amber_below = t.get("amber_below", 1.5)

    if peg <= green_below:
        signal = "undervalued"
    elif peg <= amber_below:
        signal = "fair"
    else:
        signal = "overvalued"

    log.debug(f"[SKILL-I10] PEG={peg} → {signal}")
    return {"peg_ratio": peg, "peg_signal": signal}


# ── SKILL-I11: Compute P/E vs Sector Median ──────────────────────────────────

def compute_pe_vs_sector(
    pe_ratio: float | None,
    peer_comparison: pd.DataFrame | None,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I11: Compute P/E vs Sector Median.
    Computes sector median P/E from peer comparison data.
    Requires at least 3 peers for a valid computation.
    Args:
        pe_ratio        : stock trailing P/E (from SKILL-D04)
        peer_comparison : peer group DataFrame (from SKILL-D05)
        config          : merged config dict
    Returns: dict with sector_median_pe, pe_premium_discount_pct,
             pe_vs_sector_signal
    """
    pe = _safe_float(pe_ratio)

    if pe is None:
        return {
            "sector_median_pe": None,
            "pe_premium_discount_pct": None,
            "pe_vs_sector_signal": "na",
        }

    # Extract peer P/E values from peer_comparison DataFrame
    sector_median_pe = None
    if peer_comparison is not None and not peer_comparison.empty:
        pe_col = _find_pe_column(peer_comparison)
        if pe_col is not None:
            peer_pes = []
            for val in peer_comparison[pe_col]:
                v = _safe_float(str(val).replace(",", ""))
                if v is not None and 0 < v < 500:
                    peer_pes.append(v)
            if len(peer_pes) >= 3:
                peer_pes_sorted = sorted(peer_pes)
                mid = len(peer_pes_sorted) // 2
                sector_median_pe = round(
                    peer_pes_sorted[mid] if len(peer_pes_sorted) % 2 != 0
                    else (peer_pes_sorted[mid - 1] + peer_pes_sorted[mid]) / 2,
                    2,
                )
                log.debug(f"[SKILL-I11] Sector median P/E from {len(peer_pes)} peers: {sector_median_pe}")

    if sector_median_pe is None or sector_median_pe == 0:
        return {
            "sector_median_pe": None,
            "pe_premium_discount_pct": None,
            "pe_vs_sector_signal": "na",
        }

    premium_pct = round(((pe - sector_median_pe) / sector_median_pe) * 100, 4)

    t = (config or {}).get("thresholds", {}).get("pe_vs_sector_premium_pct", {})
    discount_below = t.get("discount_below", -15)
    premium_above  = t.get("premium_above",  15)

    if premium_pct <= discount_below:
        signal = "discount"
    elif premium_pct >= premium_above:
        signal = "premium"
    else:
        signal = "inline"

    return {
        "sector_median_pe":       sector_median_pe,
        "pe_premium_discount_pct": premium_pct,
        "pe_vs_sector_signal":    signal,
    }


def _find_pe_column(df: pd.DataFrame) -> str | None:
    """Find the P/E ratio column in a peer comparison DataFrame."""
    for col in df.columns:
        col_lower = col.lower()
        if "p/e" in col_lower or "pe" in col_lower or "price/earn" in col_lower:
            return col
    return None


# ── SKILL-I12: Compute EV/EBITDA ─────────────────────────────────────────────

def compute_ev_ebitda(
    ev_ebitda_yfinance: float | None,
    ev_ebitda_screener: float | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I12: Compute EV/EBITDA.
    Prefers yfinance value; falls back to Screener.in value.
    Args:
        ev_ebitda_yfinance : EV/EBITDA from SKILL-D04
        ev_ebitda_screener : EV/EBITDA from SKILL-D05 (fallback)
        config             : merged config dict
    Returns: dict with ev_ebitda_value, ev_ebitda_signal
    """
    val = _safe_float(ev_ebitda_yfinance)
    if val is None:
        val = _safe_float(ev_ebitda_screener)
        if val is not None:
            log.debug(f"[SKILL-I12] Using Screener.in EV/EBITDA: {val}")

    if val is None:
        return {"ev_ebitda_value": None, "ev_ebitda_signal": "na"}

    t = (config or {}).get("thresholds", {}).get("ev_ebitda", {})
    green_below = t.get("green_below", 8)
    amber_below = t.get("amber_below", 15)

    if val <= green_below:
        signal = "green"
    elif val <= amber_below:
        signal = "amber"
    else:
        signal = "red"

    return {"ev_ebitda_value": round(val, 4), "ev_ebitda_signal": signal}