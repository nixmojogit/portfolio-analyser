"""
rebuild_results.py
One-time utility script.

Reads the most recent analysis results from portfolio.db and
reconstructs data/portfolio/last_results.json so that app.py
can display them on startup without needing a fresh analysis run.

Run once from the project root:
    python rebuild_results.py
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

# ── Load config and orchestrator helper ───────────────────────────────────────
from src.layers.configuration.config_manager import load_config
from src.layers.action.orchestrator import _compute_net_recommendation

PORTFOLIO_DB = Path("data/portfolio/portfolio.db")
LAST_RESULTS = Path("data/portfolio/last_results.json")

# Scorecard weights (matches scorecard_weights.yaml)
WEIGHTS = {
    "fundamental": 0.30,
    "valuation":   0.25,
    "technical":   0.20,
    "sentiment":   0.15,
    "risk":        0.10,
}

GRADE_CUTOFFS = {
    "fundamental": {"Strong": 65,      "Moderate": 35},
    "technical":   {"Bullish": 65,     "Neutral":  35},
    "valuation":   {"Undervalued": 65, "Fair":     35},
    "risk":        {"Low": 65,         "Moderate": 35},
    "sentiment":   {"Positive": 65,    "Mixed":    35},
}

REC_THRESHOLDS = {"Strong Buy": 75, "Buy": 55, "Hold": 35, "Reduce": 20}


def _grade(scorecard: str, score: float | None) -> str:
    if score is None:
        return list(GRADE_CUTOFFS.get(scorecard, {"Moderate": 0}).keys())[-1]
    cuts = GRADE_CUTOFFS.get(scorecard, {})
    keys = list(cuts.keys())
    vals = list(cuts.values())
    if score >= vals[0]:
        return keys[0]
    if score >= vals[1]:
        return keys[1]
    fallbacks = {
        "fundamental": "Weak",     "technical":  "Bearish",
        "valuation":   "Overvalued","risk":       "High",
        "sentiment":   "Negative",
    }
    return fallbacks.get(scorecard, "Unknown")


def _recommendation(score: float | None) -> str:
    if score is None:
        return "Hold"
    if score >= REC_THRESHOLDS["Strong Buy"]: return "Strong Buy"
    if score >= REC_THRESHOLDS["Buy"]:        return "Buy"
    if score >= REC_THRESHOLDS["Hold"]:       return "Hold"
    if score >= REC_THRESHOLDS["Reduce"]:     return "Reduce"
    return "Exit"


# ── DB Loaders ────────────────────────────────────────────────────────────────

def load_holdings(conn) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute("SELECT * FROM holdings").fetchall()]


def load_latest_scores(conn) -> dict[str, dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT s.*
        FROM scores_history s
        INNER JOIN (
            SELECT ticker, MAX(score_date) AS max_date
            FROM scores_history
            GROUP BY ticker
        ) latest ON s.ticker = latest.ticker AND s.score_date = latest.max_date
    """).fetchall()
    return {r["ticker"]: dict(r) for r in rows}


