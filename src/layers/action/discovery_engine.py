"""
discovery_engine.py
Layer      : Action
Owns       : SKILL-A02, SKILL-A03, SKILL-A04
Description: G2 discovery -- three complementary modes:
  Mode A: Gap Fill   -- best stocks in underweight sectors
  Mode B: Peer Compare -- better alternatives to weakest existing holdings
  Mode C: Diversifier  -- high scorers with low correlation to portfolio

  Two-stage evaluation:
  Stage 1: Score all candidates on F, T, V, R (no Claude AI)
  Stage 2: Fetch news + Claude AI sentiment for top 10 per mode, re-rank
  Final: Top 5 per mode shown with colour-coded signal
"""

from __future__ import annotations
from typing import Any

import numpy as np
import pandas as pd

from src.utils.logger import get_logger

log = get_logger(__name__)

# Colour signal thresholds
SIGNAL_STRONG  = 75
SIGNAL_GOOD    = 60
SIGNAL_MONITOR = 45

# Mode labels
MODE_A = "Gap Fill"
MODE_B = "Peer Compare"
MODE_C = "Diversifier"


def _signal_label(score: float) -> str:
    if score >= SIGNAL_STRONG:  return "Strong Opportunity"
    if score >= SIGNAL_GOOD:    return "Good Opportunity"
    if score >= SIGNAL_MONITOR: return "Monitor"
    return "Caution"


def _signal_colour(score: float) -> str:
    if score >= SIGNAL_STRONG:  return "green"
    if score >= SIGNAL_GOOD:    return "blue"
    if score >= SIGNAL_MONITOR: return "amber"
    return "red"


# -- SKILL-A02: Screen New Investment Ideas ------------------------------------

