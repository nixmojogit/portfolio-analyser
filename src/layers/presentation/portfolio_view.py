"""
portfolio_view.py
Layer      : Presentation
Owns       : SKILL-P03, SKILL-P04
Description: Renders the New Opportunities tab — combines portfolio
             rebalancing (G3) and stock discovery (G2) into one cohesive view.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd

from src.utils.helpers import format_inr
from src.utils.logger import get_logger

log = get_logger(__name__)

URGENCY_COLOUR = {"immediate": "🔴", "soon": "🟠", "monitor": "🟢"}
ACTION_COLOUR  = {"trim": "🟠", "initiate": "🟢", "switch": "🔵",
                  "distribute": "🟡", "add": "➕"}
TAG_EMOJI      = {"Initiate": "🟢", "Switch": "🔵", "Distribute": "🟡"}
GRADE_EMOJI    = {
    "Strong": "🟢", "Moderate": "🟡", "Weak": "🔴",
    "Bullish": "🟢", "Neutral": "🟡", "Bearish": "🔴",
    "Undervalued": "🟢", "Fair": "🟡", "Overvalued": "🔴",
    "Low": "🟢", "High": "🔴",
    "Positive": "🟢", "Mixed": "🟡", "Negative": "🔴",
}


# ── Combined Opportunities View ───────────────────────────────────────────────

def render_opportunities_view(
    g2_results: dict,
    g3_results: dict,
    config: dict | None = None,
) -> None:
    """
    Combined New Opportunities tab.
    Section 1 — Portfolio Rebalancing  (G3)
    Section 2 — Stock Discovery        (G2)
    """
    if not g2_results and not g3_results:
        st.info("Run Portfolio Analysis to see opportunities and rebalancing actions.")
        return

    pa = g3_results.get("portfolio_analytics", {}) if g3_results else {}

    # ── Section 1: Portfolio Rebalancing ──────────────────────────────────────
    st.markdown("#### Portfolio Rebalancing")
    _render_rebalancing_section(g3_results, pa)

    st.divider()

    # ── Section 2: Stock Discovery ────────────────────────────────────────────
    st.markdown("#### Stock Discovery")
    _render_discovery_section(g2_results)


# ── Rebalancing Section ───────────────────────────────────────────────────────

def _render_rebalancing_section(g3_results: dict, pa: dict) -> None:
    """Compact rebalancing view: risk metrics + sector allocation + actions."""
    if not pa and not g3_results:
        st.info("No rebalancing data available.")
        return

    # Risk metrics strip
    _render_risk_strip(pa)

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("**Sector Allocation**")
        _render_sector_table(pa)

    with col_right:
        st.markdown("**Correlation**")
        _render_correlation_compact(pa)

    # Rebalancing actions
    plan = g3_results.get("rebalancing_plan", []) if g3_results else []
    if plan:
        st.markdown("**Rebalancing Actions**")
        _render_rebalancing_actions(plan)
    else:
        st.success("✅ No rebalancing actions required — portfolio allocation is on target.")


def _render_risk_strip(pa: dict) -> None:
    """4-metric compact strip for portfolio risk."""
    beta        = pa.get("portfolio_beta")
    beta_signal = pa.get("beta_signal", "")
    urgency     = pa.get("drift_urgency", "monitor")
    avg_corr    = pa.get("avg_correlation")
    over        = pa.get("overweight_sectors", [])
    under       = pa.get("underweight_sectors", [])

    beta_emoji = {"defensive": "🛡️", "market_neutral": "⚖️",
                  "aggressive": "🚀"}.get(beta_signal, "⚖️")
    urg_emoji  = URGENCY_COLOUR.get(urgency, "⚪")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Portfolio Beta",
              f"{beta:.2f}" if beta else "N/A",
              f"{beta_emoji} {beta_signal.replace('_', ' ').title()}" if beta else "")
    c2.metric("Rebalancing",
              f"{urg_emoji} {urgency.capitalize()}")
    c3.metric("Avg Correlation",
              f"{avg_corr:.2f}" if avg_corr else "N/A",
              "Well diversified" if avg_corr and avg_corr < 0.5 else
              ("Moderate" if avg_corr and avg_corr < 0.7 else "Concentrated"))
    c4.metric("Sector Imbalance",
              f"{len(over)} over / {len(under)} under",
              f"▲ {', '.join(over[:2])}" if over else "On target")


def _render_sector_table(pa: dict) -> None:
    """Current vs target sector allocation table."""
    current = pa.get("sector_allocation", {})
    target  = pa.get("target_allocation",  {})
    drift   = pa.get("sector_drift",       {})
    over    = pa.get("overweight_sectors", [])
    under   = pa.get("underweight_sectors", [])

    if not current:
        st.caption("No allocation data yet.")
        return

    rows = []
    for sector in sorted(set(current) | set(target)):
        cur  = current.get(sector, 0)
        tgt  = target.get(sector, 0)
        drft = drift.get(sector, cur - tgt)
        if sector in over:   status = "🔴 Over"
        elif sector in under: status = "🟢 Under"
        else:                 status = "✅ OK"
        rows.append({
            "Sector":    sector,
            "Current":   f"{cur:.1f}%",
            "Target":    f"{tgt:.1f}%",
            "Drift":     f"{drft:+.1f}%",
            "Status":    status,
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 hide_index=True, height=260)


def _render_correlation_compact(pa: dict) -> None:
    """Compact correlation summary."""
    avg_corr = pa.get("avg_correlation")
    pairs    = pa.get("high_corr_pairs", [])

    if avg_corr is not None:
        if avg_corr < 0.4:
            st.success(f"✅ Avg correlation: **{avg_corr:.2f}** — Well diversified")
        elif avg_corr < 0.7:
            st.warning(f"⚠️ Avg correlation: **{avg_corr:.2f}** — Moderate concentration")
        else:
            st.error(f"🔴 Avg correlation: **{avg_corr:.2f}** — High concentration risk")
    else:
        st.caption("Correlation data not available.")
        return

    if pairs:
        st.caption("**Highly correlated pairs (>0.7):**")
        rows = [{"Stock A": a, "Stock B": b, "Correlation": f"{c:.2f}"}
                for a, b, c in pairs]
        st.dataframe(pd.DataFrame(rows), use_container_width=True,
                     hide_index=True, height=200)
    else:
        st.success("✅ No highly correlated pairs")


def _render_rebalancing_actions(plan: list[dict]) -> None:
    """Rebalancing actions table with estimated capital."""
    rows = []
    for item in plan:
        act   = item.get("action", "").lower()
        emoji = ACTION_COLOUR.get(act, "⚪")
        rows.append({
            "Action":      f"{emoji} {act.capitalize()}",
            "Stock":       item.get("ticker", "").replace(".NS", ""),
            "Sector":      item.get("sector", ""),
            "Current Wt":  f"{item.get('current_weight', 0):.1f}%",
            "Target Wt":   f"{item.get('target_weight', 0):.1f}%",
            "Shares":      item.get("trade_shares", 0),
            "Est. Value":  format_inr(item.get("trade_value", 0)),
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    deploy = sum(
        i.get("trade_value", 0) for i in plan
        if i.get("action", "").lower() in ("initiate", "switch", "distribute", "add")
    )
    if deploy > 0:
        st.caption(f"💰 Estimated capital to deploy: **{format_inr(deploy)}**")


# ── Discovery Section ─────────────────────────────────────────────────────────

def _render_discovery_section(g2_results: dict) -> None:
    """Stock discovery candidates with filters and rationale expanders."""
    candidates = g2_results.get("ranked_candidates", [])
    top        = g2_results.get("top_recommendations",  [])

    if not candidates:
        st.info("No discovery candidates found. Run a fresh analysis to populate.")
        return

    # Top picks strip
    if top:
        st.markdown("**Top Picks**")
        cols = st.columns(min(len(top), 5))
        for col, c in zip(cols, top):
            emoji = TAG_EMOJI.get(c.get("action_tag", ""), "⚪")
            col.metric(
                c.get("ticker", "").replace(".NS", ""),
                f"{c.get('peer_score', 0):.1f} / 100",
                f"{emoji} {c.get('action_tag', '')}",
            )
        st.divider()

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        mode_filter = st.selectbox(
            "Mode", ["All", "Gap Fill", "Peer Compare"], label_visibility="collapsed"
        )
    with col2:
        tag_filter = st.selectbox(
            "Action", ["All", "Initiate", "Switch", "Distribute"],
            label_visibility="collapsed"
        )

    filtered = candidates
    if mode_filter == "Gap Fill":
        filtered = [c for c in filtered if c.get("mode") == "gap_fill"]
    elif mode_filter == "Peer Compare":
        filtered = [c for c in filtered if c.get("mode") == "peer_compare"]
    if tag_filter != "All":
        filtered = [c for c in filtered if c.get("action_tag") == tag_filter]

    # Candidates table
    rows = []
    for c in filtered:
        tag  = c.get("action_tag", "")
        mode = "Gap Fill" if c.get("mode") == "gap_fill" else "Peer"
        rows.append({
            "Stock":    c.get("ticker", "").replace(".NS", ""),
            "Sector":   c.get("sector", ""),
            "Score":    c.get("peer_score", 0),
            "Action":   f"{TAG_EMOJI.get(tag, '⚪')} {tag}",
            "Mode":     mode,
            "Gap":      f"{c.get('score_gap', '—')}",
        })

    if rows:
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=0, max_value=100, format="%.1f"
                ),
            },
        )
        st.caption(
            "Gap Fill = new sector opportunity · "
            "Peer = better stock in an existing sector · "
            "Gap = score vs your current holding in that sector"
        )

    # Rationale expanders
    if filtered:
        st.markdown("**Rationale**")
        for c in filtered:
            rationale = c.get("rationale", {})
            if not rationale:
                continue
            tag    = c.get("action_tag", "")
            ticker = c.get("ticker", "").replace(".NS", "")
            score  = c.get("peer_score", 0)
            emoji  = TAG_EMOJI.get(tag, "⚪")

            with st.expander(f"{emoji} {ticker} — {score:.1f}/100 — {tag}", expanded=False):
                st.info(rationale.get("summary", ""))
                col1, col2 = st.columns(2)
                with col1:
                    strengths = rationale.get("strengths", [])
                    if strengths:
                        st.markdown("**✅ Strengths**")
                        for s in strengths: st.markdown(f"- {s}")
                with col2:
                    risks = rationale.get("risks", [])
                    if risks:
                        st.markdown("**⚠️ Risks**")
                        for r in risks: st.markdown(f"- {r}")
                st.success(rationale.get("action", ""))

                grades = st.columns(5)
                for col, (name, key) in zip(grades, [
                    ("Fund.", "fundamental_grade"), ("Tech.", "technical_grade"),
                    ("Val.",  "valuation_grade"),   ("Risk",  "risk_grade"),
                    ("Sent.", "sentiment_grade"),
                ]):
                    g = c.get(key, "—")
                    col.metric(name, f"{GRADE_EMOJI.get(g, '⚪')} {g}")


# ── Legacy functions kept for backward compatibility ──────────────────────────

def render_portfolio_optimisation_view(g3_results: dict) -> None:
    """Legacy — now part of render_opportunities_view."""
    pa = g3_results.get("portfolio_analytics", {}) if g3_results else {}
    _render_rebalancing_section(g3_results, pa)


def render_discovery_view(g2_results: dict) -> None:
    """Legacy — now part of render_opportunities_view."""
    _render_discovery_section(g2_results)