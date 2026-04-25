"""
app.py
Entry point for the Portfolio Analyser Streamlit application.
Run with: streamlit run app.py
"""

import streamlit as st

from src.layers.configuration.config_manager import load_config
from src.layers.action.orchestrator import run_g1_workflow
from src.layers.presentation.dashboard import render_portfolio_overview, render_alerts_panel
from src.layers.presentation.stock_detail_view import render_stock_detail_view
from src.layers.presentation.portfolio_view import (
    render_portfolio_optimisation_view,
    render_discovery_view,
)
from src.utils.logger import setup_root_logger

# ── App Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Portfolio Analyser",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

setup_root_logger("INFO")


# ── Session State Init ────────────────────────────────────────────────────────
if "config" not in st.session_state:
    st.session_state["config"] = load_config()

if "analysis_results" not in st.session_state:
    st.session_state["analysis_results"] = None

if "selected_ticker" not in st.session_state:
    st.session_state["selected_ticker"] = None


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 Portfolio Analyser")
    st.caption("Indian Stock Market · NSE/BSE")
    st.divider()

    # Navigation
    page = st.radio(
        "Navigation",
        [
            "📊 Portfolio Overview",
            "🔍 Stock Detail",
            "🔭 Discovery (G2)",
            "⚖️ Optimisation (G3)",
            "🚨 Alerts",
        ],
        index=0,
    )

    st.divider()

    # Run Analysis button
    if st.button(
        "🔄 Run Full Analysis (G1→G2→G3)",
        use_container_width=True,
        type="primary",
    ):
        with st.spinner("Running integrated analysis (G1 → G2 → G3) ..."):
            config  = st.session_state["config"]
            results = run_g1_workflow(config)
            st.session_state["analysis_results"] = results
            st.session_state["selected_ticker"]  = None

        g1_count  = len(results.get("results", {}))
        g2_count  = len(results.get("g2_results", {}).get("ranked_candidates", []))
        g3_count  = len(results.get("g3_results", {}).get("rebalancing_plan", []))
        err_count = len(results.get("errors", {}))

        if err_count == 0:
            st.success(
                f"✅ Analysis complete!\n\n"
                f"G1: {g1_count} stocks scored\n"
                f"G2: {g2_count} candidates found\n"
                f"G3: {g3_count} rebalancing actions"
            )
        else:
            st.warning(
                f"⚠️ Completed with {err_count} error(s).\n"
                f"G1: {g1_count} | G2: {g2_count} | G3: {g3_count}"
            )
        st.rerun()

    st.divider()

    # Sidebar summary after analysis
    analysis = st.session_state.get("analysis_results")
    if analysis and analysis.get("results"):
        results = analysis["results"]
        g2      = analysis.get("g2_results", {})
        g3      = analysis.get("g3_results", {})
        pa      = g3.get("portfolio_analytics", {})

        st.caption(f"**Last run:** {analysis.get('run_timestamp', '')[:16]}")
        st.caption(f"**Holdings:** {len(results)}")
        avg = sum(r.get("overall_score", 0) for r in results.values()) / max(len(results), 1)
        st.caption(f"**Avg score:** {avg:.1f}/100")
        st.caption(f"**G2 candidates:** {len(g2.get('ranked_candidates', []))}")
        st.caption(f"**Portfolio beta:** {pa.get('portfolio_beta', 'N/A')}")
        st.caption(f"**Drift urgency:** {pa.get('drift_urgency', 'N/A')}")

        st.markdown("**Quick Select**")
        for ticker, r in sorted(
            results.items(), key=lambda x: -x[1].get("overall_score", 0)
        ):
            short = ticker.replace(".NS", "").replace(".BO", "")
            rec   = r.get("recommendation", "Hold")
            emoji = {
                "Strong Buy": "🚀", "Buy": "🟢", "Hold": "🟡",
                "Reduce": "🟠", "Exit": "🔴",
            }.get(rec, "⚪")
            if st.button(
                f"{emoji} {short} ({r.get('overall_score', 0):.0f})",
                key=f"sb_{ticker}",
                use_container_width=True,
            ):
                st.session_state["selected_ticker"] = ticker
                st.rerun()


# ── Page Router ───────────────────────────────────────────────────────────────
config   = st.session_state["config"]
analysis = st.session_state.get("analysis_results")
sel      = st.session_state.get("selected_ticker")

g1_results = analysis.get("results", {})  if analysis else {}
g2_results = analysis.get("g2_results", {}) if analysis else {}
g3_results = analysis.get("g3_results", {}) if analysis else {}

if page == "📊 Portfolio Overview":
    render_portfolio_overview(config, analysis)

elif page == "🔍 Stock Detail":
    if sel and sel in g1_results:
        render_stock_detail_view(sel, g1_results[sel])
    elif g1_results:
        best = max(g1_results.items(), key=lambda x: x[1].get("overall_score", 0))
        render_stock_detail_view(best[0], best[1])
    else:
        st.info("Run Analysis first, then select a stock from the sidebar.")

elif page == "🔭 Discovery (G2)":
    render_discovery_view(g2_results)

elif page == "⚖️ Optimisation (G3)":
    render_portfolio_optimisation_view(g3_results)

elif page == "🚨 Alerts":
    render_alerts_panel()