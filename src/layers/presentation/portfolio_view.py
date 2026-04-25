"""
portfolio_view.py
Layer      : Presentation
Owns       : SKILL-P04
Description: Renders G3 portfolio optimisation view — sector allocation,
             correlation heatmap, portfolio risk metrics, rebalancing plan.
             Also renders G2 discovery candidates view.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd

from src.utils.helpers import format_inr
from src.utils.logger import get_logger

log = get_logger(__name__)

URGENCY_COLOUR = {
    "immediate": "🔴",
    "soon":      "🟠",
    "monitor":   "🟢",
}

ACTION_COLOUR = {
    "trim":       "🟠",
    "initiate":   "🟢",
    "switch":     "🔵",
    "distribute": "🟡",
}


# ── SKILL-P04: Portfolio Optimisation View ────────────────────────────────────

def render_portfolio_optimisation_view(g3_results: dict) -> None:
    """
    SKILL-P04: Render G3 Portfolio Optimisation View.
    Shows sector allocation, correlation, risk metrics and rebalancing plan.
    """
    st.title("⚖️ Portfolio Optimisation (G3)")

    if not g3_results:
        st.info("Run Analysis first to see portfolio optimisation.")
        return

    pa   = g3_results.get("portfolio_analytics", {})
    plan = g3_results.get("rebalancing_plan", [])

    # ── Portfolio Risk Summary ────────────────────────────────────────────────
    st.subheader("📊 Portfolio Risk Metrics")
    _render_risk_metrics(pa)
    st.divider()

    # ── Sector Allocation ─────────────────────────────────────────────────────
    st.subheader("🏢 Sector Allocation")
    _render_sector_allocation(pa)
    st.divider()

    # ── Correlation ───────────────────────────────────────────────────────────
    high_corr = pa.get("high_corr_pairs", [])
    avg_corr  = pa.get("avg_correlation")
    st.subheader("🔗 Correlation Analysis")
    _render_correlation_section(high_corr, avg_corr)
    st.divider()

    # ── Rebalancing Plan ──────────────────────────────────────────────────────
    st.subheader("📋 Rebalancing Plan")
    _render_rebalancing_plan(plan)


def _render_risk_metrics(pa: dict) -> None:
    """Render portfolio-level risk metrics in a metric bar."""
    beta        = pa.get("portfolio_beta")
    beta_signal = pa.get("beta_signal", "—")
    urgency     = pa.get("drift_urgency", "monitor")
    avg_corr    = pa.get("avg_correlation")
    over        = pa.get("overweight_sectors", [])
    under       = pa.get("underweight_sectors", [])

    col1, col2, col3, col4 = st.columns(4)

    beta_emoji = {"defensive": "🛡️", "market_neutral": "⚖️", "aggressive": "🚀"}.get(
        beta_signal, "⚖️"
    )
    col1.metric(
        "Portfolio Beta",
        f"{beta:.2f}" if beta else "N/A",
        f"{beta_emoji} {beta_signal.replace('_', ' ').title()}" if beta_signal else "",
    )

    urg_emoji = URGENCY_COLOUR.get(urgency, "⚪")
    col2.metric(
        "Rebalancing Urgency",
        f"{urg_emoji} {urgency.capitalize()}",
    )

    col3.metric(
        "Avg Correlation",
        f"{avg_corr:.2f}" if avg_corr else "N/A",
        "Low = well diversified" if avg_corr and avg_corr < 0.5 else "High = concentrated",
    )

    col4.metric(
        "Sector Imbalance",
        f"{len(over)} over / {len(under)} under",
        f"Overweight: {', '.join(over[:2]) if over else 'None'}",
    )


def _render_sector_allocation(pa: dict) -> None:
    """Render current vs target sector allocation as a comparison table."""
    current = pa.get("sector_allocation", {})
    target  = pa.get("target_allocation", {})
    drift   = pa.get("sector_drift", {})
    over    = pa.get("overweight_sectors", [])
    under   = pa.get("underweight_sectors", [])

    if not current:
        st.info("No sector allocation data available.")
        return

    all_sectors = sorted(set(current.keys()) | set(target.keys()))
    rows = []
    for sector in all_sectors:
        cur = current.get(sector, 0)
        tgt = target.get(sector, 0)
        drft= drift.get(sector, cur - tgt)

        if sector in over:
            status = "🔴 Overweight"
        elif sector in under:
            status = "🟢 Underweight"
        else:
            status = "✅ On Target"

        rows.append({
            "Sector":       sector,
            "Current %":    f"{cur:.1f}%",
            "Target %":     f"{tgt:.1f}%",
            "Drift":        f"{drft:+.1f}%",
            "Status":       status,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_correlation_section(
    high_corr_pairs: list,
    avg_corr: float | None,
) -> None:
    """Render correlation analysis section."""
    if avg_corr is not None:
        if avg_corr < 0.4:
            st.success(f"✅ Average correlation: **{avg_corr:.2f}** — Portfolio is well diversified")
        elif avg_corr < 0.7:
            st.warning(f"⚠️ Average correlation: **{avg_corr:.2f}** — Moderate diversification")
        else:
            st.error(f"🔴 Average correlation: **{avg_corr:.2f}** — High concentration risk")

    if high_corr_pairs:
        st.markdown("**⚠️ Highly Correlated Pairs (>0.7)**")
        rows = [
            {"Stock A": a, "Stock B": b, "Correlation": f"{c:.2f}"}
            for a, b, c in high_corr_pairs
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.success("✅ No highly correlated pairs detected")


def _render_rebalancing_plan(plan: list[dict]) -> None:
    """Render the rebalancing action plan as a formatted table."""
    if not plan:
        st.success("✅ No rebalancing actions required — portfolio is balanced.")
        return

    rows = []
    for action in plan:
        act   = action.get("action", "").lower()
        emoji = ACTION_COLOUR.get(act, "⚪")
        rows.append({
            "Action":          f"{emoji} {act.capitalize()}",
            "Ticker":          action.get("ticker", ""),
            "Sector":          action.get("sector", ""),
            "Current Wt%":     f"{action.get('current_weight', 0):.1f}%",
            "Target Wt%":      f"{action.get('target_weight', 0):.1f}%",
            "Shares":          action.get("trade_shares", 0),
            "Est. Value":      format_inr(action.get("trade_value", 0)),
            "Score":           f"{action.get('score', '—')}",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    total_deploy = sum(
        a.get("trade_value", 0)
        for a in plan
        if a.get("action", "").lower() in ("initiate", "switch", "distribute")
    )
    if total_deploy > 0:
        st.info(f"💰 Estimated capital to deploy: **{format_inr(total_deploy)}**")


# ── G2 Discovery View ─────────────────────────────────────────────────────────

def render_discovery_view(g2_results: dict) -> None:
    """
    SKILL-P03: Render G2 Discovery Candidates View.
    Shows ranked new stock candidates with mode and action tags.
    """
    st.title("🔍 Stock Discovery (G2)")

    if not g2_results:
        st.info("Run Analysis first to see discovery candidates.")
        return

    candidates = g2_results.get("ranked_candidates", [])
    top        = g2_results.get("top_recommendations", [])

    if not candidates:
        st.info("No discovery candidates found in this run.")
        return

    # ── Top Picks ─────────────────────────────────────────────────────────────
    if top:
        st.subheader("⭐ Top Recommendations")
        cols = st.columns(min(len(top), 5))
        for col, c in zip(cols, top):
            tag_emoji = {
                "Initiate":   "🟢",
                "Switch":     "🔵",
                "Distribute": "🟡",
            }.get(c.get("action_tag", ""), "⚪")
            col.metric(
                c.get("ticker", "").replace(".NS", ""),
                f"{c.get('peer_score', 0):.1f} / 100",
                f"{tag_emoji} {c.get('action_tag', '')}",
            )
        st.divider()

    # ── Filters ───────────────────────────────────────────────────────────────
    st.subheader("📋 All Candidates")
    col1, col2 = st.columns(2)
    with col1:
        mode_filter = st.selectbox(
            "Filter by Mode",
            ["All", "Gap Fill", "Peer Compare"],
        )
    with col2:
        tag_filter = st.selectbox(
            "Filter by Action",
            ["All", "Initiate", "Switch", "Distribute"],
        )

    # Apply filters
    filtered = candidates
    if mode_filter == "Gap Fill":
        filtered = [c for c in filtered if c.get("mode") == "gap_fill"]
    elif mode_filter == "Peer Compare":
        filtered = [c for c in filtered if c.get("mode") == "peer_compare"]
    if tag_filter != "All":
        filtered = [c for c in filtered if c.get("action_tag") == tag_filter]

    # ── Candidates Table ──────────────────────────────────────────────────────
    rows = []
    for c in filtered:
        tag   = c.get("action_tag", "")
        mode  = c.get("mode", "")
        emoji = {"Initiate": "🟢", "Switch": "🔵", "Distribute": "🟡"}.get(tag, "⚪")
        mode_label = "Gap Fill" if mode == "gap_fill" else "Peer"

        rows.append({
            "Ticker":     c.get("ticker", "").replace(".NS", ""),
            "Sector":     c.get("sector", ""),
            "Score":      f"{c.get('peer_score', 0):.1f}",
            "Action":     f"{emoji} {tag}",
            "Mode":       mode_label,
            "Score Gap":  f"{c.get('score_gap', '—')}",
            "Gap Fill %": f"{c.get('gap_size_pct', '—')}",
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(
            "💡 Gap Fill = missing sector opportunity | "
            "Peer = better stock in same sector | "
            "Score Gap = vs your current holding in that sector"
        )

    # ── Rationale Expanders ───────────────────────────────────────────────────
    if filtered:
        st.markdown("---")
        st.subheader("📝 Recommendation Rationale")
        for c in filtered:
            rationale = c.get("rationale", {})
            if not rationale:
                continue
            tag      = c.get("action_tag", "")
            ticker   = c.get("ticker", "").replace(".NS", "")
            score    = c.get("peer_score", 0)
            emoji    = {"Initiate": "🟢", "Switch": "🔵", "Distribute": "🟡"}.get(tag, "⚪")

            with st.expander(
                f"{emoji} {ticker} — {score:.1f}/100 — {tag}",
                expanded=False,
            ):
                # Summary
                st.markdown(f"**📋 Summary**")
                st.info(rationale.get("summary", ""))

                col1, col2 = st.columns(2)
                with col1:
                    strengths = rationale.get("strengths", [])
                    if strengths:
                        st.markdown("**✅ Key Strengths**")
                        for s in strengths:
                            st.markdown(f"- {s}")
                with col2:
                    risks = rationale.get("risks", [])
                    if risks:
                        st.markdown("**⚠️ Key Risks**")
                        for r in risks:
                            st.markdown(f"- {r}")

                st.markdown("**🎯 Suggested Action**")
                st.success(rationale.get("action", ""))

                # Scorecard grades
                st.markdown("**📊 Scorecard Grades**")
                grade_cols = st.columns(5)
                grade_map  = {
                    "Fundamental": c.get("fundamental_grade", "—"),
                    "Technical":   c.get("technical_grade",   "—"),
                    "Valuation":   c.get("valuation_grade",   "—"),
                    "Risk":        c.get("risk_grade",        "—"),
                    "Sentiment":   c.get("sentiment_grade",   "—"),
                }
                grade_emoji = {
                    "Strong": "🟢", "Moderate": "🟡", "Weak": "🔴",
                    "Bullish": "🟢", "Neutral": "🟡", "Bearish": "🔴",
                    "Undervalued": "🟢", "Fair": "🟡", "Overvalued": "🔴",
                    "Low": "🟢", "High": "🔴",
                    "Positive": "🟢", "Mixed": "🟡", "Negative": "🔴",
                }
                for col, (name, grade) in zip(grade_cols, grade_map.items()):
                    col.metric(name, f"{grade_emoji.get(grade,'⚪')} {grade}")
    else:
        st.info("No candidates match the selected filters.")