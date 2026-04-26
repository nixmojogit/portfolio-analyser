"""
dashboard.py
Layer      : Presentation
Owns       : SKILL-P01, SKILL-P05
"""

from __future__ import annotations
import streamlit as st
import pandas as pd

from src.layers.action.alert_manager import get_active_alerts, resolve_alert
from src.utils.helpers import format_inr
from src.utils.logger import get_logger

log = get_logger(__name__)

REC_EMOJI = {
    "Strong Buy": "🚀", "Buy": "🟢", "Hold": "🟡",
    "Reduce": "🟠", "Exit": "🔴",
}
NET_REC_EMOJI = {
    "Strong Buy": "🚀", "Buy": "🟢", "Hold": "🟡",
    "Reduce": "🟠", "Exit": "🔴",
}
PA_EMOJI = {
    "Trim": "✂️", "Add": "➕", "Initiate": "🆕",
    "Switch": "🔄", "Distribute": "📊", "—": "—",
}
TAG_EMOJI      = {"Initiate": "🆕", "Switch": "🔄", "Distribute": "📊"}
URGENCY_COLOUR = {"immediate": "🔴", "soon": "🟠", "monitor": "🟢"}
ACTION_COLOUR  = {"trim": "🟠", "initiate": "🟢", "switch": "🔵",
                  "distribute": "🟡", "add": "➕"}


def _score_dot(score: float) -> str:
    """Coloured dot based on score value."""
    if score >= 75: return "🟢"
    if score >= 55: return "🟡"
    if score >= 35: return "🟠"
    return "🔴"


# ── SKILL-P01: Portfolio Overview ─────────────────────────────────────────────

def render_portfolio_overview(
    config: dict,
    analysis: dict | None = None,
    g2_results: dict | None = None,
) -> None:
    if not analysis:
        st.info("No analysis results yet. Click **Run Portfolio Analysis** in the sidebar.")
        return

    results = analysis.get("results", {})
    if not results:
        st.warning("Analysis ran but returned no results.")
        return

    g2 = g2_results or {}
    g3 = analysis.get("g3_results", {}) or {}
    pa = g3.get("portfolio_analytics", {})

    _render_summary_bar(results)
    _render_inline_alerts()
    st.divider()

    # Sector allocation
    if pa.get("sector_allocation"):
        st.markdown("#### Sector Allocation")
        _render_sector_allocation(pa)
        st.divider()

    # Change 3: renamed table heading
    st.markdown("#### Current Portfolio Overview")
    _render_holdings_table(results)
    st.divider()

    # Change 7: New Ideas replaces Rebalancing Actions
    new_ideas = g2.get("new_ideas", [])
    if new_ideas:
        st.markdown("#### New Ideas")
        _render_new_ideas(new_ideas)
        st.divider()

    st.markdown("#### Recommendation Summary")
    _render_recommendation_summary(results, g2)


# ── Summary Bar ───────────────────────────────────────────────────────────────

def _render_summary_bar(results: dict) -> None:
    total_value = sum(r.get("holding_value", 0) for r in results.values())
    avg_score   = sum(r.get("overall_score", 0) for r in results.values()) / max(len(results), 1)
    alerts      = get_active_alerts()
    high_alerts = sum(1 for a in alerts if a.get("urgency") == "high")
    buy_cnt     = sum(1 for r in results.values() if r.get("recommendation") in ("Strong Buy", "Buy"))
    hold_cnt    = sum(1 for r in results.values() if r.get("recommendation") == "Hold")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Portfolio Value", format_inr(total_value, crore=True))
    c2.metric("Holdings",        len(results))
    c3.metric("Avg Score",       f"{avg_score:.1f} / 100")
    c4.metric("Buy Signals",     buy_cnt)
    c5.metric("Hold Signals",    hold_cnt)
    c6.metric("🔴 High Alerts",  high_alerts)


# ── Inline Alerts ─────────────────────────────────────────────────────────────

