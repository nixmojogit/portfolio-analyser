"""
discovery_engine.py
Layer      : Action
Owns       : SKILL-A02, SKILL-A03, SKILL-A04
Description: G2 discovery — fetches Nifty sector index constituents
             dynamically from niftyindices.com via SKILL-D15, removes
             existing holdings, scores each candidate using the full
             scoring pipeline, and returns top N ranked stocks as new ideas.
"""

from __future__ import annotations
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


# ── SKILL-A02: Screen New Investment Ideas ────────────────────────────────────

def screen_new_ideas(
    holdings: list[dict],
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-A02: Screen New Investment Ideas.
    Fetches all Nifty sector index constituents from niftyindices.com (SKILL-D15),
    removes existing portfolio holdings, scores each candidate using the full
    scoring pipeline (SKILL-A03), and returns top 10 ranked by Overall Score.
    Args:
        holdings : list of current portfolio holdings dicts
        config   : merged config dict
    Returns: dict with:
        new_ideas          (list of top 10 scored candidates)
        total_evaluated    (int: candidates that passed min score)
        total_candidates   (int: total unique candidates before scoring)
        ranked_candidates  (same as new_ideas — for backward compatibility)
        top_recommendations(same as new_ideas[:5] — for backward compatibility)
    """
    from src.layers.data.sector_universe_module import fetch_all_sector_constituents

    goals     = (config or {}).get("goals", {})
    sectors   = list(goals.get("target_sector_allocation", {}).keys())

    # Existing portfolio base symbols for exclusion
    existing_base = {h["ticker"].split(".")[0].upper() for h in holdings}

    log.info(f"[SKILL-A02] Fetching constituents for {len(sectors)} sectors ...")
    all_sectors = fetch_all_sector_constituents(sectors, config)

    # Build unique candidate list excluding existing holdings
    seen:       set  = set()
    candidates: list = []
    for sector, tickers in all_sectors.items():
        for ticker in tickers:
            base = ticker.split(".")[0].upper()
            if base not in existing_base and ticker not in seen:
                seen.add(ticker)
                candidates.append({"ticker": ticker, "sector": sector})

    log.info(f"[SKILL-A02] {len(candidates)} unique candidates to evaluate")

    # Score each candidate — no minimum score filter, show all scored stocks
    scored: list = []
    for c in candidates:
        result = evaluate_candidate(c["ticker"], config)
        if result is None:
            continue
        scored.append({
            "ticker":            c["ticker"],
            "sector":            c["sector"],
            "overall_score":     result["score"],
            "fundamental_grade": result["fundamental_grade"],
            "technical_grade":   result["technical_grade"],
            "valuation_grade":   result["valuation_grade"],
            "risk_grade":        result["risk_grade"],
            "sentiment_grade":   result["sentiment_grade"],
            "fundamental_score": result.get("fundamental_score", 50.0),
            "technical_score":   result.get("technical_score",   50.0),
            "valuation_score":   result.get("valuation_score",   50.0),
            "risk_score":        result.get("risk_score",        50.0),
            "sentiment_score":   result.get("sentiment_score",   50.0),
            "metrics":           result.get("metrics", {}),
            "fundamental_breakdown": result.get("fundamental_breakdown", {}),
            "technical_breakdown":   result.get("technical_breakdown", {}),
            "valuation_breakdown":   result.get("valuation_breakdown", {}),
            "risk_breakdown":        result.get("risk_breakdown", {}),
            "sentiment_breakdown":   result.get("sentiment_breakdown", {}),
            # Keep fields for backward compatibility with app.py detail view
            "peer_score":        result["score"],
            "action_tag":        "Initiate",
            "mode":              "new_idea",
            "rationale":         {},
        })

    # Sort by overall score descending — show all scored stocks
    scored.sort(key=lambda x: x["overall_score"], reverse=True)
    top_ideas = scored   # all scored stocks, no limit

    log.info(
        f"[SKILL-A02] {len(scored)} stocks scored and ranked | "
        f"Top scorer: {top_ideas[0]['ticker'] if top_ideas else 'none'}"
    )

    return {
        "new_ideas":           top_ideas,
        "total_evaluated":     len(scored),
        "total_candidates":    len(candidates),
        # Backward compatibility keys used by app.py and dashboard.py
        "ranked_candidates":   top_ideas,
        "top_recommendations": top_ideas[:5],
    }


# ── SKILL-A03: Evaluate a Single Candidate ───────────────────────────────────

def evaluate_candidate(
    ticker: str,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """
    SKILL-A03: Run the full scoring pipeline for a single candidate ticker.
    Claude AI sentiment is skipped — defaults to neutral 50.
    Returns dict with overall score + scorecard grades and numeric scores,
    or None on failure.
    """
    from src.layers.data.price_module import (
        fetch_historical_price_data,
        fetch_realtime_price_snapshot,
        fetch_index_and_sector_data,
    )
    from src.layers.data.fundamentals_module import (
        fetch_financial_statements, fetch_key_ratios,
    )
    from src.layers.data.shareholding_module import (
        fetch_shareholding_pattern, fetch_promoter_pledge_data,
    )
    from src.layers.intelligence.technical_module import (
        compute_moving_averages, compute_rsi, compute_macd,
        compute_beta, compute_52w_momentum, compute_volume_signal,
    )
    from src.layers.intelligence.fundamental_scoring_module import (
        compute_revenue_growth, compute_margin_trends,
        compute_free_cash_flow, compute_roic,
        compute_promoter_holding_signal, compute_earnings_surprise,
    )
    from src.layers.intelligence.valuation_scoring_module import (
        compute_peg_ratio, compute_pe_vs_sector, compute_ev_ebitda,
    )
    from src.layers.intelligence.sentiment_module import (
        compute_insider_activity_signal,
        compute_institutional_ownership_change,
    )
    from src.layers.intelligence.scorecard_aggregator import (
        compute_fundamental_score, compute_technical_score,
        compute_valuation_score, compute_risk_score,
        compute_sentiment_score, compute_overall_stock_score,
    )

    try:
        log.info(f"[SKILL-A03] Evaluating: {ticker}")

        price  = fetch_historical_price_data(ticker, period="2y", config=config)
        snap   = fetch_realtime_price_snapshot(ticker, config=config)
        index  = fetch_index_and_sector_data(config=config)
        stmts  = fetch_financial_statements(ticker, config=config)
        ratios = fetch_key_ratios(ticker, config=config)
        sh     = fetch_shareholding_pattern(ticker, config=config)
        pledge = fetch_promoter_pledge_data(ticker, config=config)

        df  = price["price_df"]
        cp  = snap.get("current_price") or 0
        idx = index["index_data"].get("^NSEI")

        if df.empty or not cp:
            return None

        ma   = compute_moving_averages(df)
        rsi  = compute_rsi(df)
        macd = compute_macd(df)
        beta = (
            compute_beta(df, idx)
            if idx is not None
            else {"beta": None, "beta_signal": "moderate"}
        )
        mom  = compute_52w_momentum(df, cp)
        vol  = compute_volume_signal(df)

        inc  = stmts["income_statement"]
        bal  = stmts["balance_sheet"]
        cf   = stmts["cash_flow"]

        rev  = compute_revenue_growth(inc, config)
        mar  = compute_margin_trends(inc, config)
        fcf  = compute_free_cash_flow(cf, inc, config)
        roic = compute_roic(inc, bal, config=config)
        prom = compute_promoter_holding_signal(
            sh["promoter_holding_pct"], sh["promoter_change_qoq"],
            pledge["pledge_pct"], config,
        )
        surp = compute_earnings_surprise([], [], config)

        peg    = compute_peg_ratio(ratios.get("pe_ratio"), rev["revenue_growth_yoy"], config)
        pe_sec = compute_pe_vs_sector(ratios.get("pe_ratio"), None, config)
        evebit = compute_ev_ebitda(ratios.get("ev_ebitda"), None, config)

        insider = compute_insider_activity_signal([])
        inst    = compute_institutional_ownership_change(
            sh["fii_change_qoq"], sh["dii_change_qoq"]
        )

        f_score = compute_fundamental_score(
            rev["revenue_signal"], mar["margin_signal"],
            fcf["fcf_signal"],    roic["roic_signal"],
            prom["promoter_signal"], surp["surprise_signal"], config,
        )
        t_score = compute_technical_score(
            ma["trend_signal"],  rsi["rsi_signal"],
            macd["macd_signal"], mom["momentum_score"],
            vol["volume_signal"], config,
        )
        v_score = compute_valuation_score(
            peg["peg_signal"], pe_sec["pe_vs_sector_signal"],
            evebit["ev_ebitda_signal"], config,
        )
        r_score = compute_risk_score(
            beta["beta"], None, None,
            ratios.get("debt_to_equity"), pledge["pledge_pct"], config,
        )
        s_score = compute_sentiment_score(
            50.0, insider["insider_signal"],
            inst["institutional_signal"],
            ratios.get("analyst_recommendation"), config,
        )
        overall = compute_overall_stock_score(
            f_score["fundamental_score"], t_score["technical_score"],
            v_score["valuation_score"],   r_score["risk_score"],
            s_score["sentiment_scorecard_score"], config,
        )

        log.info(f"[SKILL-A03] {ticker}: score={overall['overall_score']:.1f}")

        return {
            "score":             overall["overall_score"],
            "fundamental_grade": f_score["fundamental_grade"],
            "technical_grade":   t_score["technical_grade"],
            "valuation_grade":   v_score["valuation_grade"],
            "risk_grade":        r_score["risk_grade"],
            "sentiment_grade":   s_score["sentiment_grade"],
            # Numeric scores for display
            "fundamental_score": f_score["fundamental_score"],
            "technical_score":   t_score["technical_score"],
            "valuation_score":   v_score["valuation_score"],
            "risk_score":        r_score["risk_score"],
            "sentiment_score":   s_score["sentiment_scorecard_score"],
            # Breakdowns for signal column in stock detail view
            "fundamental_breakdown": f_score.get("fundamental_breakdown", {}),
            "technical_breakdown":   t_score.get("technical_breakdown", {}),
            "valuation_breakdown":   v_score.get("valuation_breakdown", {}),
            "risk_breakdown":        r_score.get("risk_breakdown", {}),
            "sentiment_breakdown":   s_score.get("sentiment_breakdown", {}),
            # Raw metrics for stock detail view
            "metrics": {
                "current_price":      cp,
                "revenue_growth_yoy": rev["revenue_growth_yoy"],
                "net_margin":         mar["net_margin"],
                "margin_trend":       mar["margin_trend"],
                "fcf":                fcf["fcf"],
                "roic":               roic["roic"],
                "pe_ratio":           ratios.get("pe_ratio"),
                "peg_ratio":          peg["peg_ratio"],
                "ev_ebitda":          evebit["ev_ebitda_value"],
                "beta":               beta["beta"],
                "rsi":                rsi["rsi_value"],
                "sma50":              ma["sma_50"],
                "sma200":             ma["sma_200"],
                "trend":              ma["trend_signal"],
                "momentum_score":     mom["momentum_score"],
                "promoter_holding":   sh["promoter_holding_pct"],
                "fii_holding":        sh["fii_holding_pct"],
                "sentiment_score":    50.0,
                "sentiment_label":    "neutral",
                "positive_themes":    [],
                "negative_themes":    [],
                "analyst_rec":        ratios.get("analyst_recommendation"),
                "analyst_rec_firm":   None,
                "analyst_rec_source": None,
                "analyst_rec_note":   None,
                "analyst_target":     ratios.get("analyst_target_price"),
                "analyst_target_source": None,
                "analyst_target_note":   None,
                "analyst_target_mean":   ratios.get("analyst_target_price"),
                "analyst_target_low":    ratios.get("analyst_target_low"),
                "analyst_target_high":   ratios.get("analyst_target_high"),
                "analyst_all_ratings":   [],
            },
        }

    except Exception as e:
        log.warning(f"[SKILL-A03] Evaluation failed for {ticker}: {e}")
        return None


# ── SKILL-A04: Rank candidates (kept for backward compatibility) ──────────────

def rank_discovery_candidates(
    gap_fill_candidates: list[dict],
    peer_candidates: list[dict],
    g1_results: dict,
    config: dict | None = None,
) -> dict[str, Any]:
    """Legacy wrapper — new discovery uses screen_new_ideas() directly."""
    log.debug("[SKILL-A04] rank_discovery_candidates called — legacy path")
    all_c = gap_fill_candidates + peer_candidates
    all_c.sort(key=lambda c: c.get("peer_score", 0), reverse=True)
    return {"ranked_candidates": all_c, "top_recommendations": all_c[:5]}


def tag_peer_recommendation(
    peer_score: float,
    avg_holding_score: float,
    switch_gap: float,
    distribute_gap: float,
) -> str:
    """Legacy helper — retained for backward compatibility."""
    gap = peer_score - avg_holding_score
    if gap >= switch_gap:     return "Switch"
    if gap >= distribute_gap: return "Distribute"
    return "Hold"