def load_latest_recommendations(conn) -> dict[str, dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT r.*
        FROM recommendations_history r
        INNER JOIN (
            SELECT ticker, MAX(rowid) AS max_rowid
            FROM recommendations_history
            GROUP BY ticker
        ) latest ON r.ticker = latest.ticker AND r.rowid = latest.max_rowid
    """).fetchall()
    result = {}
    for row in rows:
        d = dict(row)
        for key in ("supporting_signals", "contradicting_signals"):
            try:
                d[key] = json.loads(d.get(key) or "[]")
            except Exception:
                d[key] = []
        result[d["ticker"]] = d
    return result


def load_watchlist(conn) -> list[dict]:
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM watchlist ORDER BY overall_score DESC"
        ).fetchall()
        candidates = []
        for row in rows:
            d = dict(row)
            try:
                notes = json.loads(d.get("notes") or "{}")
            except Exception:
                notes = {}
            candidates.append({
                "ticker":     d.get("ticker"),
                "sector":     d.get("sector"),
                "peer_score": d.get("overall_score"),
                "mode":       notes.get("mode", "gap_fill"),
                "action_tag": notes.get("action_tag", "Initiate"),
                "score_gap":  notes.get("score_gap"),
                "rationale":  {},
            })
        return candidates
    except Exception:
        return []


def load_latest_rebalancing(conn) -> dict:
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM rebalancing_log ORDER BY plan_date DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {}
        d = dict(row)
        return {
            "rebalancing_plan":       json.loads(d.get("plan_data") or "[]"),
            "estimated_beta_after":   d.get("estimated_beta_after"),
            "estimated_sharpe_after": d.get("estimated_sharpe_after"),
        }
    except Exception:
        return {}


def load_active_alerts(conn) -> list[dict]:
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM alerts_log WHERE is_resolved = 0 ORDER BY created_at DESC"
        ).fetchall()
        alerts = []
        for row in rows:
            d = dict(row)
            try:
                d["metadata"] = json.loads(d.get("metadata") or "{}")
            except Exception:
                d["metadata"] = {}
            alerts.append(d)
        return alerts
    except Exception:
        return []


# ── Sector Drift Computation ──────────────────────────────────────────────────

def compute_sector_drift(
    holdings: list[dict],
    target_alloc: dict,
) -> dict[str, float]:
    """Compute current sector allocation and drift vs target."""
    sector_values: dict[str, float] = {}
    total = 0.0
    for h in holdings:
        sector = h.get("sector", "Others")
        value  = (h.get("buy_price", 0) or 0) * (h.get("quantity", 0) or 0)
        sector_values[sector] = sector_values.get(sector, 0) + value
        total += value

    if total == 0:
        return {}

    current_alloc = {s: (v / total * 100) for s, v in sector_values.items()}
    all_sectors   = set(current_alloc) | set(target_alloc)

    return {
        s: round(current_alloc.get(s, 0) - target_alloc.get(s, 0), 2)
        for s in all_sectors
    }


def derive_portfolio_action(
    ticker: str,
    sector: str,
    ticker_action_map: dict[str, str],
    sector_drift: dict[str, float],
    drift_threshold: float,
) -> str | None:
    """
    Derive the portfolio action for a holding.
    Priority: explicit rebalancing plan entry → sector drift signal → None
    """
    # 1. Direct entry from G3 rebalancing plan
    pa = ticker_action_map.get(ticker)
    if pa:
        return pa

    # 2. Derive from sector drift
    drift = sector_drift.get(sector, 0)
    if drift > drift_threshold:
        return "Trim"
    if drift < -drift_threshold:
        return "Add"

    return None


# ── Main Builder ──────────────────────────────────────────────────────────────

def build_results() -> dict:
    if not PORTFOLIO_DB.exists():
        print(f"ERROR: portfolio.db not found at {PORTFOLIO_DB}")
        return {}

    config          = load_config()
    goals           = config.get("goals", {})
    target_alloc    = goals.get("target_sector_allocation", {})
    drift_threshold = float(goals.get("rebalancing_drift_threshold", 5))

    with sqlite3.connect(PORTFOLIO_DB) as conn:
        holdings    = load_holdings(conn)
        scores      = load_latest_scores(conn)
        recs        = load_latest_recommendations(conn)
        watchlist   = load_watchlist(conn)
        rebalancing = load_latest_rebalancing(conn)
        alerts      = load_active_alerts(conn)

    if not holdings:
        print("ERROR: No holdings found in portfolio.db")
        return {}

    print(f"Found {len(holdings)} holding(s), {len(scores)} score record(s)")

    # Build ticker → portfolio action from stored rebalancing plan
    rebal_plan = rebalancing.get("rebalancing_plan", [])
    ticker_action_map: dict[str, str] = {
        item["ticker"]: item["action"].title()
        for item in rebal_plan
        if item.get("ticker") and item.get("action")
    }

    # Compute sector drift from current holdings vs target allocations
    sector_drift = compute_sector_drift(holdings, target_alloc)

    # Run timestamp
    run_ts = datetime.now().isoformat()
    if scores:
        latest_date = max(s.get("score_date", "") for s in scores.values())
        if latest_date:
            run_ts = f"{latest_date}T16:30:00"

    # Total portfolio value for concentration %
    total_value = sum(
        (h.get("buy_price", 0) or 0) * (h.get("quantity", 0) or 0)
        for h in holdings
    )

    # ── Build per-ticker G1 results ───────────────────────────────────────────
    g1_results: dict = {}

    for h in holdings:
        ticker    = h["ticker"]
        buy_price = float(h.get("buy_price") or 0)
        quantity  = float(h.get("quantity")  or 0)
        sl_pct    = float(h.get("stop_loss_pct") or 8.0)
        sector    = h.get("sector", "Unknown")

        sc = scores.get(ticker, {})
        rc = recs.get(ticker, {})

        f_score = float(sc.get("fundamental_score") or 50.0)
        t_score = float(sc.get("technical_score")   or 50.0)
        v_score = float(sc.get("valuation_score")   or 50.0)
        r_score = float(sc.get("risk_score")        or 50.0)
        s_score = float(sc.get("sentiment_score")   or 50.0)

        overall = float(sc.get("overall_score") or (
            f_score * WEIGHTS["fundamental"] +
            v_score * WEIGHTS["valuation"]   +
            t_score * WEIGHTS["technical"]   +
            s_score * WEIGHTS["sentiment"]   +
            r_score * WEIGHTS["risk"]
        ))
        rec = sc.get("recommendation") or _recommendation(overall)

        holding_value = buy_price * quantity
        concentration = (holding_value / total_value * 100) if total_value > 0 else 0
        stop_loss_price = round(buy_price * (1 - sl_pct / 100), 2)

        # ── Portfolio action + net recommendation ─────────────────────────────
        pa = derive_portfolio_action(
            ticker, sector, ticker_action_map, sector_drift, drift_threshold
        )
        net = _compute_net_recommendation(
            stock_rec        = rec,
            portfolio_action = pa,
            sector           = sector,
            overall_score    = overall,
        )

        score_breakdown = {
            "fundamental": {"score": f_score, "weight": WEIGHTS["fundamental"]},
            "valuation":   {"score": v_score, "weight": WEIGHTS["valuation"]},
            "technical":   {"score": t_score, "weight": WEIGHTS["technical"]},
            "sentiment":   {"score": s_score, "weight": WEIGHTS["sentiment"]},
            "risk":        {"score": r_score, "weight": WEIGHTS["risk"]},
        }

        g1_results[ticker] = {
            "ticker":            ticker,
            "company_name":      h.get("company_name", ticker),
            "sector":            sector,
            "current_price":     buy_price,
            "buy_price":         buy_price,
            "quantity":          quantity,
            "holding_value":     round(holding_value, 2),
            "concentration_pct": round(concentration, 2),
            "overall_score":     round(overall, 2),
            "recommendation":    rec,
            "score_breakdown":   score_breakdown,

            "fundamental_score": {
                "fundamental_score":     f_score,
                "fundamental_grade":     _grade("fundamental", f_score),
                "fundamental_breakdown": {},
            },
            "technical_score": {
                "technical_score":     t_score,
                "technical_grade":     _grade("technical", t_score),
                "technical_breakdown": {},
            },
            "valuation_score": {
                "valuation_score":     v_score,
                "valuation_grade":     _grade("valuation", v_score),
                "valuation_breakdown": {},
            },
            "risk_score": {
                "risk_score":     r_score,
                "risk_grade":     _grade("risk", r_score),
                "risk_breakdown": {},
            },
            "sentiment_score": {
                "sentiment_scorecard_score": s_score,
                "sentiment_grade":           _grade("sentiment", s_score),
                "sentiment_breakdown":       {},
            },

            "stop_loss": {
                "stop_loss_price":       stop_loss_price,
                "stop_loss_method":      "fixed_pct",
                "atr_value":             None,
                "atr_multiplier":        2.0,
                "equivalent_stop_pct":   sl_pct,
                "current_drawdown_pct":  0.0,
                "proximity_to_stop_pct": sl_pct,
                "stop_loss_signal":      "safe",
            },

            "thesis_intact": bool(h.get("thesis_intact", 1)),

            "recommendation_detail": {
                "recommendation":           rec,
                "recommendation_rationale": rc.get("rationale", ""),
                "supporting_signals":       rc.get("supporting_signals", []),
                "contradicting_signals":    rc.get("contradicting_signals", []),
                "recommended_action":       rc.get("recommended_action", ""),
                "base_recommendation":      rec,
                "override_applied":         False,
            },

            "metrics": {
                "revenue_growth_yoy":   None, "net_margin":         None,
                "margin_trend":         None, "fcf":                None,
                "roic":                 None, "pe_ratio":           None,
                "peg_ratio":            None, "ev_ebitda":          None,
                "beta":                 None, "rsi":                None,
                "sma50":                None, "sma200":             None,
                "trend":                None, "momentum_score":     None,
                "promoter_holding":     None, "fii_holding":        None,
                "sentiment_score":      s_score,
                "sentiment_label":      "neutral",
                "positive_themes":      [],   "negative_themes":    [],
                "analyst_rec":          None, "analyst_rec_firm":   None,
                "analyst_rec_source":   None, "analyst_rec_note":   None,
                "analyst_target":       None, "analyst_target_source": None,
                "analyst_target_note":  None,
                "analyst_target_mean":  None, "analyst_target_low": None,
                "analyst_target_high":  None, "analyst_all_ratings": [],
                "current_price":        buy_price,
            },

            "news_headlines":     [],
            "portfolio_action":   pa or "—",
            "net_recommendation": net["net_recommendation"],
            "net_reason":         net["reason"],
            "run_timestamp":      run_ts,
        }

    # ── G2 ────────────────────────────────────────────────────────────────────
    g2_results = {
        "ranked_candidates":   watchlist,
        "top_recommendations": watchlist[:5],
    }

    # ── G3 ────────────────────────────────────────────────────────────────────
    # Reconstruct sector allocation for display
    sector_values: dict[str, float] = {}
    total = 0.0
    for h in holdings:
        s = h.get("sector", "Others")
        v = (h.get("buy_price", 0) or 0) * (h.get("quantity", 0) or 0)
        sector_values[s] = sector_values.get(s, 0) + v
        total += v
    current_alloc = {s: round(v/total*100, 2) for s, v in sector_values.items()} if total else {}

    overweight  = [s for s, d in sector_drift.items() if d >  drift_threshold]
    underweight = [s for s, d in sector_drift.items() if d < -drift_threshold]
    urgency     = "immediate" if any(abs(d) >= 10 for d in sector_drift.values()) \
                  else "soon" if any(abs(d) >= drift_threshold for d in sector_drift.values()) \
                  else "monitor"

    g3_results = {
        "rebalancing_plan":      rebal_plan,
        "estimated_beta_after":  rebalancing.get("estimated_beta_after"),
        "portfolio_analytics": {
            "sector_allocation":   current_alloc,
            "target_allocation":   target_alloc,
            "sector_drift":        sector_drift,
            "overweight_sectors":  overweight,
            "underweight_sectors": underweight,
            "portfolio_beta":      None,
            "beta_signal":         None,
            "high_corr_pairs":     [],
            "avg_correlation":     None,
            "drift_urgency":       urgency,
        },
    }

    return {
        "results":       g1_results,
        "g2_results":    g2_results,
        "g3_results":    g3_results,
        "run_timestamp": run_ts,
        "errors":        {},
        "alerts":        alerts,
    }


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    print("Rebuilding last_results.json from portfolio.db ...")
    results = build_results()
    if not results:
        print("Rebuild failed — no data to write.")
        return

    LAST_RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_RESULTS, "w") as f:
        json.dump(results, f, default=str, indent=2)

    ticker_count = len(results.get("results", {}))
    g2_count     = len(results.get("g2_results", {}).get("ranked_candidates", []))
    g3_count     = len(results.get("g3_results", {}).get("rebalancing_plan", []))

    print(f"✅ Done — {LAST_RESULTS}")
    print(f"   Holdings:          {ticker_count}")
    print(f"   G2 candidates:     {g2_count}")
    print(f"   Rebalancing items: {g3_count}")
    print()
    print("Now run:  streamlit run app.py")
    print("The dashboard will load with Portfolio Action and Net Recommendation populated.")


if __name__ == "__main__":
    main()