def _render_inline_alerts() -> None:
    alerts      = get_active_alerts()
    high_alerts = [a for a in alerts if a.get("urgency") == "high"]
    med_alerts  = [a for a in alerts if a.get("urgency") == "medium"]

    if not alerts:
        return

    for alert in high_alerts[:3]:
        col1, col2 = st.columns([10, 1])
        with col1:
            st.error(
                f"🔴 **{alert.get('ticker') or 'Portfolio'}** — {alert['message']}",
                icon=None,
            )
        with col2:
            if st.button("✕", key=f"dismiss_h_{alert['alert_id']}", help="Resolve"):
                resolve_alert(alert["alert_id"])
                st.rerun()

    if med_alerts:
        with st.expander(f"⚠️ {len(med_alerts)} medium-priority alert(s)", expanded=False):
            for alert in med_alerts[:5]:
                col1, col2 = st.columns([10, 1])
                with col1:
                    st.warning(
                        f"**{alert.get('ticker') or 'Portfolio'}** — {alert['message']}",
                        icon=None,
                    )
                with col2:
                    if st.button("✕", key=f"dismiss_m_{alert['alert_id']}", help="Resolve"):
                        resolve_alert(alert["alert_id"])
                        st.rerun()


# ── Sector Allocation ─────────────────────────────────────────────────────────

