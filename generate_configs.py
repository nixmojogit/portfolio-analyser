"""
generate_configs.py
Writes all six YAML configuration files with default values.
Usage:
    python generate_configs.py           # skip existing files
    python generate_configs.py --force   # overwrite all files
"""

from __future__ import annotations
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML not found. Run: pip install PyYAML")
    sys.exit(1)

FORCE = "--force" in sys.argv
CONFIG_DIR = Path("config")


# ── Config file definitions ───────────────────────────────────────────────────

CONFIGS: dict[str, dict] = {}

# ── system.yaml ───────────────────────────────────────────────────────────────
CONFIGS["system.yaml"] = {
    "app_name": "Portfolio Analyser",
    "log_level": "INFO",
    "db_path": "data/cache/market_data.db",
    "portfolio_db_path": "data/portfolio/portfolio.db",
    "export_path": "data/exports/",
    "market": "NSE",
    "benchmark_index": "^NSEI",
    "risk_free_rate": 0.065,        # RBI repo rate — update as policy changes
    "default_exchange_suffix": "NS",
    "scraper_request_delay_seconds": 2.5,
    "max_retries": 3,
    "retry_backoff_base_seconds": 2,
}

# ── portfolio.yaml ────────────────────────────────────────────────────────────
# Populated from Excel via SKILL-D14 in Phase 4.
# Add your holdings here manually or leave for auto-import.
CONFIGS["portfolio.yaml"] = {
    "holdings": [
        {
            "ticker": "RELIANCE.NS",
            "company_name": "Reliance Industries",
            "sector": "Energy",
            "buy_price": 2450.00,
            "quantity": 10,
            "buy_date": "15-01-2024",
            "stop_loss_pct": 8.0,
            "thesis": "Dominant conglomerate with Jio and retail as growth engines.",
            "thesis_intact": True,
        },
    ],
    "_note": (
        "This file will be auto-populated from your Excel file "
        "when SKILL-D14 runs in Phase 4. Update holdings manually "
        "or leave the import to handle it."
    ),
}

# ── goals.yaml ────────────────────────────────────────────────────────────────
CONFIGS["goals.yaml"] = {
    "active_goals": {
        "G1": True,
        "G2": True,
        "G3": True,
    },

    # Target sector allocation (%) — must sum to 100
    "target_sector_allocation": {
        "Technology":         20,
        "Financial Services": 20,
        "Consumer":           15,
        "Healthcare":         10,
        "Energy":             10,
        "Pharma":             10,
        "Automobile":          5,
        "Infrastructure":      5,
        "FMCG":                5,
        "Others":              0,
    },

    # G3 rebalancing triggers
    "rebalancing_drift_threshold": 5,       # % drift before rebalancing flagged
    "rebalancing_urgency_immediate": 10,    # % drift for immediate urgency

    # G2 screening filters
    "screening_filters": {
        "min_market_cap_cr": 1000,          # minimum market cap in crores
        "min_revenue_growth_yoy_pct": 5,    # minimum YoY revenue growth %
        "fcf_must_be_positive": True,
        "min_avg_daily_volume": 100000,     # shares per day
    },

    # Portfolio construction limits
    "max_concentration_per_stock_pct": 15,  # max % of portfolio in one stock
    "min_holdings": 10,
    "max_holdings": 20,
    "cash_reserve_pct": 5,                  # keep 5% in cash for opportunities

    # Scheduling cadence (APScheduler cron-style)
    "schedule": {
        "g1_daily_time_ist":    "16:30",    # after NSE market close
        "g2_weekly_day":        "monday",
        "g2_weekly_time_ist":   "06:00",
        "g3_quarterly_months":  [1, 4, 7, 10],
        "g3_quarterly_day":     1,
        "g3_quarterly_time_ist":"06:00",
    },
}

