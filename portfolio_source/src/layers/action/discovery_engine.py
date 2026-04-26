"""
discovery_engine.py
Layer      : Action
Owns       : SKILL-A02, SKILL-A03, SKILL-A04
Description: G2 focused discovery using two complementary modes:
             Mode 1 — Gap Fill: Best stocks in underweight sectors
             Mode 2 — Peer Compare: Better performers in existing sectors
             Each candidate includes a plain-English rationale.
"""

from __future__ import annotations
import re
import time
from typing import Any

import pandas as pd

from src.utils.logger import get_logger

log = get_logger(__name__)


# ── Sector Constituents ───────────────────────────────────────────────────────

def _get_sector_constituents(
    index_ticker: str,
    existing_tickers: list[str],
    config: dict | None = None,
) -> list[str]:
    """Top 3 stocks per Nifty sector index — excluding existing holdings."""
    SECTOR_STOCKS = {
        "^CNXIT":     ["TCS.NS",       "INFY.NS",      "HCLTECH.NS"],
        "^NSEBANK":   ["HDFCBANK.NS",  "ICICIBANK.NS", "KOTAKBANK.NS"],
        "^CNXPHARMA": ["SUNPHARMA.NS", "DRREDDY.NS",   "CIPLA.NS"],
        "^CNXFMCG":   ["HINDUNILVR.NS","ITC.NS",       "NESTLEIND.NS"],
        "^CNXAUTO":   ["MARUTI.NS",    "TATAMOTORS.NS","M&M.NS"],
        "^CNXENERGY": ["RELIANCE.NS",  "ONGC.NS",      "NTPC.NS"],
        "^CNXMETAL":  ["TATASTEEL.NS", "JSWSTEEL.NS",  "HINDALCO.NS"],
        "^CNXINFRA":  ["LT.NS",        "ADANIPORTS.NS","ULTRACEMCO.NS"],
        "^CNXREALTY": ["DLF.NS",       "GODREJPROP.NS","OBEROIRLTY.NS"],
    }
    candidates   = SECTOR_STOCKS.get(index_ticker, [])
    existing_base= [t.split(".")[0].upper() for t in existing_tickers]
    return [
        t for t in candidates
        if t.split(".")[0].upper() not in existing_base
    ]


# ── SKILL-A02: Mode 1 — Gap Fill ─────────────────────────────────────────────

