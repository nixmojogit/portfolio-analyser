"""
optimisation_engine.py
Layer      : Action
Owns       : SKILL-A05, SKILL-A06
"""

from __future__ import annotations
from typing import Any
from src.utils.logger import get_logger

log = get_logger(__name__)


def detect_sector_allocation_drift(
    sector_drift: dict[str, float],
    config: dict | None = None,
) -> dict[str, Any]:
    """SKILL-A05: Detect sector allocation drift."""
    if not sector_drift:
        return {
            "drift_detected":      False,
            "sectors_to_trim":     [],
            "sectors_to_add":      [],
            "rebalancing_urgency": "monitor",
        }

    goals        = (config or {}).get("goals", {})
    drift_thresh = float(goals.get("rebalancing_drift_threshold", 5))
    urgent_thresh= float(goals.get("rebalancing_urgency_immediate", 10))

    sectors_to_trim = [s for s, d in sector_drift.items() if d >  drift_thresh]
    sectors_to_add  = [s for s, d in sector_drift.items() if d < -drift_thresh]
    drift_detected  = bool(sectors_to_trim or sectors_to_add)

    if not drift_detected:
        urgency = "monitor"
    else:
        max_drift = max(abs(d) for d in sector_drift.values())
        if max_drift >= urgent_thresh:  urgency = "immediate"
        elif max_drift >= drift_thresh: urgency = "soon"
        else:                           urgency = "monitor"

    log.info(
        f"[SKILL-A05] Drift: trim={sectors_to_trim} "
        f"add={sectors_to_add} urgency={urgency}"
    )
    return {
        "drift_detected":      drift_detected,
        "sectors_to_trim":     sectors_to_trim,
        "sectors_to_add":      sectors_to_add,
        "rebalancing_urgency": urgency,
    }


def generate_rebalancing_plan(
    sectors_to_trim: list[str],
    sectors_to_add: list[str],
    ranked_candidates: list[dict],
    holdings: list[dict],
    current_prices: dict[str, float],
    portfolio_beta: float | None,
    portfolio_sharpe: float | None,
    config: dict | None = None,
) -> dict[str, Any]:
    """SKILL-A06: Generate portfolio rebalancing plan."""
    plan = []

    # Safe defaults
    portfolio_beta    = portfolio_beta    or 1.0
    portfolio_sharpe  = portfolio_sharpe  or 0.0
    ranked_candidates = ranked_candidates or []
    holdings          = holdings          or []
    current_prices    = current_prices    or {}
    sectors_to_trim   = sectors_to_trim   or []
    sectors_to_add    = sectors_to_add    or []

    goals        = (config or {}).get("goals", {})
    target_alloc = goals.get("target_sector_allocation", {}) or {}

    total_value = sum(
        (current_prices.get(h.get("ticker",""), 0) or 0) * h.get("quantity", 0)
        for h in holdings
    )

    # Trim overweight sectors
    for sector in sectors_to_trim:
        sector_holdings = [h for h in holdings if h.get("sector") == sector]
        for h in sector_holdings:
            ticker        = h.get("ticker", "")
            price         = current_prices.get(ticker, 0) or 0
            current_value = price * h.get("quantity", 0)
            current_wt    = (current_value / total_value * 100) if total_value > 0 else 0
            n_stocks      = max(len(sector_holdings), 1)
            target_wt     = (target_alloc.get(sector, 0) or 0) / n_stocks
            trade_value   = max(0, (current_wt - target_wt) / 100 * total_value)
            trade_shares  = int(trade_value / price) if price > 0 else 0
            if trade_shares > 0:
                plan.append({
                    "action":         "trim",
                    "ticker":         ticker,
                    "sector":         sector,
                    "current_weight": round(current_wt, 2),
                    "target_weight":  round(target_wt, 2),
                    "trade_shares":   trade_shares,
                    "trade_value":    round(trade_value, 2),
                })

    # Add candidates for underweight sectors
    for candidate in ranked_candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("sector") not in sectors_to_add:
            continue
        if candidate.get("action_tag") not in ("Initiate", "Switch", "Distribute"):
            continue

        ticker      = candidate.get("ticker", "")
        sector      = candidate.get("sector", "")
        target_wt   = target_alloc.get(sector, 0) or 0
        trade_value = (target_wt / 100) * total_value
        price       = current_prices.get(ticker, 0) or 0

        if price == 0:
            try:
                from src.layers.data.price_module import fetch_realtime_price_snapshot
                snap  = fetch_realtime_price_snapshot(ticker)
                price = snap.get("current_price") or 0
            except Exception:
                pass

        trade_shares = int(trade_value / price) if price > 0 else 0
        plan.append({
            "action":         (candidate.get("action_tag") or "Initiate").lower(),
            "ticker":         ticker,
            "sector":         sector,
            "current_weight": 0.0,
            "target_weight":  round(target_wt, 2),
            "trade_shares":   trade_shares,
            "trade_value":    round(trade_value, 2),
            "score":          candidate.get("peer_score"),
            "mode":           candidate.get("mode"),
        })

    log.info(f"[SKILL-A06] Rebalancing plan: {len(plan)} actions")
    return {
        "rebalancing_plan":       plan,
        "estimated_beta_after":   portfolio_beta,
        "estimated_sharpe_after": portfolio_sharpe,
    }


def _compute_trade_size(ticker, current_weight, target_weight,
                        total_portfolio_value, current_price) -> dict:
    trade_value  = abs(target_weight - current_weight) / 100 * total_portfolio_value
    trade_shares = int(trade_value / current_price) if current_price > 0 else 0
    return {"shares_to_trade": trade_shares, "value_to_trade": round(trade_value, 2)}