# ── thresholds.yaml ───────────────────────────────────────────────────────────
CONFIGS["thresholds.yaml"] = {

    # ── Fundamental metrics ──────────────────────────────────────────────────

    "revenue_growth_yoy_pct": {
        "green_above": 10,
        "amber_above": 0,
        "red_below":   0,
    },
    "net_profit_margin_pct": {
        "green_above": 15,
        "amber_above": 5,
        "red_below":   5,
    },
    "fcf": {
        "green":  "positive_and_growing",
        "amber":  "positive_but_flat",
        "red":    "negative",
    },
    "fcf_growth_yoy_pct": {
        "green_above": 10,
        "amber_above": 0,
        "red_below":   0,
    },
    "fcf_vs_net_income_ratio": {
        "green_above": 0.8,
        "amber_above": 0.5,
        "red_below":   0.5,
    },
    "debt_to_equity": {
        "green_below": 0.5,
        "amber_below": 1.5,
        "red_above":   2.0,
    },
    "interest_coverage_ratio": {
        "green_above": 5.0,
        "amber_above": 2.0,
        "red_below":   2.0,
    },
    "roe_pct": {
        "green_above": 15,
        "amber_above": 10,
        "red_below":   10,
    },
    "roic_pct": {
        "green_above": 12,
        "amber_above": 8,
        "red_below":   8,
    },
    "operating_margin_pct": {
        "green_above": 15,
        "amber_above": 8,
        "red_below":   8,
    },
    "eps_growth_yoy_pct": {
        "green_above": 10,
        "amber_above": 0,
        "red_below":   0,
    },

    # ── Valuation metrics ────────────────────────────────────────────────────

    "pe_ratio": {
        "green_below": 15,
        "amber_below": 25,
        "red_above":   30,
    },
    "forward_pe": {
        "green_below": 15,
        "amber_below": 22,
        "red_above":   25,
    },
    "peg_ratio": {
        "green_below": 1.0,
        "amber_below": 1.5,
        "red_above":   2.0,
    },
    "pb_ratio": {
        "green_below": 1.5,
        "amber_below": 3.0,
        "red_above":   4.0,
    },
    "ps_ratio": {
        "green_below": 2,
        "amber_below": 5,
        "red_above":   8,
    },
    "ev_ebitda": {
        "green_below": 8,
        "amber_below": 15,
        "red_above":   20,
    },
    "pe_vs_sector_premium_pct": {
        "discount_below":  -15,    # > 15% cheaper than sector = discount
        "inline_between":  [-15, 15],
        "premium_above":    15,    # > 15% more expensive = premium
    },
    "dividend_yield_pct": {
        "green_above": 3,
        "amber_above": 1,
        "red_below":   1,
    },
    "payout_ratio_pct": {
        "green_between": [30, 60],
        "amber_between": [60, 80],
        "red_above":     80,
    },

    # ── Technical metrics ────────────────────────────────────────────────────

    "price_vs_sma50_pct": {
        "bullish_above":  3,
        "neutral_between":[-3, 3],
        "bearish_below": -3,
    },
    "price_vs_sma200_pct": {
        "bullish_above":  0,
        "bearish_below":  0,
    },
    "rsi": {
        "oversold_below":   30,
        "neutral_low":      40,
        "neutral_high":     60,
        "overbought_above": 70,
    },
    "volume_ratio": {
        "high_conviction_above": 1.5,
        "low_conviction_below":  0.5,
    },
    "week_52_position_pct_from_high": {
        "strong_momentum_within": 10,   # within 10% of 52W high = strong
        "weak_momentum_beyond":   40,   # more than 40% below 52W high = weak
    },

    # ── Risk metrics ─────────────────────────────────────────────────────────

    "beta": {
        "low_below":      0.8,
        "moderate_below": 1.2,
        "high_above":     1.5,
    },
    "short_interest_pct": {
        "green_below": 5,
        "amber_below": 15,
        "red_above":   20,
    },
    "portfolio_concentration_pct": {
        "green_below": 5,
        "amber_below": 10,
        "red_above":   15,
    },
    "debt_ebitda": {
        "green_below": 2,
        "amber_below": 3,
        "red_above":   4,
    },
    "current_ratio": {
        "green_above": 2,
        "amber_above": 1,
        "red_below":   1,
    },
    "stop_loss_warning_proximity_pct": 3,   # warn when within 3% of stop-loss

    # ── Sentiment metrics ────────────────────────────────────────────────────

    "earnings_surprise_pct": {
        "consistent_beat_above": 5,
        "consistent_miss_below": -5,
    },
    "analyst_target_upside_pct": {
        "green_above": 15,
        "amber_above": 0,
        "red_below":   0,
    },
    "news_sentiment_score": {
        "positive_above": 60,
        "negative_below": 40,
    },
    "institutional_change_qoq_pct": {
        "accumulating_above": 1,
        "distributing_below": -1,
    },

    # ── India-specific metrics ────────────────────────────────────────────────

    "promoter_holding_pct": {
        "green_above": 50,
        "amber_above": 40,
        "red_below":   40,
    },
    "promoter_change_qoq_pct": {
        "significant_drop_below": -3,   # drop > 3% in a quarter = red flag
    },
    "promoter_pledge_pct": {
        "green_below": 10,
        "amber_below": 30,
        "red_above":   30,
    },

    # ── Portfolio-level metrics ───────────────────────────────────────────────

    "sharpe_ratio": {
        "excellent_above": 1.5,
        "good_above":      1.0,
        "poor_below":      1.0,
    },
    "portfolio_beta": {
        "defensive_below":      0.8,
        "market_neutral_below": 1.2,
        "aggressive_above":     1.5,
    },
    "max_drawdown_pct": {
        "green_below": 10,
        "amber_below": 20,
        "red_above":   20,
    },
    "sector_concentration_pct": {
        "green_below": 25,
        "amber_below": 35,
        "red_above":   40,
    },
    "inter_stock_correlation": {
        "high_correlation_above": 0.7,   # pairs above this = diversification concern
    },
}

