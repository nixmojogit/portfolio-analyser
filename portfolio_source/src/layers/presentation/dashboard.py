"""
dashboard.py
Layer      : Presentation
Owns       : SKILL-P01, SKILL-P05
Description: Renders the main portfolio overview dashboard and alerts panel.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd

from src.layers.action.alert_manager import get_active_alerts, resolve_alert
from src.utils.helpers import format_inr
from src.utils.logger import get_logger

log = get_logger(__name__)

RECOMMENDATION_COLOURS = {
    "Strong Buy": "🟢",
    "Buy":        "🟩",
    "Hold":       "🟡",
    "Reduce":     "🟠",
    "Exit":       "🔴",
}

GRADE_COLOURS = {
    "Strong": "🟢", "Moderate": "🟡", "Weak": "🔴",
    "Bullish": "🟢", "Neutral": "🟡", "Bearish": "🔴",
    "Undervalued": "🟢", "Fair": "🟡", "Overvalued": "🔴",
    "Low": "🟢", "High": "🔴",
    "Positive": "🟢", "Mixed": "🟡", "Negative": "🔴",
}

URGENCY_COLOURS = {"high": "🔴", "medium": "🟠", "low": "🟡"}


# ── SKILL-P01: Portfolio Overview Dashboard ───────────────────────────────────

def render_portfolio_overview(config: dict, g1_results: dict | None = None) -> None:
    """
    SKILL-P01: Render Portfolio Overview Dashboard.
    Main home screen of the Streamlit application.
    """
    st.title("📈 Portfolio Analyser")

    if not g1_results:
        st.info(
            "No analysis results yet. Click **Run Analysis** in the sidebar to start."
        )
        return

    results = g1_results.get("results", {})
    if not results:
        st.warning("Analysis ran but returned no results.")
        return

    # ── Summary Bar ───────────────────────────────────────────────────────────
    _render_summary_bar(results)
    st.divider()

    # ── Active Alerts ─────────────────────────────────────────────────────────
    alerts = get_active_alerts()
    high_alerts = [a for a in alerts if a.get("urgency") == "high"]
    if high_alerts:
        st.subheader("🚨 Active Alerts")
        for alert in high_alerts[:5]:
            st.error(
                f"{URGENCY_COLOURS.get(alert['urgency'], '🔔')} "
                f"**{alert['ticker'] or ''}** — {alert['message']}"
            )
        st.divider()

    # ── Holdings Scorecard Table ──────────────────────────────────────────────
    st.subheader("📊 Portfolio Holdings")
    _render_holdings_table(results)


def _render_summary_bar(results: dict) -> None:
    """Render top-level portfolio summary metrics."""
    total_value    = sum(r.get("holding_value", 0) for r in results.values())
    avg_score      = sum(r.get("overall_score", 0) for r in results.values()) / max(len(results), 1)
    alerts         = get_active_alerts()
    high_alert_cnt = sum(1 for a in alerts if a.get("urgency") == "high")

    rec_counts = {}
    for r in results.values():
        rec = r.get("recommendation", "Hold")
        rec_counts[rec] = rec_counts.get(rec, 0) + 1

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Portfolio Value",  format_inr(total_value, crore=True))
    col2.metric("Holdings",         len(results))
    col3.metric("Avg Score",        f"{avg_score:.1f} / 100")
    col4.metric("🔴 High Alerts",   high_alert_cnt)
    col5.metric("Recommendations",
                f"Buy:{rec_counts.get('Strong Buy',0)+rec_counts.get('Buy',0)} "
                f"Hold:{rec_counts.get('Hold',0)} "
                f"Exit:{rec_counts.get('Exit',0)+rec_counts.get('Reduce',0)}")


def _render_holdings_table(results: dict) -> None:
    """Render the holdings scorecard summary table with ATR stop-loss column."""
    rows = []
    for ticker, r in sorted(results.items()):
        bd   = r.get("score_breakdown", {})
        rec  = r.get("recommendation", "Hold")
        sl   = r.get("stop_loss", {})
        cp   = r.get("current_price", 0) or 0
        bp   = r.get("buy_price", 0) or 0

        # Stop-loss display
        sl_price   = sl.get("stop_loss_price")
        sl_signal  = sl.get("stop_loss_signal", "safe")
        sl_method  = sl.get("stop_loss_method", "fixed_pct")
        sl_pct     = sl.get("equivalent_stop_pct")
        drawdown   = sl.get("current_drawdown_pct", 0) or 0

        # Stop-loss cell content
        if sl_price:
            method_tag = "ATR" if sl_method == "atr" else "Fixed"
            sl_display = f"₹{sl_price:,.2f} ({sl_pct:.1f}%) [{method_tag}]"
        else:
            sl_display = "N/A"

        # Colour emoji for stop-loss status
        sl_emoji = {"breached": "🔴", "warning": "🟠", "safe": "🟢"}.get(sl_signal, "⚪")

        # Drawdown colour
        drawdown_str = f"{drawdown:+.1f}%"

        rows.append({
            "Ticker":       ticker.replace(".NS", "").replace(".BO", ""),
            "Company":      r.get("company_name", ticker)[:20],
            "Price":        f"₹{cp:,.0f}",
            "Buy Price":    f"₹{bp:,.0f}",
            "Drawdown":     drawdown_str,
            "Stop-Loss":    sl_display,
            "SL Status":    f"{sl_emoji} {sl_signal.capitalize()}",
            "Score":        f"{r.get('overall_score', 0):.1f}",
            "Rec":          f"{RECOMMENDATION_COLOURS.get(rec, '⚪')} {rec}",
            "F":            f"{bd.get('fundamental', {}).get('score', 0):.0f}",
            "T":            f"{bd.get('technical',   {}).get('score', 0):.0f}",
            "V":            f"{bd.get('valuation',   {}).get('score', 0):.0f}",
            "R":            f"{bd.get('risk',        {}).get('score', 0):.0f}",
            "S":            f"{bd.get('sentiment',   {}).get('score', 0):.0f}",
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    # Stock selector for drill-down
    st.markdown("---")
    tickers = [r.replace(".NS", "").replace(".BO", "")
               for r in sorted(results.keys())]
    selected = st.selectbox(
        "🔍 Select a stock to view details:", ["— Select —"] + tickers
    )
    if selected and selected != "— Select —":
        full_ticker = next(
            (t for t in results if t.startswith(selected)), None
        )
        if full_ticker:
            st.session_state["selected_ticker"] = full_ticker

    # ── Table 2 — Recommendation Summary ─────────────────────────────────────
    st.divider()
    st.subheader("🎯 Recommendation Summary")
    _render_recommendation_summary(results)


def _render_recommendation_summary(results: dict) -> None:
    """
    Table 2 — Recommendation Summary.
    Shows Stock Rec, Portfolio Action, Net Recommendation and Reason
    for each holding in a clean, readable table.
    """
    NET_REC_EMOJI = {
        "Strong Buy": "🚀",
        "Buy":        "🟢",
        "Hold":       "🟡",
        "Reduce":     "🟠",
        "Exit":       "🔴",
    }
    PA_EMOJI = {
        "Trim":       "✂️",
        "Add":        "➕",
        "Initiate":   "🆕",
        "Switch":     "🔄",
        "Distribute": "📊",
        "—":          "—",
        None:         "—",
    }

    rows = []
    for ticker, r in sorted(results.items()):
        short    = ticker.replace(".NS", "").replace(".BO", "")
        stock_rec= r.get("recommendation", "Hold")
        pa       = r.get("portfolio_action") or "—"
        net_rec  = r.get("net_recommendation") or stock_rec
        reason   = r.get("net_reason") or "No combined signal available yet — run full analysis."

        stock_emoji = RECOMMENDATION_COLOURS.get(stock_rec, "⚪")
        net_emoji   = NET_REC_EMOJI.get(net_rec, "⚪")
        pa_emoji    = PA_EMOJI.get(pa, "—")

        rows.append({
            "Ticker":           short,
            "Stock Rec":        f"{stock_emoji} {stock_rec}",
            "Portfolio Action": f"{pa_emoji} {pa}",
            "Net Recommendation": f"{net_emoji} {net_rec}",
            "Reason":           reason,
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Reason": st.column_config.TextColumn(
                "Reason",
                width="large",
            ),
        },
    )
    st.caption(
        "💡 Stock Rec = G1 scorecard signal | "
        "Portfolio Action = G3 rebalancing need | "
        "Net Recommendation = combined actionable signal"
    )


# ── SKILL-P05: Alerts Panel ───────────────────────────────────────────────────

def render_alerts_panel() -> None:
    """
    SKILL-P05: Render dedicated alerts panel.
    Shows all active alerts sorted by urgency with resolve option.
    """
    st.title("🚨 Alerts")
    alerts = get_active_alerts()

    if not alerts:
        st.success("✅ No active alerts — portfolio is healthy.")
        return

    high   = [a for a in alerts if a.get("urgency") == "high"]
    medium = [a for a in alerts if a.get("urgency") == "medium"]
    low    = [a for a in alerts if a.get("urgency") == "low"]

    def _render_section(section_alerts: list, colour_fn, header: str) -> None:
        if not section_alerts:
            return
        st.subheader(header)
        for alert in section_alerts:
            col1, col2 = st.columns([5, 1])
            with col1:
                colour_fn(
                    f"**{alert.get('ticker', 'Portfolio')}** — "
                    f"{alert['message']} "
                    f"*(raised: {alert.get('created_at', '')[:10]})*"
                )
            with col2:
                if st.button("✅ Resolve", key=f"resolve_{alert['alert_id']}"):
                    resolve_alert(alert["alert_id"])
                    st.rerun()

    _render_section(high,   st.error,   "🔴 High Urgency")
    _render_section(medium, st.warning, "🟠 Medium Urgency")
    _render_section(low,    st.info,    "🟡 Low Urgency")

    st.divider()
    st.caption(f"Total active alerts: {len(alerts)}")