def _render_sector_allocation(pa: dict) -> None:
    current = pa.get("sector_allocation", {})
    target  = pa.get("target_allocation",  {})
    drift   = pa.get("sector_drift",       {})
    over    = pa.get("overweight_sectors", [])
    under   = pa.get("underweight_sectors", [])
    urgency = pa.get("drift_urgency", "monitor")

    col_tbl, col_sum = st.columns([3, 1])
    with col_tbl:
        rows = []
        for sector in sorted(set(current) | set(target)):
            cur  = current.get(sector, 0)
            tgt  = target.get(sector, 0)
            drft = drift.get(sector, cur - tgt)
            if sector in over:    status = "🔴 Overweight"
            elif sector in under: status = "🟢 Underweight"
            else:                 status = "✅ On target"
            rows.append({
                "Sector":  sector,
                "Current": f"{cur:.1f}%",
                "Target":  f"{tgt:.1f}%",
                "Drift":   f"{drft:+.1f}%",
                "Status":  status,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True,
                     hide_index=True, height=220)
    with col_sum:
        urg_emoji = URGENCY_COLOUR.get(urgency, "⚪")
        st.metric("Rebalancing", f"{urg_emoji} {urgency.capitalize()}")
        st.metric("Overweight",  len(over))
        st.metric("Underweight", len(under))


# ── New Ideas Table (replaces Rebalancing Actions) ───────────────────────────

def _render_new_ideas(new_ideas: list[dict]) -> None:
    """
    Render discovered stocks with F, T, V, R, S scores and coloured dots —
    same visual style as Current Portfolio Overview.
    """
    if not new_ideas:
        st.info("No new ideas found. Run a fresh analysis to populate.")
        return

    rows = []
    for c in new_ideas:
        f = c.get("fundamental_score", 50.0)
        t = c.get("technical_score",   50.0)
        v = c.get("valuation_score",   50.0)
        r = c.get("risk_score",        50.0)
        s = c.get("sentiment_score",   50.0)
        score = c.get("overall_score", 0.0)

        rows.append({
            "Stock":  c.get("ticker", "").replace(".NS", "").replace(".BO", ""),
            "Sector": c.get("sector", ""),
            "Score":  f"{_score_dot(score)} {score:.1f}",
            "F":      f"{_score_dot(f)} {f:.0f}",
            "T":      f"{_score_dot(t)} {t:.0f}",
            "V":      f"{_score_dot(v)} {v:.0f}",
            "R":      f"{_score_dot(r)} {r:.0f}",
            "S":      f"{_score_dot(s)} {s:.0f}",
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        f"{len(new_ideas)} stocks discovered across all sectors · "
        "F = Fundamental · T = Technical · V = Valuation · R = Risk · S = Sentiment"
    )


# ── Holdings Table (Changes 3, 4, 5) ─────────────────────────────────────────

def _render_holdings_table(results: dict) -> None:
    rows = []
    for ticker, r in sorted(results.items()):
        bd  = r.get("score_breakdown", {})
        sl  = r.get("stop_loss", {})
        cp  = r.get("current_price", 0) or 0

        sl_price  = sl.get("stop_loss_price")
        sl_signal = sl.get("stop_loss_signal", "safe")
        sl_method = sl.get("stop_loss_method", "fixed_pct")
        sl_pct    = sl.get("equivalent_stop_pct")
        drawdown  = sl.get("current_drawdown_pct", 0) or 0

        sl_display = (
            f"₹{sl_price:,.2f} ({sl_pct:.1f}%) "
            f"[{'ATR' if sl_method == 'atr' else 'Fixed'}]"
            if sl_price else "N/A"
        )
        # Change 4: restored label next to icon
        sl_emoji  = {"breached": "🔴", "warning": "🟠", "safe": "🟢"}.get(sl_signal, "⚪")
        sl_status = f"{sl_emoji} {sl_signal.capitalize()}"

        def _sc(name):
            v = bd.get(name, {})
            return float(v.get("score", 0)) if isinstance(v, dict) else 0.0

        score = r.get("overall_score", 0)

        rows.append({
            "Stock":     ticker.replace(".NS", "").replace(".BO", ""),
            "Price":     f"₹{cp:,.0f}",
            "Drawdown":  f"{drawdown:+.1f}%",
            "Stop-Loss": sl_display,
            # Change 4: label restored
            "SL Status": sl_status,
            # Change 5: coloured dot + score number, no progress bar
            "Score":     f"{_score_dot(score)} {score:.1f}",
            "F":  f"{_score_dot(_sc('fundamental'))} {_sc('fundamental'):.0f}",
            "T":  f"{_score_dot(_sc('technical'))}  {_sc('technical'):.0f}",
            "V":  f"{_score_dot(_sc('valuation'))}  {_sc('valuation'):.0f}",
            "R":  f"{_score_dot(_sc('risk'))}        {_sc('risk'):.0f}",
            "S":  f"{_score_dot(_sc('sentiment'))}  {_sc('sentiment'):.0f}",
        })

    # Change 5: no ProgressColumn — plain dataframe
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("F = Fundamental · T = Technical · V = Valuation · R = Risk · S = Sentiment")


# ── Recommendation Summary (Changes 6, 4) ────────────────────────────────────

def _render_recommendation_summary(
    results: dict,
    g2_results: dict,
) -> None:
    rows = []

    # Existing holdings
    for ticker, r in sorted(results.items()):
        # Change 6: "Stock" column removed, "Company" kept
        pa      = r.get("portfolio_action") or "—"
        net_rec = r.get("net_recommendation") or r.get("recommendation", "Hold")
        reason  = r.get("net_reason") or "—"

        rows.append({
            "Company":        r.get("company_name", ticker)[:25],
            "Portfolio Need": f"{PA_EMOJI.get(pa, '—')} {pa}",
            "Net Action":     f"{NET_REC_EMOJI.get(net_rec, '⚪')} {net_rec}",
            "Reason":         reason,
        })

    # Discovery candidates
    candidates = g2_results.get("ranked_candidates", [])
    for c in candidates:
        ticker  = c.get("ticker", "")
        short   = ticker.replace(".NS", "").replace(".BO", "")
        tag     = c.get("action_tag", "Initiate")
        rat     = c.get("rationale", {})
        summary = rat.get("summary", "") or rat.get("action", "") or "—"
        mode    = "Gap fill" if c.get("mode") == "gap_fill" else "Peer switch"

        rows.append({
            "Company":        f"{short} · {c.get('sector', '')} ({mode})",
            "Portfolio Need": "💡 New idea",
            "Net Action":     f"{TAG_EMOJI.get(tag, '⚪')} {tag}",
            "Reason":         summary[:120] + ("…" if len(summary) > 120 else ""),
        })

    if not rows:
        st.info("No data available.")
        return

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Reason": st.column_config.TextColumn("Reason", width="large"),
        },
    )
    st.caption(
        "Holdings: Portfolio Need = rebalancing signal · Net Action = combined decision  |  "
        "New ideas: Portfolio Need = 💡 New idea · Net Action = suggested entry type"
    )


# ── SKILL-P05: Alerts Panel ───────────────────────────────────────────────────

def render_alerts_panel() -> None:
    st.markdown("#### Active Alerts")
    alerts = get_active_alerts()
    if not alerts:
        st.success("✅ No active alerts — portfolio is healthy.")
        return
    for urgency, fn in [("high", st.error), ("medium", st.warning), ("low", st.info)]:
        section = [a for a in alerts if a.get("urgency") == urgency]
        for alert in section:
            col1, col2 = st.columns([10, 1])
            with col1:
                fn(
                    f"**{alert.get('ticker', 'Portfolio')}** — "
                    f"{alert['message']} "
                    f"*({alert.get('created_at', '')[:10]})*",
                    icon=None,
                )
            with col2:
                if st.button("✕", key=f"resolve_{alert['alert_id']}"):
                    resolve_alert(alert["alert_id"])
                    st.rerun()