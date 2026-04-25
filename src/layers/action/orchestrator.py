"""
orchestrator.py
Layer      : Action
Owns       : SKILL-A10, SKILL-A11, SKILL-A12, SKILL-A13
Description: Orchestrates the integrated analysis run — all three goals
             execute as one cohesive block. Data fetched once and shared.
             Results flow sequentially: G1 → G2 → G3.
"""

from __future__ import annotations
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

PORTFOLIO_DB = Path("data/portfolio/portfolio.db")


# ── Database Helpers ──────────────────────────────────────────────────────────

def _load_portfolio_holdings(config: dict) -> list[dict]:
    """Load all current holdings from portfolio.db."""
    try:
        with sqlite3.connect(PORTFOLIO_DB) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM holdings ORDER BY ticker"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"Failed to load holdings: {e}")
        return []


def _write_score_to_db(ticker: str, result: dict) -> None:
    """Write scorecard results to scores_history table."""
    try:
        bd = result.get("score_breakdown", {})
        with sqlite3.connect(PORTFOLIO_DB) as conn:
            conn.execute("""
                INSERT INTO scores_history
                    (ticker, score_date, overall_score, fundamental_score,
                     technical_score, valuation_score, risk_score,
                     sentiment_score, recommendation)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker,
                datetime.now().strftime("%Y-%m-%d"),
                result.get("overall_score"),
                bd.get("fundamental", {}).get("score") if isinstance(bd.get("fundamental"), dict) else None,
                bd.get("technical",   {}).get("score") if isinstance(bd.get("technical"),   dict) else None,
                bd.get("valuation",   {}).get("score") if isinstance(bd.get("valuation"),   dict) else None,
                bd.get("risk",        {}).get("score") if isinstance(bd.get("risk"),        dict) else None,
                bd.get("sentiment",   {}).get("score") if isinstance(bd.get("sentiment"),   dict) else None,
                result.get("recommendation"),
            ))
            conn.commit()
    except Exception as e:
        log.warning(f"Score write error for {ticker}: {e}")


def _write_recommendation_to_db(ticker: str, rec: dict) -> None:
    """Write recommendation to recommendations_history table."""
    try:
        with sqlite3.connect(PORTFOLIO_DB) as conn:
            conn.execute("""
                INSERT INTO recommendations_history
                    (ticker, recommendation, overall_score, rationale,
                     recommended_action, supporting_signals, contradicting_signals)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker,
                rec.get("recommendation"),
                rec.get("overall_score"),
                rec.get("recommendation_rationale"),
                rec.get("recommended_action"),
                json.dumps(rec.get("supporting_signals", [])),
                json.dumps(rec.get("contradicting_signals", [])),
            ))
            conn.commit()
    except Exception as e:
        log.warning(f"Recommendation write error for {ticker}: {e}")


def _write_g2_results_to_db(ranked_candidates: list[dict]) -> None:
    """Store G2 ranked candidates to portfolio.db watchlist table."""
    try:
        with sqlite3.connect(PORTFOLIO_DB) as conn:
            # Clear previous G2 results
            conn.execute("DELETE FROM watchlist")
            for c in ranked_candidates[:20]:  # store top 20
                conn.execute("""
                    INSERT OR IGNORE INTO watchlist
                        (ticker, company_name, sector, overall_score, notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    c.get("ticker"),
                    c.get("ticker", "").split(".")[0],
                    c.get("sector"),
                    c.get("peer_score"),
                    json.dumps({
                        "mode":       c.get("mode"),
                        "action_tag": c.get("action_tag"),
                        "score_gap":  c.get("score_gap"),
                    }),
                ))
            conn.commit()
        log.info(f"G2: {len(ranked_candidates[:20])} candidates stored to watchlist")
    except Exception as e:
        log.warning(f"G2 DB write error: {e}")


def _write_rebalancing_to_db(plan: dict) -> None:
    """Store G3 rebalancing plan to rebalancing_log."""
    try:
        import uuid
        plan_id = str(uuid.uuid4())[:8]
        with sqlite3.connect(PORTFOLIO_DB) as conn:
            conn.execute("""
                INSERT INTO rebalancing_log
                    (plan_id, plan_date, plan_data,
                     estimated_beta_after, estimated_sharpe_after, status)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                plan_id,
                datetime.now().strftime("%Y-%m-%d"),
                json.dumps(plan.get("rebalancing_plan", [])),
                plan.get("estimated_beta_after"),
                plan.get("estimated_sharpe_after"),
                "pending",
            ))
            conn.commit()
        log.info(f"G3 rebalancing plan stored: {plan_id}")
    except Exception as e:
        log.warning(f"G3 DB write error: {e}")
