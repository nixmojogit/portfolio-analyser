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
    "Switch": "🔄", "Distribute": "📊", "-": "-",
}
TAG_EMOJI = {"Initiate": "🆕", "Switch": "🔄", "Distribute": "📊"}
URGENCY_COLOUR = {"immediate": "🔴", "soon": "🟠", "monitor": "🟢"}
SIGNAL_ICON = {
    "Strong Opportunity": "🟢",
    "Good Opportunity":   "🔵",
    "Monitor":            "🟡",
    "Caution":            "🔴",
}
MODE_CONFIG = {
    "Gap Fill":     {"icon": "🎯", "desc": "Best stocks in underweight sectors -- Initiate"},
    "Peer Compare": {"icon": "🔄", "desc": "Better alternatives to existing holdings -- Switch or Distribute"},
    "Diversifier":  {"icon": "🌐", "desc": "High scorers with low portfolio correlation -- Initiate"},
}


def _score_dot(score: float) -> str:
    if score >= 75: return "🟢"
    if score >= 55: return "🟡"
    if score >= 35: return "🟠"
    return "🔴"


def _signal_label(score: float) -> str:
    if score >= 75: return "Strong Opportunity"
    if score >= 60: return "Good Opportunity"
    if score >= 45: return "Monitor"
    return "Caution"


def render_portfolio_overview(
    config: dict,
    analysis: dict | None = None,
    g2_results: dict | None = None,
) -> None:
    if not analysis:
        st.info("No analysis results yet. Click Run Portfolio Analysis in the sidebar.")
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
    if pa.get("sector_allocation"):
        st.markdown("#### Sector Allocation")
        _render_sector_allocation(pa)
        st.divider()
    st.markdown("#### Current Portfolio Overview")
    _render_holdings_table(results)
    st.divider()
    has_new_ideas = any([g2.get("mode_a"), g2.get("mode_b"), g2.get("mode_c")])
    if has_new_ideas:
        st.markdown("#### New Ideas")
        _render_new_ideas(g2)
        st.divider()
    st.markdown("#### Recommendation Summary")
    _render_recommendation_summary(results, g2)


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
    c6.metric("High Alerts",     high_alerts)


def _render_inline_alerts() -> None:
    alerts      = get_active_alerts()
    high_alerts = [a for a in alerts if a.get("urgency") == "high"]
    med_alerts  = [a for a in alerts if a.get("urgency") == "medium"]
    if not alerts:
        return
    for alert in high_alerts[:3]:
        col1, col2 = st.columns([10, 1])
        with col1:
            st.error(f"🔴 **{alert.get('ticker') or 'Portfolio'}** -- {alert['message']}", icon=None)
        with col2:
            if st.button("✕", key=f"dismiss_h_{alert['alert_id']}", help="Resolve"):
                resolve_alert(alert["alert_id"])
                st.rerun()
    if med_alerts:
        with st.expander(f"⚠️ {len(med_alerts)} medium-priority alert(s)", expanded=False):
            for alert in med_alerts[:5]:
                col1, col2 = st.columns([10, 1])
                with col1:
                    st.warning(f"**{alert.get('ticker') or 'Portfolio'}** -- {alert['message']}", icon=None)
                with col2:
                    if st.button("✕", key=f"dismiss_m_{alert['alert_id']}", help="Resolve"):
                        resolve_alert(alert["alert_id"])
                        st.rerun()


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
            status = "🔴 Overweight" if sector in over else "🟢 Underweight" if sector in under else "✅ On target"
            rows.append({"Sector": sector, "Current": f"{cur:.1f}%", "Target": f"{tgt:.1f}%", "Drift": f"{drft:+.1f}%", "Status": status})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=220)
    with col_sum:
        urg_emoji = URGENCY_COLOUR.get(urgency, "⚪")
        st.metric("Rebalancing", f"{urg_emoji} {urgency.capitalize()}")
        st.metric("Overweight",  len(over))
        st.metric("Underweight", len(under))