def screen_gap_fill_candidates(
    sector_drift: dict[str, float],
    existing_tickers: list[str],
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-A02: Mode 1 — Gap Fill Discovery.
    Finds best stocks in sectors where portfolio is underweight.
    """
    goals         = (config or {}).get("goals", {})
    sector_idx_map= goals.get("sector_index_map", {})
    drift_thresh  = goals.get("rebalancing_drift_threshold", 5)

    underweight = {
        sector: abs(drift)
        for sector, drift in sector_drift.items()
        if drift < -drift_thresh
    }

    if not underweight:
        log.info("[SKILL-A02] No significantly underweight sectors found")
        return {"gap_fill_candidates": [], "underweight_sectors": []}

    log.info(
        f"[SKILL-A02] Underweight sectors: "
        f"{[f'{s}({d:.1f}%)' for s, d in underweight.items()]}"
    )

    candidates = []
    for sector, gap_size in underweight.items():
        index_ticker = sector_idx_map.get(sector)
        if not index_ticker:
            continue
        tickers = _get_sector_constituents(index_ticker, existing_tickers, config)
        for ticker in tickers:
            candidates.append({
                "ticker":       ticker,
                "sector":       sector,
                "mode":         "gap_fill",
                "gap_size_pct": round(gap_size, 2),
                "source_index": index_ticker,
                "action_tag":   "Initiate",
            })

    log.info(f"[SKILL-A02] {len(candidates)} gap-fill candidates identified")
    return {
        "gap_fill_candidates": candidates,
        "underweight_sectors": list(underweight.keys()),
    }


# ── SKILL-A03: Mode 2 — Peer Compare ─────────────────────────────────────────

def screen_peer_compare_candidates(
    holdings: list[dict],
    g1_results: dict,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-A03: Mode 2 — Peer Comparison Discovery.
    Finds peers in existing sectors and tags Switch/Distribute/Hold.
    """
    goals          = (config or {}).get("goals", {})
    sector_idx_map = goals.get("sector_index_map", {})
    switch_gap     = goals.get("g2_switch_score_gap",     15)
    distribute_gap = goals.get("g2_distribute_score_gap",  5)

    existing_tickers = [h["ticker"] for h in holdings]

    sector_holdings: dict[str, list[dict]] = {}
    for h in holdings:
        sector = h.get("sector", "Others")
        sector_holdings.setdefault(sector, []).append(h)

    candidates = []
    for sector, sector_stocks in sector_holdings.items():
        index_ticker = sector_idx_map.get(sector)
        if not index_ticker:
            continue

        holding_scores = []
        holding_tickers= []
        for h in sector_stocks:
            ticker = h["ticker"]
            score  = g1_results.get(ticker, {}).get("overall_score")
            if score is not None:
                holding_scores.append(score)
                holding_tickers.append(ticker)

        if not holding_scores:
            continue

        avg_holding_score = sum(holding_scores) / len(holding_scores)
        peers = _get_sector_constituents(index_ticker, existing_tickers, config)

        for peer_ticker in peers:
            candidates.append({
                "ticker":              peer_ticker,
                "sector":              sector,
                "mode":                "peer_compare",
                "avg_holding_score":   round(avg_holding_score, 2),
                "holding_tickers":     holding_tickers,
                "source_index":        index_ticker,
                "switch_gap":          switch_gap,
                "distribute_gap":      distribute_gap,
                "peer_score":          None,
                "score_gap":           None,
                "action_tag":          "Pending",
            })

    log.info(f"[SKILL-A03] {len(candidates)} peer candidates to evaluate")
    return {"peer_candidates": candidates}


def tag_peer_recommendation(
    peer_score: float,
    avg_holding_score: float,
    switch_gap: float,
    distribute_gap: float,
) -> str:
    """Assign Switch / Distribute / Hold based on score gap."""
    gap = peer_score - avg_holding_score
    if gap >= switch_gap:    return "Switch"
    if gap >= distribute_gap: return "Distribute"
    return "Hold"


# ── SKILL-A04: Rank Discovery Candidates ─────────────────────────────────────

def rank_discovery_candidates(
    gap_fill_candidates: list[dict],
    peer_candidates: list[dict],
    g1_results: dict,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-A04: Merge, filter, rank and generate rationale for all candidates.
    """
    goals     = (config or {}).get("goals", {})
    min_score = goals.get("g2_min_candidate_score", 45)

    all_candidates = gap_fill_candidates + peer_candidates

    scored = [
        c for c in all_candidates
        if c.get("peer_score") is not None
        and c.get("peer_score", 0) >= min_score
        and c.get("action_tag") != "Hold"
    ]

    scored.sort(
        key=lambda c: (c.get("peer_score", 0), c.get("gap_size_pct", 0)),
        reverse=True,
    )

    # Deduplicate
    seen   = set()
    unique = []
    for c in scored:
        if c["ticker"] not in seen:
            seen.add(c["ticker"])
            # Generate rationale for each unique candidate
            c["rationale"] = _build_rationale(c, g1_results, config)
            unique.append(c)

    top_5 = unique[:5]
    log.info(
        f"[SKILL-A04] {len(unique)} ranked candidates | "
        f"Top 5: {[c['ticker'] for c in top_5]}"
    )
    return {"ranked_candidates": unique, "top_recommendations": top_5}


# ── Rationale Builder ─────────────────────────────────────────────────────────

def _build_rationale(
    candidate: dict,
    g1_results: dict,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    Generate a plain-English rationale for a G2 candidate.
    Returns a structured dict with summary, strengths, risks and action.
    """
    ticker     = candidate.get("ticker", "")
    company    = ticker.split(".")[0]
    sector     = candidate.get("sector", "")
    score      = candidate.get("peer_score", 0)
    action_tag = candidate.get("action_tag", "Initiate")
    mode       = candidate.get("mode", "gap_fill")

    # Scorecard grades from evaluation
    f_grade = candidate.get("fundamental_grade", "Moderate")
    t_grade = candidate.get("technical_grade",   "Neutral")
    v_grade = candidate.get("valuation_grade",   "Fair")
    r_grade = candidate.get("risk_grade",        "Moderate")
    s_grade = candidate.get("sentiment_grade",   "Mixed")

    # Build strengths (green/bullish/undervalued/low grades)
    strengths = []
    if f_grade == "Strong":
        strengths.append("Strong fundamentals — healthy revenue, margins and cash flow")
    if t_grade == "Bullish":
        strengths.append("Bullish technical trend — price above key moving averages")
    if v_grade == "Undervalued":
        strengths.append("Attractive valuation — trading below sector median")
    if r_grade == "Low":
        strengths.append("Low risk profile — low beta and comfortable stop-loss distance")
    if s_grade == "Positive":
        strengths.append("Positive market sentiment and analyst coverage")

    # Build risks (weak/bearish/overvalued/high grades)
    risks = []
    if f_grade == "Weak":
        risks.append("Weak fundamentals — revenue or profitability concerns")
    if t_grade == "Bearish":
        risks.append("Bearish technical trend — price below 200-day moving average")
    if v_grade == "Overvalued":
        risks.append("Stretched valuation — trading at a premium to sector peers")
    if r_grade == "High":
        risks.append("Elevated risk — high beta or concentrated position risk")
    if s_grade == "Negative":
        risks.append("Negative news sentiment detected")

    # Defaults if nothing flagged
    if not strengths:
        strengths.append(f"Overall score of {score:.1f}/100 — meets minimum quality threshold")
    if not risks:
        risks.append("No major risk flags — monitor standard market risks")

    # Build summary and action based on tag
    goals        = (config or {}).get("goals", {})
    target_alloc = goals.get("target_sector_allocation", {})
    target_pct   = target_alloc.get(sector, 0)

    if action_tag == "Initiate":
        gap_pct = candidate.get("gap_size_pct", 0)
        summary = (
            f"{company} scores {score:.1f}/100 — recommended to initiate a position "
            f"to fill a {gap_pct:.1f}% gap in the {sector} sector."
        )
        action = (
            f"Open a new position in {company}. "
            f"Target allocation: {target_pct}% of portfolio."
        )

    elif action_tag == "Switch":
        avg   = candidate.get("avg_holding_score", 0)
        gap   = candidate.get("score_gap", 0)
        held  = ", ".join(candidate.get("holding_tickers", []))
        summary = (
            f"{company} scores {score:.1f}/100 — {gap:.1f} points higher than "
            f"your existing {sector} holding ({held} at {avg:.1f}/100). "
            f"A switch is recommended."
        )
        action = (
            f"Consider selling {held} and initiating a position in {company} "
            f"within the {sector} sector."
        )

    else:  # Distribute
        avg  = candidate.get("avg_holding_score", 0)
        gap  = candidate.get("score_gap", 0)
        held = ", ".join(candidate.get("holding_tickers", []))
        summary = (
            f"{company} scores {score:.1f}/100 — {gap:.1f} points above "
            f"your existing {sector} holding ({held} at {avg:.1f}/100). "
            f"The gap is not large enough to recommend a full switch."
        )
        action = (
            f"Consider distributing your {sector} allocation across both "
            f"{held} and {company} to improve sector diversification."
        )

    return {
        "summary":    summary,
        "strengths":  strengths,
        "risks":      risks,
        "action":     action,
        "score":      score,
        "action_tag": action_tag,
    }


# ── Evaluate a Single Candidate ───────────────────────────────────────────────

def evaluate_candidate(
    ticker: str,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """
    Run the full scoring pipeline for a single candidate.
    Returns a dict with score + scorecard grades, or None on failure.
    Claude AI sentiment skipped — defaults to neutral 50.
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
        beta = compute_beta(df, idx) if idx is not None else {"beta": None, "beta_signal": "moderate"}
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

        # Return score + grades for rationale generation
        return {
            "score":              overall["overall_score"],
            "fundamental_grade":  f_score["fundamental_grade"],
            "technical_grade":    t_score["technical_grade"],
            "valuation_grade":    v_score["valuation_grade"],
            "risk_grade":         r_score["risk_grade"],
            "sentiment_grade":    s_score["sentiment_grade"],
        }

    except Exception as e:
        log.warning(f"[SKILL-A03] Evaluation failed for {ticker}: {e}")
        return None