def _compute_net_recommendation(
    stock_rec: str,
    portfolio_action: str | None,
    sector: str,
    overall_score: float,
    sector_drift: float | None = None,
) -> dict:
    """
    Compute net recommendation combining G1 stock score and G3 portfolio action.
    Returns net_recommendation and plain-English reason.
    """
    pa = (portfolio_action or "").lower()
    sr = (stock_rec or "hold").lower()

    # ── Net recommendation logic ──────────────────────────────────────────────
    if pa == "trim":
        if sr in ("strong buy", "buy"):
            net = "Hold"
            reason = (
                f"{sector} sector is overweight vs target. "
                f"Stock scores well ({overall_score:.0f}/100) but portfolio "
                f"balance requires trimming. Hold rather than add."
            )
        elif sr == "hold":
            net = "Reduce"
            reason = (
                f"{sector} sector is overweight vs target. "
                f"Combined with neutral stock score ({overall_score:.0f}/100), "
                f"reduce position to rebalance portfolio."
            )
        else:  # reduce / exit
            net = sr.title()
            reason = (
                f"Both stock quality ({sr.title()}) and portfolio balance "
                f"(sector overweight) signal reducing this position."
            )

    elif pa in ("initiate", "add"):
        if sr in ("strong buy", "buy"):
            net = "Strong Buy"
            reason = (
                f"Strong stock score ({overall_score:.0f}/100) aligns with "
                f"portfolio need — {sector} sector is underweight vs target."
            )
        elif sr == "hold":
            net = "Buy"
            reason = (
                f"Portfolio needs {sector} exposure (underweight). "
                f"Stock scores adequately ({overall_score:.0f}/100) — "
                f"consider initiating or adding to this position."
            )
        else:
            net = "Hold"
            reason = (
                f"Portfolio needs {sector} exposure but stock quality "
                f"({overall_score:.0f}/100) is weak. "
                f"Seek a better-scoring alternative in this sector."
            )

    elif pa == "distribute":
        net = sr.title()
        reason = (
            f"Consider distributing {sector} allocation — "
            f"a peer stock scores similarly. "
            f"Stock score: {overall_score:.0f}/100."
        )

    elif pa == "switch":
        net = "Reduce"
        reason = (
            f"A peer in {sector} scores significantly higher. "
            f"Consider switching from this stock to the recommended peer."
        )

    else:
        # No portfolio action — stock rec drives everything
        net = sr.title()
        if sr in ("strong buy", "buy"):
            reason = (
                f"Strong stock score ({overall_score:.0f}/100). "
                f"No portfolio rebalancing conflict — proceed with confidence."
            )
        elif sr == "hold":
            reason = (
                f"Stock scores {overall_score:.0f}/100. "
                f"No rebalancing action required — monitor regularly."
            )
        else:
            reason = (
                f"Stock score is weak ({overall_score:.0f}/100). "
                f"Consider reducing or exiting this position."
            )

    return {"net_recommendation": net, "reason": reason}




# ── SKILL-A10: Integrated Workflow (G1 → G2 → G3) ────────────────────────────

