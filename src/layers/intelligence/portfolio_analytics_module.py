"""
portfolio_analytics_module.py
Layer      : Intelligence
Owns       : SKILL-I27, SKILL-I28, SKILL-I29, SKILL-I30
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from src.utils.logger import get_logger

log = get_logger(__name__)


def compute_correlation_matrix(price_data: dict) -> dict:
    """SKILL-I27: Compute inter-stock correlation matrix."""
    try:
        if len(price_data) < 2:
            return {"correlation_matrix": pd.DataFrame(),
                    "high_correlation_pairs": [], "avg_portfolio_correlation": None}
        returns = {}
        for ticker, df in price_data.items():
            if not df.empty and "Close" in df.columns:
                returns[ticker] = df["Close"].pct_change().dropna()
        if len(returns) < 2:
            return {"correlation_matrix": pd.DataFrame(),
                    "high_correlation_pairs": [], "avg_portfolio_correlation": None}
        ret_df = pd.DataFrame(returns).dropna()
        corr   = ret_df.corr()
        pairs  = []
        tickers = list(corr.columns)
        for i in range(len(tickers)):
            for j in range(i+1, len(tickers)):
                c = corr.iloc[i, j]
                if abs(c) > 0.7:
                    pairs.append((tickers[i], tickers[j], round(float(c), 4)))
        vals = [corr.iloc[i,j] for i in range(len(tickers))
                for j in range(i+1, len(tickers))]
        avg = round(float(np.mean(vals)), 4) if vals else None
        return {"correlation_matrix": corr,
                "high_correlation_pairs": pairs,
                "avg_portfolio_correlation": avg}
    except Exception as e:
        log.warning(f"Correlation matrix error: {e}")
        return {"correlation_matrix": pd.DataFrame(),
                "high_correlation_pairs": [], "avg_portfolio_correlation": None}


def compute_sector_allocation(holdings: list, current_prices: dict,
                               config: dict | None = None) -> dict:
    """SKILL-I28: Compute sector allocation vs targets."""
    try:
        sector_values: dict = {}
        total = 0.0
        for h in holdings:
            ticker = h["ticker"]
            sector = h.get("sector", "Others")
            price  = current_prices.get(ticker, 0) or 0
            value  = price * h.get("quantity", 0)
            sector_values[sector] = sector_values.get(sector, 0) + value
            total += value

        if total == 0:
            return {"sector_allocation": {}, "target_allocation": {},
                    "sector_drift": {}, "overweight_sectors": [],
                    "underweight_sectors": []}

        current_alloc = {s: round((v/total)*100, 2)
                         for s, v in sector_values.items()}
        target_alloc  = (config or {}).get("goals", {}).get(
            "target_sector_allocation", {}
        )
        drift_thresh  = (config or {}).get("goals", {}).get(
            "rebalancing_drift_threshold", 5
        )

        all_sectors = set(current_alloc) | set(target_alloc)
        drift = {
            s: round(current_alloc.get(s, 0) - target_alloc.get(s, 0), 2)
            for s in all_sectors
        }
        overweight  = [s for s, d in drift.items() if d >  drift_thresh]
        underweight = [s for s, d in drift.items() if d < -drift_thresh]

        return {
            "sector_allocation":  current_alloc,
            "target_allocation":  target_alloc,
            "sector_drift":       drift,
            "overweight_sectors": overweight,
            "underweight_sectors": underweight,
        }
    except Exception as e:
        log.warning(f"Sector allocation error: {e}")
        return {"sector_allocation": {}, "target_allocation": {},
                "sector_drift": {}, "overweight_sectors": [],
                "underweight_sectors": []}


def compute_portfolio_beta(holdings: list, betas: dict,
                            current_prices: dict) -> dict:
    """SKILL-I29: Compute weighted average portfolio beta."""
    try:
        total_value = sum(
            (current_prices.get(h["ticker"], 0) or 0) * h.get("quantity", 0)
            for h in holdings
        )
        if total_value == 0:
            return {"portfolio_beta": None, "beta_signal": "market_neutral",
                    "weight_breakdown": {}}
        weighted_beta = 0.0
        breakdown     = {}
        for h in holdings:
            ticker = h["ticker"]
            price  = current_prices.get(ticker, 0) or 0
            value  = price * h.get("quantity", 0)
            weight = value / total_value
            beta   = betas.get(ticker, 1.0) or 1.0
            weighted_beta += weight * beta
            breakdown[ticker] = {"weight": round(weight, 4), "beta": beta}

        weighted_beta = round(weighted_beta, 4)
        if weighted_beta < 0.8:   signal = "defensive"
        elif weighted_beta <= 1.2: signal = "market_neutral"
        else:                      signal = "aggressive"

        return {"portfolio_beta": weighted_beta, "beta_signal": signal,
                "weight_breakdown": breakdown}
    except Exception as e:
        log.warning(f"Portfolio beta error: {e}")
        return {"portfolio_beta": None, "beta_signal": "market_neutral",
                "weight_breakdown": {}}


def compute_portfolio_sharpe(portfolio_returns: pd.Series,
                              risk_free_rate: float) -> dict:
    """SKILL-I30: Compute portfolio Sharpe ratio."""
    try:
        if portfolio_returns is None or len(portfolio_returns) < 30:
            return {"sharpe_ratio": None, "sharpe_signal": "poor",
                    "portfolio_volatility": None}
        daily_rfr  = risk_free_rate / 252
        excess_ret = portfolio_returns - daily_rfr
        sharpe     = round(float(excess_ret.mean() / excess_ret.std() * np.sqrt(252)), 4)
        vol        = round(float(portfolio_returns.std() * np.sqrt(252)), 4)
        if sharpe > 1.5:   signal = "excellent"
        elif sharpe > 1.0: signal = "good"
        else:               signal = "poor"
        return {"sharpe_ratio": sharpe, "sharpe_signal": signal,
                "portfolio_volatility": vol}
    except Exception as e:
        log.warning(f"Sharpe ratio error: {e}")
        return {"sharpe_ratio": None, "sharpe_signal": "poor",
                "portfolio_volatility": None}