def _render_holdings_table(results: dict) -> None:
    sector_values: dict[str, float] = {}
    total_value = sum(r.get("holding_value", 0) or 0 for r in results.values())
    for r in results.values():
        s = r.get("sector", "Others")
        sector_values[s] = sector_values.get(s, 0) + (r.get("holding_value", 0) or 0)
    sector_pct = {s: round((v / total_value * 100), 1) if total_value > 0 else 0 for s, v in sector_values.items()}
    rows = []
    for ticker, r in sorted(results.items()):
        bd       = r.get("score_breakdown", {})
        sl       = r.get("stop_loss", {})
        cp       = r.get("current_price", 0) or 0
        quantity = r.get("quantity", 0) or 0
        sector   = r.get("sector", "-")
        sl_price  = sl.get("stop_loss_price")
        sl_signal = sl.get("stop_loss_signal", "safe")
        sl_method = sl.get("stop_loss_method", "fixed_pct")
        sl_pct    = sl.get("equivalent_stop_pct")
        drawdown  = sl.get("current_drawdown_pct", 0) or 0
        sl_display = f"₹{sl_price:,.2f} ({sl_pct:.1f}%) [{'ATR' if sl_method == 'atr' else 'Fixed'}]" if sl_price else "N/A"
        sl_emoji  = {"breached": "🔴", "warning": "🟠", "safe": "🟢"}.get(sl_signal, "⚪")
        sl_status = f"{sl_emoji} {sl_signal.capitalize()}"
        def _sc(name):
            v = bd.get(name, {})
            return float(v.get("score", 0)) if isinstance(v, dict) else 0.0
        score = r.get("overall_score", 0)
        rows.append({
            "Stock": ticker.replace(".NS", "").replace(".BO", ""),
            "Sector": sector, "Sector %": f"{sector_pct.get(sector, 0):.1f}%",
            "Qty": f"{int(quantity):,}", "Price": f"₹{cp:,.0f}",
            "Drawdown": f"{drawdown:+.1f}%", "Stop-Loss": sl_display, "SL Status": sl_status,
            "Score": f"{_score_dot(score)} {score:.1f}",
            "F": f"{_score_dot(_sc('fundamental'))} {_sc('fundamental'):.0f}",
            "T": f"{_score_dot(_sc('technical'))} {_sc('technical'):.0f}",
            "V": f"{_score_dot(_sc('valuation'))} {_sc('valuation'):.0f}",
            "R": f"{_score_dot(_sc('risk'))} {_sc('risk'):.0f}",
            "S": f"{_score_dot(_sc('sentiment'))} {_sc('sentiment'):.0f}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("F = Fundamental · T = Technical · V = Valuation · R = Risk · S = Sentiment · Sector % = sector share of total portfolio")


def _render_new_ideas(g2_data: dict) -> None:
    mode_a = g2_data.get("mode_a", [])
    mode_b = g2_data.get("mode_b", [])
    mode_c = g2_data.get("mode_c", [])
    if not mode_a and not mode_b and not mode_c:
        st.info("No new ideas found. Run a fresh analysis to populate.")
        return
    for mode_name, candidates in [("Gap Fill", mode_a), ("Peer Compare", mode_b), ("Diversifier", mode_c)]:
        if not candidates:
            continue
        cfg = MODE_CONFIG[mode_name]
        st.markdown(f"**{cfg['icon']} {mode_name}**")
        st.caption(cfg["desc"])
        rows = []
        for c in candidates:
            if not isinstance(c, dict):
                continue
            score  = c.get("final_score") or c.get("overall_score") or 0
            signal = c.get("signal") or _signal_label(score)
            action = c.get("action_tag", "Initiate")
            f = float(c.get("fundamental_score", 50.0))
            t = float(c.get("technical_score",   50.0))
            v = float(c.get("valuation_score",   50.0))
            r = float(c.get("risk_score",        50.0))
            s = float(c.get("sentiment_score",   50.0))
            row = {
                "Signal": f"{SIGNAL_ICON.get(signal, '⚪')} {signal}",
                "Stock": c.get("ticker", "").replace(".NS", "").replace(".BO", ""),
                "Sector": c.get("sector", ""), "Action": action,
                "Score": f"{_score_dot(score)} {score:.1f}",
                "F": f"{_score_dot(f)} {f:.0f}", "T": f"{_score_dot(t)} {t:.0f}",
                "V": f"{_score_dot(v)} {v:.0f}", "R": f"{_score_dot(r)} {r:.0f}",
                "S": f"{_score_dot(s)} {s:.0f}", "Reason": c.get("reason", "-"),
            }
            if mode_name == "Peer Compare":
                gap  = c.get("score_gap", 0)
                held = ", ".join(t.replace(".NS", "") for t in c.get("holding_tickers", []))
                row["vs Holding"] = f"{held} ({c.get('avg_holding_score', 0):.1f})"
                row["Score Gap"]  = f"+{gap:.1f}"
            elif mode_name == "Diversifier":
                corr = c.get("max_correlation")
                row["Correlation"] = f"{corr:.2f}" if corr is not None else "N/A"
            rows.append(row)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                column_config={"Reason": st.column_config.TextColumn("Reason", width="large")})
            st.caption("Signal: 🟢 Strong (75+) | 🔵 Good (60-74) | 🟡 Monitor (45-59) | 🔴 Caution (<45)")
        st.divider()


def _render_recommendation_summary(results: dict, g2_results: dict) -> None:
    rows = []
    for ticker, r in sorted(results.items()):
        pa        = r.get("portfolio_action") or "-"
        stock_rec = r.get("recommendation", "Hold")
        net_rec   = r.get("net_recommendation") or stock_rec
        reason    = r.get("net_reason") or "-"
        rows.append({
            "Company": r.get("company_name", ticker)[:25], "Type": "Holding",
            "Stock Action": f"{REC_EMOJI.get(stock_rec, '⚪')} {stock_rec}",
            "Portfolio Need": f"{PA_EMOJI.get(pa, '-')} {pa}",
            "Net Action": f"{NET_REC_EMOJI.get(net_rec, '⚪')} {net_rec}",
            "Reason": reason,
        })
    selected_new: dict[str, dict] = {}
    for c in g2_results.get("mode_a", []):
        sector = c.get("sector", "")
        if sector not in selected_new and isinstance(c, dict):
            selected_new[sector] = c
    for c in g2_results.get("mode_b", []):
        if c.get("action_tag") == "Switch" and isinstance(c, dict):
            sector = c.get("sector", "")
            if sector not in selected_new:
                selected_new[sector] = c
    for c in selected_new.values():
        ticker = c.get("ticker", "")
        short  = ticker.replace(".NS", "").replace(".BO", "")
        tag    = c.get("action_tag", "Initiate")
        mode   = c.get("mode", "")
        reason = c.get("reason", "-")
        mode_label = {"Gap Fill": "Gap Fill", "Peer Compare": "Peer Switch", "Diversifier": "Diversifier"}.get(mode, mode)
        rows.append({
            "Company": f"{short} ({c.get('sector', '')})", "Type": f"💡 {mode_label}",
            "Stock Action": "-", "Portfolio Need": "💡 New idea",
            "Net Action": f"{TAG_EMOJI.get(tag, '⚪')} {tag}", "Reason": reason,
        })
    if not rows:
        st.info("No data available.")
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
        column_config={
            "Reason": st.column_config.TextColumn("Reason", width="large"),
            "Type":   st.column_config.TextColumn("Type",   width="small"),
        })
    st.caption("Stock Action = G1 scorecard signal | Portfolio Need = rebalancing requirement | Net Action = combined decision")


def render_alerts_panel() -> None:
    st.markdown("#### Active Alerts")
    alerts = get_active_alerts()
    if not alerts:
        st.success("No active alerts -- portfolio is healthy.")
        return
    for urgency, fn in [("high", st.error), ("medium", st.warning), ("low", st.info)]:
        section = [a for a in alerts if a.get("urgency") == urgency]
        for alert in section:
            col1, col2 = st.columns([10, 1])
            with col1:
                fn(f"**{alert.get('ticker', 'Portfolio')}** -- {alert['message']} *({alert.get('created_at', '')[:10]})*", icon=None)
            with col2:
                if st.button("✕", key=f"resolve_{alert['alert_id']}"):
                    resolve_alert(alert["alert_id"])
                    st.rerun()