def run_g1_workflow(
    config: dict,
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    """
    SKILL-A10: Orchestrate Integrated Analysis — G1 → G2 → G3.
    All three goals run as one cohesive block. Data fetched once
    and shared. Results flow: G1 → G2 → G3.
    Args:
        config  : merged config dict
        tickers : specific tickers to run G1 for (all holdings if None)
    Returns: dict with g1_results, g2_results, g3_results,
             run_timestamp, errors, alerts
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
    from src.layers.data.news_module import (
        fetch_rss_news_feeds, fetch_corporate_announcements,
    )
    from src.layers.intelligence.technical_module import (
        compute_moving_averages, compute_rsi, compute_macd,
        compute_beta, compute_52w_momentum, compute_volume_signal,
    )
    from src.layers.intelligence.fundamental_scoring_module import (
        compute_revenue_growth, compute_margin_trends,
        compute_free_cash_flow, compute_roic,
        compute_promoter_holding_signal, compute_earnings_surprise,
        compute_earnings_estimate_revisions,
    )
    from src.layers.intelligence.valuation_scoring_module import (
        compute_peg_ratio, compute_pe_vs_sector, compute_ev_ebitda,
    )
    from src.layers.intelligence.sentiment_module import (
        score_news_sentiment, compute_insider_activity_signal,
        compute_institutional_ownership_change,
        resolve_analyst_data,
    )
    from src.layers.intelligence.risk_module import compute_stop_loss_proximity
    from src.layers.intelligence.scorecard_aggregator import (
        compute_fundamental_score, compute_technical_score,
        compute_valuation_score, compute_risk_score,
        compute_sentiment_score, compute_overall_stock_score,
    )
    from src.layers.intelligence.portfolio_analytics_module import (
        compute_sector_allocation, compute_portfolio_beta,
        compute_portfolio_sharpe, compute_correlation_matrix,
    )
    from src.layers.action.recommendation_engine import generate_stock_recommendation
    from src.layers.action.alert_manager import (
        detect_stop_loss_breach, detect_thesis_integrity_change,
        store_alerts_batch, generate_alert,
    )
    from src.layers.action.discovery_engine import (
        screen_gap_fill_candidates, screen_peer_compare_candidates,
        tag_peer_recommendation, rank_discovery_candidates,
        evaluate_candidate,
    )
    from src.layers.action.optimisation_engine import (
        detect_sector_allocation_drift, generate_rebalancing_plan,
    )

    start_time = datetime.now()
    log.info("=" * 60)
    log.info("[INTEGRATED] Starting full analysis: G1 → G2 → G3")

    holdings = _load_portfolio_holdings(config)
    if not holdings:
        log.error("[INTEGRATED] No holdings found in portfolio.db")
        return {
            "results": {}, "g2_results": {}, "g3_results": {},
            "run_timestamp": start_time.isoformat(),
            "errors": {"all": "No holdings found"}, "alerts": [],
        }

    if tickers:
        holdings = [h for h in holdings if h["ticker"] in tickers]

    # ── Shared Data Fetch (once, reused across all goals) ─────────────────────
    log.info("[INTEGRATED] Phase 1: Shared data fetch ...")
    index_data = fetch_index_and_sector_data(config=config)
    nifty_df   = index_data["index_data"].get("^NSEI")

    snapshots = {}
    for h in holdings:
        snap = fetch_realtime_price_snapshot(h["ticker"], config=config)
        snapshots[h["ticker"]] = snap

    total_value = sum(
        (snapshots.get(h["ticker"], {}).get("current_price") or 0) * h["quantity"]
        for h in holdings
    )

    # ── G1: Score Existing Holdings ───────────────────────────────────────────
    log.info("[INTEGRATED] Phase 2: G1 — Scoring existing holdings ...")

    g1_results:       dict = {}
    errors:           dict = {}
    sl_signals:       dict = {}
    fundamental_scores: dict = {}
    thesis_flags:     dict = {}
    revenue_signals:  dict = {}
    fcf_signals:      dict = {}

    for holding in holdings:
        ticker        = holding["ticker"]
        company_name  = holding.get("company_name", ticker)
        buy_price     = holding.get("buy_price", 0)
        quantity      = holding.get("quantity", 0)
        stop_loss_pct = holding.get("stop_loss_pct", 12.0)
        thesis_intact = bool(holding.get("thesis_intact", 1))

        log.info(f"[G1] Processing {ticker} ...")

        try:
            price_result = fetch_historical_price_data(ticker, period="2y", config=config)
            df           = price_result["price_df"]
            snap         = snapshots.get(ticker, {})
            cp           = snap.get("current_price") or buy_price

            stmts  = fetch_financial_statements(ticker, config=config)
            ratios = fetch_key_ratios(ticker, config=config)
            sh     = fetch_shareholding_pattern(ticker, config=config)
            pledge = fetch_promoter_pledge_data(ticker, config=config)
            news   = fetch_rss_news_feeds(company_name, ticker, config=config)
            anns   = fetch_corporate_announcements(ticker, config=config)

            all_headlines = news["headlines"] + [
                {"title": a["subject"], "source": "NSE", "summary": "", "url": ""}
                for a in anns["announcements"]
            ]

            ma   = compute_moving_averages(df)
            rsi  = compute_rsi(df)
            macd = compute_macd(df)
            beta = compute_beta(df, nifty_df) if nifty_df is not None else {"beta": None, "beta_signal": "moderate"}
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

            sentiment = score_news_sentiment(all_headlines, company_name, ticker, config)
            insider   = compute_insider_activity_signal(anns["insider_disclosures"])
            inst      = compute_institutional_ownership_change(
                sh["fii_change_qoq"], sh["dii_change_qoq"]
            )
            # Resolve analyst data through priority stack
            analyst   = resolve_analyst_data(sentiment, ratios)

            holding_value = cp * quantity
            concentration = (holding_value / total_value * 100) if total_value > 0 else 0
            sl = compute_stop_loss_proximity(cp, buy_price, df, stop_loss_pct, config)
            sl_signals[ticker] = sl

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
                beta["beta"], sl["proximity_to_stop_pct"],
                concentration, ratios.get("debt_to_equity"),
                pledge["pledge_pct"], config,
            )
            s_score = compute_sentiment_score(
                sentiment["sentiment_score"], insider["insider_signal"],
                inst["institutional_signal"], ratios.get("analyst_recommendation"),
                config,
            )
            overall = compute_overall_stock_score(
                f_score["fundamental_score"], t_score["technical_score"],
                v_score["valuation_score"],   r_score["risk_score"],
                s_score["sentiment_scorecard_score"], config,
            )

            rec = generate_stock_recommendation(
                overall["overall_score"],
                f_score["fundamental_grade"],
                t_score["technical_grade"],
                s_score["sentiment_grade"],
                sl["stop_loss_signal"],
                thesis_intact,
                overall["score_breakdown"],
                config,
            )

            stock_result = {
                "ticker":            ticker,
                "company_name":      company_name,
                "sector":            holding.get("sector", "Unknown"),
                "current_price":     cp,
                "buy_price":         buy_price,
                "quantity":          quantity,
                "holding_value":     round(holding_value, 2),
                "concentration_pct": round(concentration, 2),
                "overall_score":        overall["overall_score"],
                "recommendation":       overall["recommendation"],
                "score_breakdown":      overall["score_breakdown"],
                "fundamental_score":    f_score,
                "technical_score":      t_score,
                "valuation_score":      v_score,
                "risk_score":           r_score,
                "sentiment_score":      s_score,
                "stop_loss":            sl,
                "thesis_intact":        thesis_intact,
                "recommendation_detail": rec,
                "metrics": {
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
                    "sentiment_score":    sentiment["sentiment_score"],
                    "sentiment_label":    sentiment["sentiment_label"],
                    "positive_themes":    sentiment["key_positive_themes"],
                    "negative_themes":    sentiment["key_negative_themes"],
                    "analyst_rec":        analyst["rating"]["value"],
                    "analyst_rec_firm":   analyst["rating"]["firm"],
                    "analyst_rec_source": analyst["rating"]["source"],
                    "analyst_rec_note":   analyst["rating"]["note"],
                    "analyst_target":     analyst["target_price"]["value"],
                    "analyst_target_source": analyst["target_price"]["source"],
                    "analyst_target_note":   analyst["target_price"]["note"],
                    "analyst_target_mean":   analyst["target_mean"]["value"],
                    "analyst_target_low":    analyst["target_low"]["value"],
                    "analyst_target_high":   analyst["target_high"]["value"],
                    "analyst_all_ratings":   analyst["all_ratings"],
                    "current_price":         cp,
                },
                "news_headlines":    news["headlines"][:5],
                "run_timestamp":     datetime.now().isoformat(),
            }

            g1_results[ticker]             = stock_result
            fundamental_scores[ticker]     = f_score
            thesis_flags[ticker]           = thesis_intact
            revenue_signals[ticker]        = rev["revenue_signal"]
            fcf_signals[ticker]            = fcf["fcf_signal"]

            _write_score_to_db(ticker, {
                "overall_score":   overall["overall_score"],
                "recommendation":  overall["recommendation"],
                "score_breakdown": overall["score_breakdown"],
            })
            _write_recommendation_to_db(ticker, {
                **rec, "overall_score": overall["overall_score"],
            })

            log.info(
                f"[G1] {ticker}: score={overall['overall_score']:.1f} "
                f"→ {overall['recommendation']}"
            )

        except Exception as e:
            log.error(f"[G1] Failed for {ticker}: {e}")
            errors[ticker] = str(e)

    # G1 alerts
    sl_check     = detect_stop_loss_breach(sl_signals)
    thesis_check = detect_thesis_integrity_change(
        fundamental_scores, thesis_flags, revenue_signals, fcf_signals
    )
    all_alerts = sl_check["alerts"] + thesis_check["alerts"]

    log.info(
        f"[G1] Complete: {len(g1_results)} stocks, "
        f"{len(errors)} errors, {len(all_alerts)} alerts"
    )

    # ── G2: Discovery (Gap Fill + Peer Compare) ───────────────────────────────
    log.info("[INTEGRATED] Phase 3: G2 — Discovery ...")

    g2_results = {"ranked_candidates": [], "top_recommendations": []}

    try:
        from src.layers.data.cache_manager import cache_read, cache_write

        # ── G2 Cache Check — skip re-evaluation if run within 7 days ─────────
        g2_cache_key = "g2_discovery_results"
        g2_cached    = cache_read("SKILL-A11", g2_cache_key, ttl_hours=168)
        if g2_cached["cache_hit"]:
            log.info("[G2] Serving cached discovery results (within 7 days)")
            g2_results = g2_cached["cached_data"]
            ranked = g2_results  # ensure ranked is always defined
        else:
            # Compute sector allocation for gap detection
            current_prices = {
                h["ticker"]: (snapshots.get(h["ticker"], {}).get("current_price") or 0)
                for h in holdings
            }
            sector_alloc = compute_sector_allocation(holdings, current_prices, config)
            sector_drift = sector_alloc.get("sector_drift", {})

            existing_tickers = [h["ticker"] for h in holdings]

            # Mode 1 — Gap Fill
            log.info("[G2] Mode 1: Gap fill ...")
            gap_result     = screen_gap_fill_candidates(sector_drift, existing_tickers, config)
            gap_candidates = gap_result["gap_fill_candidates"]

            # Mode 2 — Peer Compare
            log.info("[G2] Mode 2: Peer compare ...")
            peer_result     = screen_peer_compare_candidates(holdings, g1_results, config)
            peer_candidates = peer_result["peer_candidates"]

            # Deduplicate all candidates to evaluate
            all_to_eval = {}
            for c in gap_candidates + peer_candidates:
                t = c["ticker"]
                if t not in all_to_eval:
                    all_to_eval[t] = c

            log.info(
                f"[G2] Evaluating {len(all_to_eval)} unique candidates "
                f"(no Claude AI — fundamentals + technicals only) ..."
            )

            goals          = config.get("goals", {})
            switch_gap     = goals.get("g2_switch_score_gap", 15)
            distribute_gap = goals.get("g2_distribute_score_gap", 5)

            evaluated_gap  = []
            evaluated_peer = []

            for ticker, candidate in all_to_eval.items():
                eval_result = evaluate_candidate(ticker, config)
                if eval_result is None:
                    continue

                candidate = dict(candidate)
                candidate["peer_score"]        = eval_result["score"]
                candidate["fundamental_grade"] = eval_result["fundamental_grade"]
                candidate["technical_grade"]   = eval_result["technical_grade"]
                candidate["valuation_grade"]   = eval_result["valuation_grade"]
                candidate["risk_grade"]        = eval_result["risk_grade"]
                candidate["sentiment_grade"]   = eval_result["sentiment_grade"]

                if candidate["mode"] == "gap_fill":
                    candidate["action_tag"] = "Initiate"
                    evaluated_gap.append(candidate)
                else:
                    avg_holding = candidate.get("avg_holding_score", 50)
                    tag = tag_peer_recommendation(
                        eval_result["score"], avg_holding, switch_gap, distribute_gap
                    )
                    candidate["action_tag"] = tag
                    candidate["score_gap"]  = round(eval_result["score"] - avg_holding, 2)
                    evaluated_peer.append(candidate)

            ranked = rank_discovery_candidates(
                evaluated_gap, evaluated_peer, g1_results, config
            )
            g2_results = dict(ranked)

            # Cache G2 results for 7 days
            cache_write("SKILL-A11", g2_cache_key, {
                "ranked_candidates":   ranked.get("ranked_candidates", []),
                "top_recommendations": ranked.get("top_recommendations", []),
            })
            log.info("[G2] Results cached for 7 days")

            # Store top candidates to DB watchlist
            _write_g2_results_to_db(ranked.get("ranked_candidates", []))

        # G2 alert if top switch candidate found
        top = ranked.get("top_recommendations", [])
        if top and top[0].get("action_tag") == "Switch":
            all_alerts.append({
                "alert_type": "rebalancing_required",
                "ticker":     top[0]["ticker"],
                "message":    (
                    f"G2: {top[0]['ticker']} scores {top[0]['peer_score']:.1f} "
                    f"vs {top[0]['avg_holding_score']:.1f} avg in "
                    f"{top[0]['sector']} — consider switching."
                ),
                "urgency": "medium",
            })

        log.info(
            f"[G2] Complete: {len(ranked.get('ranked_candidates', []))} "
            f"candidates ranked"
        )

    except Exception as e:
        log.error(f"[G2] Workflow error: {e}")
        errors["g2"] = str(e)

    # ── G3: Portfolio Optimisation ────────────────────────────────────────────
    log.info("[INTEGRATED] Phase 4: G3 — Portfolio optimisation ...")

    g3_results = {"rebalancing_plan": [], "portfolio_analytics": {}}

    try:
        current_prices = {
            h["ticker"]: (snapshots.get(h["ticker"], {}).get("current_price") or 0)
            for h in holdings
        }

        # Portfolio analytics
        price_data = {}
        for h in holdings:
            pr = fetch_historical_price_data(h["ticker"], period="1y", config=config)
            if not pr["price_df"].empty:
                price_data[h["ticker"]] = pr["price_df"]

        corr   = compute_correlation_matrix(price_data)
        alloc  = compute_sector_allocation(holdings, current_prices, config)
        betas  = {
            t: g1_results[t]["metrics"].get("beta")
            for t in g1_results if g1_results[t]["metrics"].get("beta")
        }
        p_beta = compute_portfolio_beta(holdings, betas, current_prices)

        # Sector drift detection
        drift_result = detect_sector_allocation_drift(
            alloc.get("sector_drift", {}), config
        )

        # Rebalancing plan
        rebal = generate_rebalancing_plan(
            drift_result.get("sectors_to_trim", []),
            drift_result.get("sectors_to_add", []),
            g2_results.get("ranked_candidates", []),
            holdings,
            current_prices,
            p_beta.get("portfolio_beta", 1.0),
            0.0,
            config,
        )

        g3_results = {
            "rebalancing_plan":      rebal.get("rebalancing_plan", []),
            "estimated_beta_after":  rebal.get("estimated_beta_after"),
            "portfolio_analytics": {
                "sector_allocation":    alloc.get("sector_allocation", {}),
                "target_allocation":    alloc.get("target_allocation", {}),
                "sector_drift":         alloc.get("sector_drift", {}),
                "overweight_sectors":   alloc.get("overweight_sectors", []),
                "underweight_sectors":  alloc.get("underweight_sectors", []),
                "portfolio_beta":       p_beta.get("portfolio_beta"),
                "beta_signal":          p_beta.get("beta_signal"),
                "high_corr_pairs":      corr.get("high_correlation_pairs", []),
                "avg_correlation":      corr.get("avg_portfolio_correlation"),
                "drift_urgency":        drift_result.get("rebalancing_urgency"),
            },
        }

        _write_rebalancing_to_db(g3_results)

        # ── Enrich G1 results with G3 portfolio actions ───────────────────────
        rebal_plan = g3_results.get("rebalancing_plan", [])
        # Build lookup: ticker -> portfolio action
        ticker_action = {
            r.get("ticker"): r.get("action", "").title()
            for r in rebal_plan
            if r.get("ticker")
        }
        # Also check sector-level actions for holdings not directly in plan
        sector_drift = g3_results.get("portfolio_analytics", {}).get("sector_drift", {})

        for ticker, result in g1_results.items():
            sector = result.get("sector", "")
            # Direct ticker action from rebalancing plan
            pa = ticker_action.get(ticker)
            if not pa:
                # Derive from sector drift
                drift = sector_drift.get(sector, 0)
                drift_thresh = (config or {}).get("goals", {}).get(
                    "rebalancing_drift_threshold", 5
                )
                if drift > drift_thresh:
                    pa = "Trim"
                elif drift < -drift_thresh:
                    pa = "Add"
                else:
                    pa = None

            # Compute net recommendation
            net = _compute_net_recommendation(
                stock_rec      = result.get("recommendation", "Hold"),
                portfolio_action = pa,
                sector         = sector,
                overall_score  = result.get("overall_score", 50),
            )
            result["portfolio_action"]   = pa or "—"
            result["net_recommendation"] = net["net_recommendation"]
            result["net_reason"]         = net["reason"]

        # G3 drift alert
        if drift_result.get("drift_detected"):
            urgency = (
                "high"   if drift_result.get("rebalancing_urgency") == "immediate"
                else "medium" if drift_result.get("rebalancing_urgency") == "soon"
                else "low"
            )
            all_alerts.append({
                "alert_type": "sector_drift",
                "ticker":     None,
                "message":    (
                    f"G3: Sector drift detected — "
                    f"overweight: {drift_result.get('sectors_to_trim')} | "
                    f"underweight: {drift_result.get('sectors_to_add')}. "
                    f"Urgency: {drift_result.get('rebalancing_urgency')}."
                ),
                "urgency": urgency,
            })

        log.info(
            f"[G3] Complete: {len(rebal.get('rebalancing_plan', []))} "
            f"rebalancing actions"
        )

    except Exception as e:
        log.error(f"[G3] Workflow error: {e}")
        errors["g3"] = str(e)

    # ── Store all alerts ──────────────────────────────────────────────────────
    if all_alerts:
        stored = store_alerts_batch(all_alerts)
        log.info(f"[INTEGRATED] {stored} alerts stored")

    run_time = (datetime.now() - start_time).seconds
    log.info(
        f"[INTEGRATED] Analysis complete in {run_time}s | "
        f"G1: {len(g1_results)} stocks | "
        f"G2: {len(g2_results.get('ranked_candidates', []))} candidates | "
        f"G3: {len(g3_results.get('rebalancing_plan', []))} actions | "
        f"Errors: {len(errors)}"
    )
    log.info("=" * 60)

    return {
        "results":       g1_results,     # G1 — keyed by ticker
        "g2_results":    g2_results,      # G2 — ranked candidates
        "g3_results":    g3_results,      # G3 — rebalancing plan + analytics
        "run_timestamp": start_time.isoformat(),
        "errors":        errors,
        "alerts":        all_alerts,
    }


# ── Legacy stubs (kept for compatibility) ────────────────────────────────────

def run_g2_workflow(config: dict) -> dict[str, Any]:
    """G2 now runs as part of the integrated workflow via run_g1_workflow."""
    log.info("[SKILL-A11] G2 runs as part of integrated workflow")
    return {"ranked_candidates": [], "run_timestamp": datetime.now().isoformat()}


def run_g3_workflow(config: dict) -> dict[str, Any]:
    """G3 now runs as part of the integrated workflow via run_g1_workflow."""
    log.info("[SKILL-A12] G3 runs as part of integrated workflow")
    return {"rebalancing_plan": [], "run_timestamp": datetime.now().isoformat()}


def schedule_automated_refresh(config: dict) -> None:
    """SKILL-A13: Scheduler — implemented in Phase 13."""
    log.info("[SKILL-A13] Scheduler not yet implemented")


def _load_nifty500_tickers() -> list[str]:
    """Not needed — G2 uses sector index constituents."""
    return []