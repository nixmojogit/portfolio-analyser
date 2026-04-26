"""
app.py
Entry point for the Portfolio Analyser Streamlit application.
Run with: streamlit run app.py
"""

import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.layers.configuration.config_manager import load_config
from src.layers.action.orchestrator import run_g1_workflow
from src.layers.presentation.dashboard import render_portfolio_overview, render_alerts_panel
from src.layers.presentation.stock_detail_view import render_stock_detail_view
from src.layers.presentation.portfolio_view import render_opportunities_view
from src.utils.logger import setup_root_logger

# -- App Config ----------------------------------------------------------------

st.set_page_config(
    page_title="Portfolio Analyser",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

setup_root_logger("INFO")

PORTFOLIO_DB = Path("data/portfolio/portfolio.db")
INPUT_DIR    = Path("data/input")
LAST_RESULTS = Path("data/portfolio/last_results.json")

# -- Global CSS ----------------------------------------------------------------

st.markdown("""
<style>
div[data-testid="metric-container"] {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    padding: 6px 10px;
}
div[data-testid="metric-container"] > label {
    font-size: 0.68rem !important;
    color: #6c757d !important;
    text-transform: uppercase;
    letter-spacing: 0.03em;
}
div[data-testid="metric-container"] > div {
    font-size: 0.95rem !important;
    font-weight: 600;
}
button[data-baseweb="tab"] {
    font-size: 0.85rem;
    padding: 6px 16px;
}
section[data-testid="stSidebar"] .stCaption {
    font-size: 0.72rem;
}
div[data-testid="stAlert"] {
    padding: 6px 12px;
    font-size: 0.8rem;
}
</style>
""", unsafe_allow_html=True)


# -- Persistence Helpers -------------------------------------------------------

def _save_results(results: dict) -> None:
    """Persist full analysis results to disk after every run."""
    try:
        LAST_RESULTS.parent.mkdir(parents=True, exist_ok=True)

        def _clean(obj):
            if isinstance(obj, dict):  return {k: _clean(v) for k, v in obj.items()}
            if isinstance(obj, list):  return [_clean(v) for v in obj]
            if isinstance(obj, float):
                return None if (math.isnan(obj) or math.isinf(obj)) else obj
            try:
                import numpy as np
                if isinstance(obj, np.integer):  return int(obj)
                if isinstance(obj, np.floating):
                    return None if (math.isnan(float(obj)) or math.isinf(float(obj))) else float(obj)
                if isinstance(obj, np.ndarray):  return obj.tolist()
            except ImportError:
                pass
            try:
                import pandas as pd
                if isinstance(obj, pd.Timestamp): return obj.isoformat()
                if isinstance(obj, pd.DataFrame): return None
            except ImportError:
                pass
            return obj

        with open(LAST_RESULTS, "w") as f:
            json.dump(_clean(results), f, default=str)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not save results: {e}")


def _load_results() -> dict | None:
    try:
        if not LAST_RESULTS.exists():
            return None
        with open(LAST_RESULTS) as f:
            return json.load(f)
    except Exception:
        return None


def _results_age(results: dict) -> str:
    try:
        ts  = results.get("run_timestamp")
        if not ts: return "unknown"
        dt  = datetime.fromisoformat(ts)
        ago = datetime.now() - dt
        h   = int(ago.total_seconds() // 3600)
        m   = int((ago.total_seconds() % 3600) // 60)
        if h >= 24: return f"{h // 24}d ago"
        if h  >  0: return f"{h}h {m}m ago"
        return f"{m}m ago"
    except Exception:
        return "unknown"


# -- Portfolio DB Helpers ------------------------------------------------------

def _holdings_count() -> int:
    try:
        with sqlite3.connect(PORTFOLIO_DB) as conn:
            return conn.execute("SELECT COUNT(*) FROM holdings").fetchone()[0]
    except Exception:
        return 0


def _run_portfolio_import(uploaded_file, config: dict) -> None:
    """
    Import portfolio from Excel. Permanent loop guard: uses a unique key
    based on filename + filesize to prevent re-importing the same file
    on Streamlit reruns. Re-importing a genuinely updated file (different
    size) always works correctly.
    """
    from src.layers.data.fundamentals_module import import_portfolio_from_excel

    # Loop guard -- skip if this exact file was already imported this session
    file_key = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("_last_import_key") == file_key:
        return

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_path = INPUT_DIR / "portfolio.xlsx"
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    with st.spinner("Importing portfolio ..."):
        result = import_portfolio_from_excel(str(save_path), config)

    status = result.get("import_status", "failed")
    errors = result.get("validation_errors", [])
    df     = result.get("holdings_df")

    if status == "success":
        st.session_state["_last_import_key"] = file_key
        st.success(f"✅ {len(df)} holding(s) imported successfully.")
        st.session_state["analysis_results"] = None
        st.rerun()
    elif status == "partial":
        st.session_state["_last_import_key"] = file_key
        st.warning(f"⚠️ {len(df)} holding(s) imported with warnings.")
        for e in errors: st.caption(f"• {e}")
        st.session_state["analysis_results"] = None
        st.rerun()
    else:
        st.error("❌ Import failed.")
        for e in errors: st.caption(f"• {e}")


# -- Discovery Stock Data Builder ----------------------------------------------

def _build_discovery_stock_data(candidate: dict) -> dict:
    """
    Build a stock_data dict compatible with render_stock_detail_view
    from a G2 discovery candidate. Uses real metrics computed during
    evaluate_candidate() if available.
    """
    ticker = candidate.get("ticker", "")
    score  = candidate.get("overall_score") or candidate.get("peer_score") or 0
    tag    = candidate.get("action_tag", "Initiate")
    rat    = candidate.get("rationale", {})

    def _grade_score(grade, mapping):
        return mapping.get(grade, 50.0)

    f_score = _grade_score(candidate.get("fundamental_grade"), {"Strong": 75, "Moderate": 50, "Weak": 20})
    t_score = _grade_score(candidate.get("technical_grade"),   {"Bullish": 75, "Neutral": 50, "Bearish": 20})
    v_score = _grade_score(candidate.get("valuation_grade"),   {"Undervalued": 75, "Fair": 50, "Overvalued": 20})
    r_score = _grade_score(candidate.get("risk_grade"),        {"Low": 75, "Moderate": 50, "High": 20})
    s_score = _grade_score(candidate.get("sentiment_grade"),   {"Positive": 75, "Mixed": 50, "Negative": 20})

    # Use real metrics from evaluate_candidate() if present
    raw_metrics = candidate.get("metrics", {})

    return {
        "ticker":        ticker,
        "company_name":  ticker.replace(".NS", "").replace(".BO", ""),
        "sector":        candidate.get("sector", "-"),
        "current_price": raw_metrics.get("current_price"),
        "buy_price":     None,
        "quantity":      0,
        "holding_value": 0,
        "concentration_pct": 0,
        "overall_score": score,
        "recommendation": tag,
        "score_breakdown": {
            "fundamental": {"score": f_score, "weight": 0.30},
            "valuation":   {"score": v_score, "weight": 0.25},
            "technical":   {"score": t_score, "weight": 0.20},
            "sentiment":   {"score": s_score, "weight": 0.15},
            "risk":        {"score": r_score, "weight": 0.10},
        },
        "fundamental_score": {
            "fundamental_score": f_score,
            "fundamental_grade": candidate.get("fundamental_grade", "-"),
            "fundamental_breakdown": candidate.get("fundamental_breakdown", {}),
        },
        "technical_score": {
            "technical_score": t_score,
            "technical_grade": candidate.get("technical_grade", "-"),
            "technical_breakdown": candidate.get("technical_breakdown", {}),
        },
        "valuation_score": {
            "valuation_score": v_score,
            "valuation_grade": candidate.get("valuation_grade", "-"),
            "valuation_breakdown": candidate.get("valuation_breakdown", {}),
        },
        "risk_score": {
            "risk_score": r_score,
            "risk_grade": candidate.get("risk_grade", "-"),
            "risk_breakdown": candidate.get("risk_breakdown", {}),
        },
        "sentiment_score": {
            "sentiment_scorecard_score": s_score,
            "sentiment_grade": candidate.get("sentiment_grade", "-"),
            "sentiment_breakdown": candidate.get("sentiment_breakdown", {}),
        },
        "stop_loss": {
            "stop_loss_price": None, "stop_loss_method": "-",
            "atr_value": None, "equivalent_stop_pct": None,
            "current_drawdown_pct": None, "proximity_to_stop_pct": None,
            "stop_loss_signal": "safe",
        },
        "thesis_intact": True,
        "recommendation_detail": {
            "recommendation":           tag,
            "recommendation_rationale": rat.get("summary", ""),
            "supporting_signals":       rat.get("strengths", []),
            "contradicting_signals":    rat.get("risks", []),
            "recommended_action":       rat.get("action", ""),
            "base_recommendation":      tag,
            "override_applied":         False,
        },
        "metrics": {
            **raw_metrics,
            # Ensure all expected keys exist with safe fallbacks
            "sentiment_score":       raw_metrics.get("sentiment_score", s_score),
            "sentiment_label":       raw_metrics.get("sentiment_label", "neutral"),
            "positive_themes":       raw_metrics.get("positive_themes", []),
            "negative_themes":       raw_metrics.get("negative_themes", []),
            "analyst_rec":           raw_metrics.get("analyst_rec"),
            "analyst_rec_firm":      raw_metrics.get("analyst_rec_firm"),
            "analyst_rec_source":    raw_metrics.get("analyst_rec_source"),
            "analyst_rec_note":      raw_metrics.get("analyst_rec_note"),
            "analyst_target":        raw_metrics.get("analyst_target"),
            "analyst_target_source": raw_metrics.get("analyst_target_source"),
            "analyst_target_note":   raw_metrics.get("analyst_target_note"),
            "analyst_target_mean":   raw_metrics.get("analyst_target_mean"),
            "analyst_target_low":    raw_metrics.get("analyst_target_low"),
            "analyst_target_high":   raw_metrics.get("analyst_target_high"),
            "analyst_all_ratings":   raw_metrics.get("analyst_all_ratings", []),
            "current_price":         raw_metrics.get("current_price"),
        },
        "news_headlines":     [],
        "portfolio_action":   tag,
        "net_recommendation": tag,
        "net_reason":         rat.get("action", ""),
        "run_timestamp":      None,
    }


# -- Session State -------------------------------------------------------------

if "config" not in st.session_state:
    st.session_state["config"] = load_config()

if "selected_ticker" not in st.session_state:
    st.session_state["selected_ticker"] = None

if "analysis_results" not in st.session_state:
    st.session_state["analysis_results"] = _load_results()
    st.session_state["_from_disk"] = st.session_state["analysis_results"] is not None


# -- Sidebar -------------------------------------------------------------------

with st.sidebar:

    st.markdown("## 📈 Portfolio Analyser")
    st.caption("AI-powered · Indian Stock Market · NSE / BSE")
    st.divider()

    holdings_count = _holdings_count()
    analysis       = st.session_state.get("analysis_results")

    col_a, col_b = st.columns(2)
    col_a.metric("Holdings", holdings_count if holdings_count else "-")
    col_b.metric("Last Run", _results_age(analysis) if analysis else "Never")

    st.divider()

    if holdings_count == 0:
        st.markdown("**Import your portfolio to begin:**")
        up = st.file_uploader(
            "Upload portfolio.xlsx", type=["xlsx"], key="initial_uploader",
            help="Required: Ticker, Company Name, Sector, Buy Price, Quantity"
        )
        if up:
            _run_portfolio_import(up, st.session_state["config"])
        st.caption(
            "Required columns: Ticker, Company Name, Sector, Buy Price, Quantity\n\n"
            "Optional: Stop Loss %, Investment Thesis\n\n"
            "Tickers without .NS/.BO default to NSE."
        )
    else:
        with st.expander("📂 Import / Update Portfolio"):
            st.caption("Upload a new Excel file to update your holdings.")
            up = st.file_uploader(
                "portfolio.xlsx", type=["xlsx"], key="reimport_uploader",
                label_visibility="collapsed"
            )
            if up:
                _run_portfolio_import(up, st.session_state["config"])

    st.divider()

    run_disabled = holdings_count == 0
    if st.button(
        "🔄  Run Portfolio Analysis",
        use_container_width=True,
        type="primary",
        disabled=run_disabled,
    ):
        with st.spinner("Running portfolio analysis ..."):
            config  = st.session_state["config"]
            results = run_g1_workflow(config)
            st.session_state["analysis_results"] = results
            st.session_state["selected_ticker"]  = None
            st.session_state["_from_disk"]        = False
            _save_results(results)

        g1 = len(results.get("results", {}))
        g2 = len(results.get("g2_results", {}).get("new_ideas", []))
        g3 = len(results.get("g3_results", {}).get("rebalancing_plan", []))
        er = len(results.get("errors", {}))

        if er == 0:
            st.success(
                f"✅ Analysis complete - {g1} stocks scored, "
                f"{g2} new ideas found, {g3} rebalancing actions."
            )
        else:
            st.warning(
                f"⚠️ Completed with {er} error(s). "
                f"Stocks: {g1} | Ideas: {g2} | Actions: {g3}"
            )
        st.rerun()

    if run_disabled:
        st.caption("Import your portfolio above to enable analysis.")

    if analysis and st.session_state.get("_from_disk"):
        st.caption("📂 Displaying saved results - click Run to refresh.")

    st.divider()
    st.caption("**Portfolio Analyser v1.0**\n\nNSE / BSE · AI-powered scoring")


# -- Main Content --------------------------------------------------------------

config    = st.session_state["config"]
analysis  = st.session_state.get("analysis_results")
sel       = st.session_state.get("selected_ticker")

g1_results = analysis.get("results",    {}) if analysis else {}
g2_results = analysis.get("g2_results", {}) if analysis else {}
g3_results = analysis.get("g3_results", {}) if analysis else {}

tab1, tab2 = st.tabs(["📊  Portfolio Overview", "📋  Stock Details"])

with tab1:
    render_portfolio_overview(config, analysis, g2_results)

with tab2:
    # Stock Details tab -- holdings and discovery stocks in one selector
    if g1_results or g2_results.get("new_ideas"):
        st.markdown("#### Stock Detail")

        options: dict[str, tuple] = {}

        # Existing holdings
        for t, r in sorted(g1_results.items()):
            short = t.replace(".NS", "").replace(".BO", "")
            options[short] = (t, r)

        # Discovery stocks
        for c in g2_results.get("new_ideas", []):
            t     = c.get("ticker", "")
            short = t.replace(".NS", "").replace(".BO", "")
            tag   = c.get("action_tag", "")
            label = f"{short} 💡 {tag}"
            options[label] = (t, _build_discovery_stock_data(c))

        labels  = list(options.keys())
        default = labels[0] if labels else None
        if sel:
            for lbl, (t, _) in options.items():
                if t == sel:
                    default = lbl
                    break

        chosen = st.selectbox(
            "Select stock",
            labels,
            index=labels.index(default) if default in labels else 0,
            label_visibility="collapsed",
        )

        if chosen and chosen in options:
            chosen_ticker, chosen_data = options[chosen]
            st.session_state["selected_ticker"] = chosen_ticker
            render_stock_detail_view(chosen_ticker, chosen_data)
    else:
        st.info("Run Portfolio Analysis to view stock details.")