def screen_new_ideas(
    holdings: list[dict],
    g1_results: dict,
    price_data: dict,
    sector_drift: dict,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-A02: Screen New Investment Ideas across three complementary modes.
    Two-stage evaluation: Stage 1 scores all on F/T/V/R, Stage 2 adds
    sentiment via Claude AI for top 10 per mode, then re-ranks to top 5.
    """
    from src.layers.data.sector_universe_module import fetch_all_sector_constituents

    goals          = (config or {}).get("goals", {})
    drift_threshold= float(goals.get("rebalancing_drift_threshold", 5))
    switch_gap     = float(goals.get("g2_switch_score_gap", 15))
    distribute_gap = float(goals.get("g2_distribute_score_gap", 5))

    # Sectors with non-zero target allocation
    sectors = [
        s for s, w in goals.get("target_sector_allocation", {}).items()
        if w > 0
    ]

    # Existing holdings lookup
    existing_base = {h["ticker"].split(".")[0].upper() for h in holdings}

    # Fetch all sector constituents with company names
    log.info(f"[SKILL-A02] Fetching constituents for {len(sectors)} sectors ...")
    all_sectors = fetch_all_sector_constituents(sectors, config)

    # Build full unique candidate pool (excluding existing holdings)
    all_candidates: list[dict] = []
    seen: set = set()
    for sector, constituents in all_sectors.items():
        for c in constituents:
            ticker = c["ticker"]
            base   = ticker.split(".")[0].upper()
            if base not in existing_base and ticker not in seen:
                seen.add(ticker)
                all_candidates.append({
                    "ticker":       ticker,
                    "company_name": c["company_name"],
                    "sector":       sector,
                })

    log.info(f"[SKILL-A02] {len(all_candidates)} unique candidates to evaluate in Stage 1")

    # ---- Stage 1: Score all candidates on F, T, V, R -------------------------
    stage1_scores: dict[str, dict] = {}
    for c in all_candidates:
        result = _evaluate_stage1(c["ticker"], config)
        if result:
            stage1_scores[c["ticker"]] = result

    log.info(f"[SKILL-A02] Stage 1 complete: {len(stage1_scores)} candidates scored")

    # ---- Mode A: Gap Fill ----------------------------------------------------
    mode_a = _mode_a_gap_fill(
        all_candidates, stage1_scores, sector_drift,
        drift_threshold, config
    )

    # ---- Mode B: Peer Compare ------------------------------------------------
    mode_b = _mode_b_peer_compare(
        all_candidates, stage1_scores, holdings,
        g1_results, switch_gap, distribute_gap, config
    )

    # ---- Mode C: Diversifier -------------------------------------------------
    mode_c = _mode_c_diversifier(
        all_candidates, stage1_scores, price_data, config
    )

    # ---- Stage 2: Sentiment enrichment for top 10 per mode -------------------
    log.info("[SKILL-A02] Stage 2: Sentiment enrichment for top candidates ...")

    mode_a_final = _stage2_enrich(mode_a[:10], all_candidates, config)[:5]
    mode_b_final = _stage2_enrich(mode_b[:10], all_candidates, config)[:5]
    mode_c_final = _stage2_enrich(mode_c[:10], all_candidates, config)[:5]

    # Add mode labels and signal colours
    for c in mode_a_final:
        c["mode"] = MODE_A
        c["action_tag"] = "Initiate"
        c["signal"] = _signal_label(c["final_score"])
        c["signal_colour"] = _signal_colour(c["final_score"])

    for c in mode_b_final:
        c["mode"] = MODE_B
        c["signal"] = _signal_label(c["final_score"])
        c["signal_colour"] = _signal_colour(c["final_score"])

    for c in mode_c_final:
        c["mode"] = MODE_C
        c["action_tag"] = "Initiate"
        c["signal"] = _signal_label(c["final_score"])
        c["signal_colour"] = _signal_colour(c["final_score"])

    all_ideas = mode_a_final + mode_b_final + mode_c_final

    log.info(
        f"[SKILL-A02] Final: Mode A={len(mode_a_final)} | "
        f"Mode B={len(mode_b_final)} | Mode C={len(mode_c_final)}"
    )

    return {
        "mode_a":          mode_a_final,
        "mode_b":          mode_b_final,
        "mode_c":          mode_c_final,
        "new_ideas":       all_ideas,
        "ranked_candidates": all_ideas,
        "top_recommendations": all_ideas[:5],
        "total_candidates":  len(all_candidates),
        "total_evaluated":   len(stage1_scores),
    }


# -- Mode A: Gap Fill ----------------------------------------------------------

def _mode_a_gap_fill(
    all_candidates: list[dict],
    stage1_scores: dict,
    sector_drift: dict,
    drift_threshold: float,
    config: dict | None = None,
) -> list[dict]:
    """
    Mode A: Best stocks in underweight sectors.
    Underweight = current allocation < target by more than drift_threshold.
    """
    underweight_sectors = {
        s for s, d in sector_drift.items()
        if d < -drift_threshold
    }

    if not underweight_sectors:
        log.info("[Mode A] No underweight sectors found")
        return []

    log.info(f"[Mode A] Underweight sectors: {underweight_sectors}")

    candidates = []
    for c in all_candidates:
        if c["sector"] not in underweight_sectors:
            continue
        ticker = c["ticker"]
        if ticker not in stage1_scores:
            continue
        entry = {**c, **stage1_scores[ticker]}
        entry["gap_size_pct"] = abs(sector_drift.get(c["sector"], 0))
        candidates.append(entry)

    # Sort by stage1 score descending
    candidates.sort(key=lambda x: x.get("stage1_score", 0), reverse=True)
    log.info(f"[Mode A] {len(candidates)} gap fill candidates")
    return candidates


# -- Mode B: Peer Compare ------------------------------------------------------

def _mode_b_peer_compare(
    all_candidates: list[dict],
    stage1_scores: dict,
    holdings: list[dict],
    g1_results: dict,
    switch_gap: float,
    distribute_gap: float,
    config: dict | None = None,
) -> list[dict]:
    """
    Mode B: Better alternatives to existing holdings by sector.
    Compares peer Stage 1 score vs existing holding overall score.
    """
    # Build sector -> avg holding score map
    sector_holding_scores: dict[str, list] = {}
    sector_holding_tickers: dict[str, list] = {}
    for h in holdings:
        sector = h.get("sector", "Others")
        ticker = h["ticker"]
        score  = g1_results.get(ticker, {}).get("overall_score")
        if score is not None:
            sector_holding_scores.setdefault(sector, []).append(score)
            sector_holding_tickers.setdefault(sector, []).append(ticker)

    candidates = []
    for c in all_candidates:
        sector = c["sector"]
        ticker = c["ticker"]
        if sector not in sector_holding_scores:
            continue
        if ticker not in stage1_scores:
            continue

        avg_holding_score = sum(sector_holding_scores[sector]) / len(sector_holding_scores[sector])
        peer_score        = stage1_scores[ticker]["stage1_score"]
        score_gap         = peer_score - avg_holding_score

        if score_gap >= switch_gap:
            action_tag = "Switch"
        elif score_gap >= distribute_gap:
            action_tag = "Distribute"
        else:
            continue   # holding is better -- skip

        entry = {**c, **stage1_scores[ticker]}
        entry["action_tag"]        = action_tag
        entry["score_gap"]         = round(score_gap, 2)
        entry["avg_holding_score"] = round(avg_holding_score, 2)
        entry["holding_tickers"]   = sector_holding_tickers.get(sector, [])
        candidates.append(entry)

    # Sort by score gap descending
    candidates.sort(key=lambda x: x.get("score_gap", 0), reverse=True)
    log.info(f"[Mode B] {len(candidates)} peer compare candidates")
    return candidates


# -- Mode C: Diversifier -------------------------------------------------------

def _mode_c_diversifier(
    all_candidates: list[dict],
    stage1_scores: dict,
    existing_price_data: dict,
    config: dict | None = None,
) -> list[dict]:
    """
    Mode C: High-scoring stocks with low correlation to existing portfolio.
    Threshold: Stage 1 score > 65 AND max correlation < 0.7 with all holdings.
    """
    high_scorers = [
        c for c in all_candidates
        if c["ticker"] in stage1_scores
        and stage1_scores[c["ticker"]]["stage1_score"] >= 65
    ]

    if not existing_price_data:
        log.info("[Mode C] No existing price data for correlation -- skipping")
        return []

    # Compute existing holding daily returns
    existing_returns: dict[str, pd.Series] = {}
    for ticker, df in existing_price_data.items():
        if "Close" in df.columns and len(df) >= 30:
            existing_returns[ticker] = df["Close"].pct_change().dropna()

    if not existing_returns:
        return []

    candidates = []
    for c in high_scorers:
        ticker = c["ticker"]
        # Fetch price data for this candidate
        try:
            from src.layers.data.price_module import fetch_historical_price_data
            pr = fetch_historical_price_data(ticker, period="1y", config=config)
            df = pr.get("price_df")
            if df is None or df.empty or "Close" not in df.columns:
                continue
            cand_returns = df["Close"].pct_change().dropna()

            # Check max correlation with all existing holdings
            max_corr = 0.0
            for _, hold_returns in existing_returns.items():
                common = cand_returns.index.intersection(hold_returns.index)
                if len(common) < 30:
                    continue
                corr = float(
                    np.corrcoef(
                        cand_returns.loc[common].values,
                        hold_returns.loc[common].values
                    )[0, 1]
                )
                if abs(corr) > max_corr:
                    max_corr = abs(corr)

            if max_corr >= 0.7:
                continue   # too correlated -- skip

            entry = {**c, **stage1_scores[ticker]}
            entry["max_correlation"] = round(max_corr, 4)
            candidates.append(entry)

        except Exception as e:
            log.debug(f"[Mode C] Correlation check failed for {ticker}: {e}")
            continue

    # Sort by stage1 score descending
    candidates.sort(key=lambda x: x.get("stage1_score", 0), reverse=True)
    log.info(f"[Mode C] {len(candidates)} diversifier candidates (correlation < 0.7)")
    return candidates


# -- Stage 1: Score on F, T, V, R only ----------------------------------------

def _evaluate_stage1(
    ticker: str,
    config: dict | None = None,
) -> dict | None:
    """
    Stage 1 evaluation: F, T, V, R scoring only. No Claude AI sentiment.
    Returns dict with stage1_score, individual scores, grades, breakdowns.
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
    from src.layers.intelligence.scorecard_aggregator import (
        compute_fundamental_score, compute_technical_score,
        compute_valuation_score, compute_risk_score,
    )

    try:
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

        f_score = compute_fundamental_score(
            rev["revenue_signal"], mar["margin_signal"],
            fcf["fcf_signal"], roic["roic_signal"],
            prom["promoter_signal"], surp["surprise_signal"], config,
        )
        t_score = compute_technical_score(
            ma["trend_signal"], rsi["rsi_signal"],
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

        # Stage 1 score: F(30%) + T(20%) + V(25%) + R(10%) -- no S yet
        # Normalise weights to sum to 1 without S
        stage1 = round(
            f_score["fundamental_score"] * (0.30 / 0.85) +
            t_score["technical_score"]   * (0.20 / 0.85) +
            v_score["valuation_score"]   * (0.25 / 0.85) +
            r_score["risk_score"]        * (0.10 / 0.85),
            4
        )

        return {
            "stage1_score":      stage1,
            "fundamental_score": f_score["fundamental_score"],
            "technical_score":   t_score["technical_score"],
            "valuation_score":   v_score["valuation_score"],
            "risk_score":        r_score["risk_score"],
            "sentiment_score":   50.0,   # default until Stage 2
            "fundamental_grade": f_score["fundamental_grade"],
            "technical_grade":   t_score["technical_grade"],
            "valuation_grade":   v_score["valuation_grade"],
            "risk_grade":        r_score["risk_grade"],
            "sentiment_grade":   "Mixed",
            "fundamental_breakdown": f_score.get("fundamental_breakdown", {}),
            "technical_breakdown":   t_score.get("technical_breakdown", {}),
            "valuation_breakdown":   v_score.get("valuation_breakdown", {}),
            "risk_breakdown":        r_score.get("risk_breakdown", {}),
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
                # Raw signals for reason builder
                "revenue_signal":  rev["revenue_signal"],
                "fcf_signal":      fcf["fcf_signal"],
                "roic_signal":     roic["roic_signal"],
                "promoter_signal": prom["promoter_signal"],
            },
        }

    except Exception as e:
        log.debug(f"[Stage 1] Failed for {ticker}: {e}")
        return None


# -- Stage 2: Sentiment Enrichment ---------------------------------------------

def _stage2_enrich(
    candidates: list[dict],
    all_candidates: list[dict],
    config: dict | None = None,
) -> list[dict]:
    """
    Stage 2: Fetch news + Claude AI sentiment for top candidates.
    Recalculates final score = F(30%) + T(20%) + V(25%) + R(10%) + S(15%).
    Re-ranks by final score descending.
    """
    from src.layers.data.news_module import fetch_rss_news_feeds
    from src.layers.intelligence.sentiment_module import (
        score_news_sentiment,
        compute_insider_activity_signal,
        compute_institutional_ownership_change,
    )
    from src.layers.intelligence.scorecard_aggregator import compute_sentiment_score
    from src.layers.action.orchestrator import (
        _build_fundamental_driver,
        _build_sentiment_driver,
    )
    from src.layers.configuration.config_manager import is_skill_enabled

    # Build company name lookup
    name_lookup = {c["ticker"]: c["company_name"] for c in all_candidates}

    enriched = []
    for c in candidates:
        ticker       = c.get("ticker", "")
        company_name = name_lookup.get(ticker, ticker.split(".")[0])
        metrics      = c.get("metrics", {})

        try:
            # Fetch news
            news = fetch_rss_news_feeds(company_name, ticker, config=config)
            headlines = news.get("headlines", [])

            # Claude AI sentiment (if enabled)
            sentiment_result = score_news_sentiment(
                headlines, company_name, ticker, config
            )

            # Compute sentiment scorecard score
            insider = compute_insider_activity_signal([])
            inst    = compute_institutional_ownership_change(None, None)
            s_score = compute_sentiment_score(
                sentiment_result["sentiment_score"],
                insider["insider_signal"],
                inst["institutional_signal"],
                metrics.get("analyst_rec"),
                config,
            )

            sentiment_scorecard = s_score["sentiment_scorecard_score"]

            # Recalculate final score with S
            final_score = round(
                c.get("fundamental_score", 50) * 0.30 +
                c.get("technical_score",   50) * 0.20 +
                c.get("valuation_score",   50) * 0.25 +
                c.get("risk_score",        50) * 0.10 +
                sentiment_scorecard            * 0.15,
                4
            )

            # Update sentiment fields
            updated = dict(c)
            updated["sentiment_score"]   = sentiment_scorecard
            updated["sentiment_grade"]   = s_score["sentiment_grade"]
            updated["sentiment_breakdown"] = s_score.get("sentiment_breakdown", {})
            updated["final_score"]       = final_score
            updated["overall_score"]     = final_score
            updated["peer_score"]        = final_score

            # Update metrics with real sentiment data
            updated_metrics = dict(metrics)
            updated_metrics.update({
                "sentiment_score":   sentiment_result["sentiment_score"],
                "sentiment_label":   sentiment_result["sentiment_label"],
                "positive_themes":   sentiment_result.get("key_positive_themes", []),
                "negative_themes":   sentiment_result.get("key_negative_themes", []),
            })
            updated["metrics"] = updated_metrics

            # Build enriched reason
            fund_signals = {
                "revenue_signal":  metrics.get("revenue_signal", "amber"),
                "margin_trend":    metrics.get("margin_trend", "stable"),
                "fcf_signal":      metrics.get("fcf_signal", "amber"),
                "roic_signal":     metrics.get("roic_signal", "amber"),
                "promoter_signal": metrics.get("promoter_signal", "amber"),
            }
            sent_data = {
                "sentiment_score":  sentiment_result["sentiment_score"],
                "sentiment_label":  sentiment_result["sentiment_label"],
                "positive_themes":  sentiment_result.get("key_positive_themes", []),
                "negative_themes":  sentiment_result.get("key_negative_themes", []),
                "analyst_rec":      metrics.get("analyst_rec"),
                "analyst_target":   metrics.get("analyst_target"),
            }

            fund_driver      = _build_fundamental_driver(fund_signals)
            sentiment_driver = _build_sentiment_driver(sent_data, metrics.get("current_price"))

            mode     = c.get("mode", "")
            action   = c.get("action_tag", "Initiate")
            gap      = c.get("score_gap", 0)
            gap_size = c.get("gap_size_pct", 0)
            max_corr = c.get("max_correlation")

            if mode == MODE_A:
                core = (
                    f"{c.get('sector')} sector is underweight by {gap_size:.1f}%. "
                    f"Score {final_score:.1f}/100 -- recommend initiating a position."
                )
            elif mode == MODE_B:
                held = ", ".join(
                    t.replace(".NS", "") for t in c.get("holding_tickers", [])
                )
                core = (
                    f"Scores {gap:.1f} points above your current {c.get('sector')} "
                    f"holding ({held}) at {c.get('avg_holding_score', 0):.1f}/100. "
                    f"Action: {action}."
                )
            else:  # Mode C
                core = (
                    f"High scorer ({final_score:.1f}/100) with low portfolio "
                    f"correlation ({max_corr:.2f}). Good diversification opportunity."
                    if max_corr is not None
                    else f"High scorer ({final_score:.1f}/100) -- diversification opportunity."
                )

            reason_parts = [core]
            if fund_driver:
                reason_parts.append(f"Fundamentals: {fund_driver}")
            if sentiment_driver:
                reason_parts.append(f"Market view: {sentiment_driver}")
            updated["reason"] = " | ".join(reason_parts)

            enriched.append(updated)

        except Exception as e:
            log.warning(f"[Stage 2] Enrichment failed for {ticker}: {e}")
            # Fall back to stage1 score
            c["final_score"]  = c.get("stage1_score", 50)
            c["overall_score"]= c["final_score"]
            c["peer_score"]   = c["final_score"]
            c["reason"]       = f"Score {c['final_score']:.1f}/100. Sentiment data unavailable."
            enriched.append(c)

    # Re-rank by final score
    enriched.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    return enriched


# -- SKILL-A03: Evaluate a Single Candidate (legacy) ---------------------------

def evaluate_candidate(
    ticker: str,
    config: dict | None = None,
) -> dict[str, Any] | None:
    """Legacy wrapper -- calls Stage 1 evaluation."""
    result = _evaluate_stage1(ticker, config)
    if result:
        result["score"] = result["stage1_score"]
    return result


# -- Legacy stubs --------------------------------------------------------------

def rank_discovery_candidates(
    gap_fill_candidates: list[dict],
    peer_candidates: list[dict],
    g1_results: dict,
    config: dict | None = None,
) -> dict[str, Any]:
    all_c = gap_fill_candidates + peer_candidates
    all_c.sort(key=lambda c: c.get("peer_score", 0), reverse=True)
    return {"ranked_candidates": all_c, "top_recommendations": all_c[:5]}


def tag_peer_recommendation(
    peer_score: float,
    avg_holding_score: float,
    switch_gap: float,
    distribute_gap: float,
) -> str:
    gap = peer_score - avg_holding_score
    if gap >= switch_gap:     return "Switch"
    if gap >= distribute_gap: return "Distribute"
    return "Hold"