"""
stock_detail_view.py
Layer      : Presentation
Owns       : SKILL-P02, SKILL-P03
Description: Renders per-stock drilldown view and discovery candidates view.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd

from src.utils.helpers import format_inr
from src.utils.logger import get_logger

log = get_logger(__name__)

SIGNAL_EMOJI = {"green": "🟢", "amber": "🟡", "red": "🔴", "na": "⚪", None: "⚪"}

SOURCE_BADGE = {
    "news_extraction": "📰 Live News",
    "screener":        "🔍 Screener",
    "yfinance":        "⚠️ Yahoo Finance",
    None:              "—",
}
GRADE_EMOJI  = {
    "Strong": "🟢", "Moderate": "🟡", "Weak": "🔴",
    "Bullish": "🟢", "Neutral": "🟡", "Bearish": "🔴",
    "Undervalued": "🟢", "Fair": "🟡", "Overvalued": "🔴",
    "Low": "🟢", "Moderate Risk": "🟡", "High": "🔴",
    "Positive": "🟢", "Mixed": "🟡", "Negative": "🔴",
}
REC_EMOJI = {
    "Strong Buy": "🚀", "Buy": "🟢", "Hold": "🟡",
    "Reduce": "🟠", "Exit": "🔴",
}


def render_stock_detail_view(ticker: str, stock_data: dict) -> None:
    """
    SKILL-P02: Render Stock Detail & Scorecard View.
    Full drilldown for a selected holding.
    """
    company  = stock_data.get("company_name", ticker)
    rec      = stock_data.get("recommendation", "Hold")
    score    = stock_data.get("overall_score", 0)
    cp       = stock_data.get("current_price", 0)
    bp       = stock_data.get("buy_price", 0)
    qty      = stock_data.get("quantity", 0)
    val      = stock_data.get("holding_value", 0)
    sl       = stock_data.get("stop_loss", {})
    metrics  = stock_data.get("metrics", {})
    bd       = stock_data.get("score_breakdown", {})

    # ── Header ────────────────────────────────────────────────────────────────
    st.title(f"{REC_EMOJI.get(rec, '⚪')} {company} ({ticker})")
    st.caption(f"{stock_data.get('sector', '')}  |  Overall Score: **{score:.1f} / 100**  |  Recommendation: **{rec}**")

    # ── Top Metrics ───────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Current Price",  f"₹{cp:,.2f}")
    col2.metric("Buy Price",      f"₹{bp:,.2f}")
    col3.metric("Quantity",       f"{qty:,.0f}")
    col4.metric("Holding Value",  format_inr(val))
    drawdown = sl.get("current_drawdown_pct", 0) or 0
    col5.metric("Drawdown",       f"{drawdown:.1f}%",
                delta_color="inverse")

    st.divider()

    # ── Scorecard Cards ───────────────────────────────────────────────────────
    st.subheader("📋 Scorecard Breakdown")
    _render_scorecard_cards(stock_data)
    st.divider()

    # ── Recommendation ────────────────────────────────────────────────────────
    st.subheader("🎯 Recommendation Detail")
    rec_detail = stock_data.get("recommendation_detail", {})
    _render_recommendation_panel(rec_detail, sl)
    st.divider()

    # ── Key Metrics Table ─────────────────────────────────────────────────────
    st.subheader("📊 Key Metrics")
    _render_metrics_table(metrics, stock_data)
    st.divider()

    # ── News & Sentiment ──────────────────────────────────────────────────────
    st.subheader("📰 News & Sentiment")
    _render_news_sentiment(metrics, stock_data.get("news_headlines", []))


def _render_scorecard_cards(stock_data: dict) -> None:
    """Render 5 scorecard summary cards in a horizontal row."""
    f = stock_data.get("fundamental_score", {})
    t = stock_data.get("technical_score",   {})
    v = stock_data.get("valuation_score",   {})
    r = stock_data.get("risk_score",        {})
    s = stock_data.get("sentiment_score",   {})

    cards = [
        ("🏦 Fundamental", f.get("fundamental_score", 0), f.get("fundamental_grade", "—")),
        ("📈 Technical",   t.get("technical_score",   0), t.get("technical_grade",   "—")),
        ("💰 Valuation",   v.get("valuation_score",   0), v.get("valuation_grade",   "—")),
        ("⚠️ Risk",         r.get("risk_score",        0), r.get("risk_grade",        "—")),
        ("🗞️ Sentiment",   s.get("sentiment_scorecard_score", 0), s.get("sentiment_grade", "—")),
    ]

    cols = st.columns(5)
    for col, (label, score, grade) in zip(cols, cards):
        emoji = GRADE_EMOJI.get(grade, "⚪")
        col.metric(label, f"{score:.1f}", f"{emoji} {grade}")


def _render_recommendation_panel(rec_detail: dict, sl: dict) -> None:
    """Render recommendation with rationale and signals."""
    rec    = rec_detail.get("recommendation", "Hold")
    action = rec_detail.get("recommended_action", "")
    reason = rec_detail.get("recommendation_rationale", "")

    colour_fn = {
        "Strong Buy": st.success, "Buy": st.success,
        "Hold": st.info,
        "Reduce": st.warning, "Exit": st.error,
    }.get(rec, st.info)

    colour_fn(f"**{REC_EMOJI.get(rec, '')} {rec}** — {action}")

    if reason:
        st.write(reason)

    col1, col2 = st.columns(2)
    with col1:
        supporting = rec_detail.get("supporting_signals", [])
        if supporting:
            st.markdown("**✅ Supporting Signals**")
            for s in supporting[:4]:
                st.markdown(f"- {s}")
    with col2:
        contradicting = rec_detail.get("contradicting_signals", [])
        if contradicting:
            st.markdown("**⚠️ Risk Signals**")
            for c in contradicting[:4]:
                st.markdown(f"- {c}")

    # Stop-loss status
    sl_signal = sl.get("stop_loss_signal", "safe")
    sl_price  = sl.get("stop_loss_price", "—")
    prox      = sl.get("proximity_to_stop_pct")

    if sl_signal == "breached":
        st.error(f"🔴 **Stop-Loss Breached** — Stop at ₹{sl_price:,.2f}")
    elif sl_signal == "warning":
        st.warning(f"🟠 **Stop-Loss Warning** — {prox:.1f}% above stop at ₹{sl_price:,.2f}")
    else:
        st.success(f"🟢 Stop-Loss Safe — Stop at ₹{sl_price:,.2f}")


def _render_metrics_table(metrics: dict, stock_data: dict) -> None:
    """Render the full metrics detail table."""
    f = stock_data.get("fundamental_score", {})
    t = stock_data.get("technical_score",   {})
    v = stock_data.get("valuation_score",   {})
    r = stock_data.get("risk_score",        {})
    s = stock_data.get("sentiment_score",   {})

    def _fmt(val, suffix="", prefix="") -> str:
        if val is None: return "N/A"
        if isinstance(val, float): return f"{prefix}{val:,.2f}{suffix}"
        return f"{prefix}{val}{suffix}"

    rows = [
        # Fundamentals
        ("Revenue Growth (YoY)",  _fmt(metrics.get("revenue_growth_yoy"), "%"),
         _sig(f.get("fundamental_breakdown", {}).get("revenue"))),
        ("Net Profit Margin",     _fmt(metrics.get("net_margin"), "%"),
         _sig(f.get("fundamental_breakdown", {}).get("margin"))),
        ("Margin Trend",          str(metrics.get("margin_trend", "N/A")), "—"),
        ("Free Cash Flow",        _fmt(metrics.get("fcf"), " Cr") if metrics.get("fcf") else "N/A",
         _sig(f.get("fundamental_breakdown", {}).get("fcf"))),
        ("ROIC",                  _fmt(metrics.get("roic"), "%"),
         _sig(f.get("fundamental_breakdown", {}).get("roic"))),
        ("Promoter Holding",      _fmt(metrics.get("promoter_holding"), "%"),
         _sig(f.get("fundamental_breakdown", {}).get("promoter"))),
        # Valuation
        ("P/E Ratio",             _fmt(metrics.get("pe_ratio")),
         "—"),
        ("PEG Ratio",             _fmt(metrics.get("peg_ratio")),
         _sig(v.get("valuation_breakdown", {}).get("peg"))),
        ("EV/EBITDA",             _fmt(metrics.get("ev_ebitda")),
         _sig(v.get("valuation_breakdown", {}).get("ev_ebitda"))),
        # Technical
        ("Price vs 200D MA",      _fmt(stock_data.get("stop_loss", {}).get("current_drawdown_pct"), "%"),
         _sig(t.get("technical_breakdown", {}).get("trend"))),
        ("RSI (14-day)",          _fmt(metrics.get("rsi")),
         _sig(t.get("technical_breakdown", {}).get("rsi"))),
        ("Trend Signal",          str(metrics.get("trend", "N/A")).capitalize(), "—"),
        ("Momentum Score",        _fmt(metrics.get("momentum_score"), "/100"), "—"),
        ("Beta",                  _fmt(metrics.get("beta")),
         _sig(r.get("risk_breakdown", {}).get("beta"))),
        # Sentiment
        ("Sentiment Score",       _fmt(metrics.get("sentiment_score"), "/100"),
         "—"),
        ("Sentiment Label",       str(metrics.get("sentiment_label", "N/A")).capitalize(), "—"),
        ("FII Holding",           _fmt(metrics.get("fii_holding"), "%"), "—"),
        ("Analyst Recommendation",str(metrics.get("analyst_rec", "N/A") or "N/A").capitalize(), "—"),
        ("Analyst Target Price",  _fmt(metrics.get("analyst_target"), prefix="₹"), "—"),
    ]

    df = pd.DataFrame(rows, columns=["Metric", "Value", "Signal"])
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_news_sentiment(metrics: dict, headlines: list) -> None:
    """Render news sentiment and analyst coverage sections."""
    score  = metrics.get("sentiment_score", 50)
    label  = metrics.get("sentiment_label", "neutral")
    pos    = metrics.get("positive_themes", [])
    neg    = metrics.get("negative_themes", [])

    emoji  = {"positive": "🟢", "neutral": "🟡", "negative": "🔴"}.get(label, "⚪")
    st.metric("Sentiment Score", f"{score}/100", f"{emoji} {label.capitalize()}")

    col1, col2 = st.columns(2)
    with col1:
        if pos:
            st.markdown("**✅ Positive Themes**")
            for p in pos:
                st.markdown(f"- {p}")
    with col2:
        if neg:
            st.markdown("**⚠️ Negative Themes**")
            for n in neg:
                st.markdown(f"- {n}")

    if headlines:
        st.markdown("**Recent Headlines**")
        for h in headlines[:5]:
            st.markdown(
                f"- [{h.get('title', '')}]({h.get('url', '#')}) "
                f"*({h.get('source', '')} — "
                f"{str(h.get('published_date', ''))[:10]})*"
            )

    # ── Analyst Coverage ──────────────────────────────────────────────────────
    st.divider()
    st.markdown("**📊 Analyst Coverage**")
    _render_analyst_coverage(metrics)


def _render_analyst_coverage(metrics: dict) -> None:
    """
    Render analyst rating and target price with source badges.
    Shows source of each value — news extraction, screener, or yfinance.
    yfinance values are clearly flagged as fallback.
    """
    rec         = metrics.get("analyst_rec")
    rec_firm    = metrics.get("analyst_rec_firm")
    rec_source  = metrics.get("analyst_rec_source")
    rec_note    = metrics.get("analyst_rec_note")

    target      = metrics.get("analyst_target")
    tgt_source  = metrics.get("analyst_target_source")
    tgt_note    = metrics.get("analyst_target_note")

    target_mean = metrics.get("analyst_target_mean")
    target_low  = metrics.get("analyst_target_low")
    target_high = metrics.get("analyst_target_high")
    current     = metrics.get("current_price") or 0

    all_ratings = metrics.get("analyst_all_ratings", [])

    col1, col2, col3 = st.columns(3)

    # ── Rating ────────────────────────────────────────────────────────────────
    with col1:
        badge = SOURCE_BADGE.get(rec_source, "—")
        if rec:
            rec_emoji = {"buy": "🟢", "hold": "🟡", "sell": "🔴",
                         "strong_buy": "🚀", "underperform": "🟠"}.get(
                rec.lower() if rec else "", "⚪"
            )
            firm_str = f" ({rec_firm})" if rec_firm else ""
            st.metric("Analyst Rating", f"{rec_emoji} {rec}{firm_str}")
            st.caption(badge)
            if rec_note:
                st.warning(f"⚠️ {rec_note}", icon=None)
        else:
            st.metric("Analyst Rating", "N/A")
            st.caption("No coverage data available")

    # ── Target Price ──────────────────────────────────────────────────────────
    with col2:
        badge = SOURCE_BADGE.get(tgt_source, "—")
        if target:
            upside = ((target - current) / current * 100) if current else None
            upside_str = f"{upside:+.1f}%" if upside is not None else ""
            st.metric("Target Price", f"₹{target:,.0f}", upside_str)
            st.caption(badge)
            if tgt_note:
                st.warning(f"⚠️ {tgt_note}", icon=None)
        else:
            st.metric("Target Price", "N/A")
            st.caption("No target data available")

    # ── Target Range ──────────────────────────────────────────────────────────
    with col3:
        if target_low or target_mean or target_high:
            st.markdown("**Target Range** ⚠️ Yahoo Finance")
            if target_low:
                st.caption(f"Low:  ₹{target_low:,.0f}")
            if target_mean:
                st.caption(f"Mean: ₹{target_mean:,.0f}")
            if target_high:
                st.caption(f"High: ₹{target_high:,.0f}")
            st.warning("⚠️ Fallback — may not reflect latest analyst views")
        else:
            st.metric("Target Range", "N/A")
            st.caption("No range data available")

    # ── Individual Analyst Ratings from News ──────────────────────────────────
    if all_ratings:
        st.markdown("**📰 Analyst Signals Extracted from News**")
        rows = []
        for r in all_ratings:
            rows.append({
                "Firm":    r.get("firm") or "Unknown",
                "Rating":  r.get("rating") or "—",
                "Target":  f"₹{r.get('target_price'):,.0f}" if r.get("target_price") else "—",
                "Action":  r.get("action") or "—",
                "Source":  "📰 Live News",
            })
        import pandas as pd
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )


def _sig(signal: str | None) -> str:
    """Convert signal string to emoji."""
    return SIGNAL_EMOJI.get(signal, "⚪") + f" {signal or 'N/A'}".capitalize()