# ── scorecard_weights.yaml ────────────────────────────────────────────────────
CONFIGS["scorecard_weights.yaml"] = {

    # Overall stock score — weights must sum to 1.0
    "overall_score_weights": {
        "fundamental": 0.30,
        "valuation":   0.25,
        "technical":   0.20,
        "sentiment":   0.15,
        "risk":        0.10,
    },

    # Signal to sub-score mapping (used by scorecard_aggregator.py)
    "signal_scores": {
        "green":  80,
        "amber":  50,
        "red":    15,
        "na":     None,    # excluded from average
    },

    # Score to recommendation mapping
    "recommendation_thresholds": {
        "strong_buy": 75,
        "buy":        55,
        "hold":       35,
        "reduce":     20,
        "exit":       0,
    },

    # Scorecard grade cutoffs
    "grade_cutoffs": {
        "fundamental": {
            "strong_above":   65,
            "moderate_above": 35,
            "weak_below":     35,
        },
        "technical": {
            "bullish_above":  65,
            "neutral_above":  35,
            "bearish_below":  35,
        },
        "valuation": {
            "undervalued_above": 65,
            "fair_above":        35,
            "overvalued_below":  35,
        },
        "risk": {
            "low_above":      65,
            "moderate_above": 35,
            "high_below":     35,
        },
        "sentiment": {
            "positive_above": 65,
            "mixed_above":    35,
            "negative_below": 35,
        },
    },

    # G2 portfolio fit adjustment weight
    "portfolio_fit_weight": 0.20,

    # Exit override rules
    "exit_overrides": {
        "stop_loss_breach_triggers_exit":  True,
        "thesis_broken_triggers_reduce":   True,
        "overvaluation_trim_peg_above":    2.5,
        "overvaluation_trim_rsi_above":    70,
    },
}

# ── skills.yaml ───────────────────────────────────────────────────────────────
CONFIGS["skills.yaml"] = {
    "skills": {

        # ── Data Layer ───────────────────────────────────────────────────────
        "SKILL-D01": {"enabled": True,  "cache_ttl_hours": 24},
        "SKILL-D02": {"enabled": True,  "cache_ttl_hours": 1},
        "SKILL-D03": {"enabled": True,  "cache_ttl_hours": 168},
        "SKILL-D04": {"enabled": True,  "cache_ttl_hours": 24},
        "SKILL-D05": {"enabled": True,  "cache_ttl_hours": 168},
        "SKILL-D06": {"enabled": True,  "cache_ttl_hours": 24},
        "SKILL-D07": {"enabled": True,  "cache_ttl_hours": 720},
        "SKILL-D08": {"enabled": True,  "cache_ttl_hours": 720},
        "SKILL-D09": {"enabled": True,  "cache_ttl_hours": 6},
        "SKILL-D10": {"enabled": True,  "cache_ttl_hours": 6},
        "SKILL-D11": {"enabled": True,  "cache_ttl_hours": 168},
        "SKILL-D12": {"enabled": True,  "cache_ttl_hours": 24},
        "SKILL-D13": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-D14": {"enabled": True,  "cache_ttl_hours": None},

        # ── Intelligence Layer ───────────────────────────────────────────────
        "SKILL-I01": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I02": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I03": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I04": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I05": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I06": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I07": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I08": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I09": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I10": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I11": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I12": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I13": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I14": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I15": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I16": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I17": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I18": {"enabled": True,  "cache_ttl_hours": 12},   # Claude AI — has cost
        "SKILL-I19": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I20": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I21": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I22": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I23": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I24": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I25": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I26": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I27": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I28": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I29": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I30": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-I31": {"enabled": True,  "cache_ttl_hours": None},

        # ── Action Layer ─────────────────────────────────────────────────────
        "SKILL-A01": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A02": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A03": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A04": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A05": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A06": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A07": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A08": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A09": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A10": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A11": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A12": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-A13": {"enabled": True,  "cache_ttl_hours": None},

        # ── Presentation Layer ───────────────────────────────────────────────
        "SKILL-P01": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-P02": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-P03": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-P04": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-P05": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-P06": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-P07": {"enabled": True,  "cache_ttl_hours": None},
        "SKILL-P08": {"enabled": True,  "cache_ttl_hours": None},
    }
}


# ── Writer ────────────────────────────────────────────────────────────────────

def write_configs(configs: dict[str, dict], force: bool = False) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    written, skipped, errors = 0, 0, 0

    print(f"\n  Portfolio Analyser — Config Generator")
    print(f"  Mode: {'overwrite' if force else 'skip existing'}")
    print(f"{'─' * 55}")

    for filename, content in configs.items():
        path = CONFIG_DIR / filename
        try:
            if path.exists() and not force:
                # Check if file is empty — write even without --force
                if path.stat().st_size == 0:
                    pass   # fall through to write
                else:
                    print(f"  SKIP   {path}  (use --force to overwrite)")
                    skipped += 1
                    continue

            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    content,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                    indent=2,
                )
            print(f"  WRITE  {path}")
            written += 1

        except Exception as e:
            print(f"  ERROR  {path}: {e}")
            errors += 1

    print(f"\n{'─' * 55}")
    print(f"  ✅  Written  : {written}")
    print(f"  ⏭   Skipped  : {skipped}")
    print(f"  ❌  Errors   : {errors}")
    print(f"{'─' * 55}")
    print("\n  All config files ready.")
    print("  Next: review config/ files and adjust values to your preference.\n")


if __name__ == "__main__":
    write_configs(CONFIGS, force=FORCE)