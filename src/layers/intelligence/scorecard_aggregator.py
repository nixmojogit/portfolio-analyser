"""
scorecard_aggregator.py
Layer      : Intelligence
Owns       : SKILL-I21, SKILL-I22, SKILL-I23, SKILL-I24, SKILL-I25, SKILL-I26
Description: Aggregates individual metric signals into five scorecard scores
             and combines them into a single Overall Stock Score (0-100).
             All weights loaded from scorecard_weights.yaml.
             Signal-to-score mapping: green->80, amber->50, red->15, na->excluded
"""

from __future__ import annotations
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

# Default signal-to-score mapping
SIGNAL_SCORES = {"green": 80.0, "amber": 50.0, "red": 15.0}

# Default scorecard weights
DEFAULT_WEIGHTS = {
    "fundamental": 0.30,
    "valuation":   0.25,
    "technical":   0.20,
    "sentiment":   0.15,
    "risk":        0.10,
}

# Default recommendation thresholds
DEFAULT_REC_THRESHOLDS = {
    "strong_buy": 75,
    "buy":        55,
    "hold":       35,
    "reduce":     20,
    "exit":       0,
}


# ── Core Utilities ────────────────────────────────────────────────────────────

def _signal_to_score(signal: str, config: dict | None = None) -> float | None:
    """
    Convert a green/amber/red signal string to a numeric sub-score.
    Returns None for 'na' or unknown signals (excluded from average).
    """
    scores = (config or {}).get("scorecard_weights", {}).get(
        "signal_scores", SIGNAL_SCORES
    )
    val = scores.get(signal.lower() if signal else "na")
    return float(val) if val is not None else None


def _aggregate_signals(
    signal_dict: dict[str, str | float],
    config: dict | None = None,
) -> float:
    """
    Convert a dict of signal strings or numeric scores to a weighted average.
    N/A signals are excluded from the average — not penalised.
    Args:
        signal_dict : dict of metric_name -> signal string or float score
        config      : merged config dict
    Returns: weighted average score (float 0-100), defaults to 50 if all N/A
    """
    scores = []
    for key, val in signal_dict.items():
        if isinstance(val, (int, float)):
            scores.append(float(val))
        elif isinstance(val, str):
            s = _signal_to_score(val, config)
            if s is not None:
                scores.append(s)
        # None / "na" excluded silently

    if not scores:
        return 50.0   # neutral default when all signals are N/A

    return round(sum(scores) / len(scores), 4)


def _score_to_grade(score: float, grade_map: dict) -> str:
    """Map a numeric score to a grade string using a threshold dict."""
    keys = list(grade_map.keys())
    # Expect format: {high_label: cutoff, mid_label: cutoff, low_label: cutoff}
    values = list(grade_map.values())
    if score >= values[0]:
        return keys[0]
    elif score >= values[1]:
        return keys[1]
    else:
        return keys[2]


def _score_to_recommendation(score: float, config: dict | None = None) -> str:
    """
    Map an overall score (0-100) to a recommendation string.
    Thresholds from scorecard_weights.yaml.
    """
    t = (config or {}).get("scorecard_weights", {}).get(
        "recommendation_thresholds", DEFAULT_REC_THRESHOLDS
    )
    if score >= t.get("strong_buy", 75):  return "Strong Buy"
    if score >= t.get("buy",        55):  return "Buy"
    if score >= t.get("hold",       35):  return "Hold"
    if score >= t.get("reduce",     20):  return "Reduce"
    return "Exit"


# ── SKILL-I21: Fundamental Scorecard ─────────────────────────────────────────

def compute_fundamental_score(
    revenue_signal: str,
    margin_signal: str,
    fcf_signal: str,
    roic_signal: str,
    promoter_signal: str,
    surprise_signal: str,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I21: Compute Fundamental Scorecard Score (0-100).
    Aggregates fundamental metric signals. N/A signals excluded from average.
    Args:
        revenue_signal   : from SKILL-I07
        margin_signal    : from SKILL-I08
        fcf_signal       : from SKILL-I09
        roic_signal      : from SKILL-I13
        promoter_signal  : from SKILL-I17
        surprise_signal  : from SKILL-I15
        config           : merged config dict
    Returns: dict with fundamental_score, fundamental_grade, fundamental_breakdown
    """
    breakdown = {
        "revenue":   revenue_signal,
        "margin":    margin_signal,
        "fcf":       fcf_signal,
        "roic":      roic_signal,
        "promoter":  promoter_signal,
        "surprise":  surprise_signal if surprise_signal != "na" else None,
    }

    score = _aggregate_signals(
        {k: v for k, v in breakdown.items() if v is not None},
        config,
    )

    t = (config or {}).get("scorecard_weights", {}).get("grade_cutoffs", {}).get(
        "fundamental", {"strong_above": 65, "moderate_above": 35, "weak_below": 35}
    )
    if score >= t.get("strong_above", 65):   grade = "Strong"
    elif score >= t.get("moderate_above", 35): grade = "Moderate"
    else:                                      grade = "Weak"

    log.debug(f"[SKILL-I21] Fundamental score={score} grade={grade}")
    return {
        "fundamental_score":     score,
        "fundamental_grade":     grade,
        "fundamental_breakdown": breakdown,
    }


# ── SKILL-I22: Technical Scorecard ───────────────────────────────────────────

def compute_technical_score(
    trend_signal: str,
    rsi_signal: str,
    macd_signal: str,
    momentum_score: float,
    volume_signal: str,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I22: Compute Technical Scorecard Score (0-100).
    Args:
        trend_signal   : from SKILL-I01 ('bullish'|'neutral'|'bearish')
        rsi_signal     : from SKILL-I02 ('oversold'|'neutral'|'overbought')
        macd_signal    : from SKILL-I03
        momentum_score : from SKILL-I05 (already 0-100)
        volume_signal  : from SKILL-I06
        config         : merged config dict
    Returns: dict with technical_score, technical_grade, technical_breakdown
    """
    # Map non-standard signals to green/amber/red
    trend_mapped = {
        "bullish": "green", "neutral": "amber", "bearish": "red"
    }.get(trend_signal, "amber")

    rsi_mapped = {
        "oversold": "green",    # oversold = buying opportunity
        "neutral":  "amber",
        "overbought": "red",
    }.get(rsi_signal, "amber")

    macd_mapped = {
        "bullish_crossover": "green",
        "neutral":           "amber",
        "bearish_crossover": "red",
    }.get(macd_signal, "amber")

    vol_mapped = {
        "high_conviction": "green",
        "normal":          "amber",
        "low_conviction":  "red",
    }.get(volume_signal, "amber")

    breakdown = {
        "trend":    trend_mapped,
        "rsi":      rsi_mapped,
        "macd":     macd_mapped,
        "volume":   vol_mapped,
        "momentum": momentum_score,   # numeric — used directly
    }

    score = _aggregate_signals(breakdown, config)

    t = (config or {}).get("scorecard_weights", {}).get("grade_cutoffs", {}).get(
        "technical", {"bullish_above": 65, "neutral_above": 35, "bearish_below": 35}
    )
    if score >= t.get("bullish_above", 65):   grade = "Bullish"
    elif score >= t.get("neutral_above", 35): grade = "Neutral"
    else:                                      grade = "Bearish"

    log.debug(f"[SKILL-I22] Technical score={score} grade={grade}")
    return {
        "technical_score":     score,
        "technical_grade":     grade,
        "technical_breakdown": breakdown,
    }


# ── SKILL-I23: Valuation Scorecard ───────────────────────────────────────────

def compute_valuation_score(
    peg_signal: str,
    pe_vs_sector_signal: str,
    ev_ebitda_signal: str,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I23: Compute Valuation Scorecard Score (0-100).
    Higher score = more attractive valuation.
    Args:
        peg_signal          : from SKILL-I10 ('undervalued'|'fair'|'overvalued'|'na')
        pe_vs_sector_signal : from SKILL-I11 ('discount'|'inline'|'premium'|'na')
        ev_ebitda_signal    : from SKILL-I12 ('green'|'amber'|'red'|'na')
        config              : merged config dict
    Returns: dict with valuation_score, valuation_grade, valuation_breakdown
    """
    # Map valuation-specific signals to green/amber/red
    peg_mapped = {
        "undervalued": "green", "fair": "amber",
        "overvalued":  "red",   "na":   None,
    }.get(peg_signal, None)

    pe_mapped = {
        "discount": "green", "inline": "amber",
        "premium":  "red",   "na":     None,
    }.get(pe_vs_sector_signal, None)

    breakdown = {
        "peg":        peg_mapped,
        "pe_sector":  pe_mapped,
        "ev_ebitda":  ev_ebitda_signal if ev_ebitda_signal != "na" else None,
    }

    score = _aggregate_signals(
        {k: v for k, v in breakdown.items() if v is not None},
        config,
    )

    t = (config or {}).get("scorecard_weights", {}).get("grade_cutoffs", {}).get(
        "valuation", {"undervalued_above": 65, "fair_above": 35, "overvalued_below": 35}
    )
    if score >= t.get("undervalued_above", 65): grade = "Undervalued"
    elif score >= t.get("fair_above",       35): grade = "Fair"
    else:                                         grade = "Overvalued"

    log.debug(f"[SKILL-I23] Valuation score={score} grade={grade}")
    return {
        "valuation_score":     score,
        "valuation_grade":     grade,
        "valuation_breakdown": breakdown,
    }


# ── SKILL-I24: Risk Scorecard ─────────────────────────────────────────────────

def compute_risk_score(
    beta: float | None,
    stop_loss_proximity_pct: float | None,
    portfolio_concentration_pct: float | None,
    debt_equity: float | None,
    pledge_pct: float | None,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I24: Compute Risk Scorecard Score (0-100). Higher = lower risk.
    Args:
        beta                       : from SKILL-I04
        stop_loss_proximity_pct    : from SKILL-I31
        portfolio_concentration_pct: stock weight in portfolio (%)
        debt_equity                : D/E ratio (from SKILL-D04)
        pledge_pct                 : promoter pledge % (from SKILL-D08)
        config                     : merged config dict
    Returns: dict with risk_score, risk_grade, risk_breakdown
    """
    breakdown: dict[str, str | None] = {}

    # Beta signal
    if beta is not None:
        bt = (config or {}).get("thresholds", {}).get("beta", {})
        if beta < bt.get("low_below", 0.8):
            breakdown["beta"] = "green"
        elif beta <= bt.get("moderate_below", 1.2):
            breakdown["beta"] = "amber"
        else:
            breakdown["beta"] = "red"

    # Stop-loss proximity
    if stop_loss_proximity_pct is not None:
        warning = (config or {}).get("thresholds", {}).get(
            "stop_loss_warning_proximity_pct", 3
        )
        if stop_loss_proximity_pct <= 0:
            breakdown["stop_loss"] = "red"
        elif stop_loss_proximity_pct <= warning:
            breakdown["stop_loss"] = "amber"
        else:
            breakdown["stop_loss"] = "green"

    # Portfolio concentration
    if portfolio_concentration_pct is not None:
        ct = (config or {}).get("thresholds", {}).get("portfolio_concentration_pct", {})
        if portfolio_concentration_pct < ct.get("green_below", 5):
            breakdown["concentration"] = "green"
        elif portfolio_concentration_pct < ct.get("amber_below", 10):
            breakdown["concentration"] = "amber"
        else:
            breakdown["concentration"] = "red"

    # Debt/Equity
    if debt_equity is not None:
        de = debt_equity / 100 if debt_equity > 10 else debt_equity  # yfinance returns as ratio
        dt = (config or {}).get("thresholds", {}).get("debt_to_equity", {})
        if de < dt.get("green_below", 0.5):
            breakdown["debt_equity"] = "green"
        elif de < dt.get("amber_below", 1.5):
            breakdown["debt_equity"] = "amber"
        else:
            breakdown["debt_equity"] = "red"

    # Pledge
    if pledge_pct is not None:
        pt = (config or {}).get("thresholds", {}).get("promoter_pledge_pct", {})
        if pledge_pct < pt.get("green_below", 10):
            breakdown["pledge"] = "green"
        elif pledge_pct < pt.get("amber_below", 30):
            breakdown["pledge"] = "amber"
        else:
            breakdown["pledge"] = "red"

    score = _aggregate_signals(
        {k: v for k, v in breakdown.items() if v is not None},
        config,
    )

    t = (config or {}).get("scorecard_weights", {}).get("grade_cutoffs", {}).get(
        "risk", {"low_above": 65, "moderate_above": 35, "high_below": 35}
    )
    if score >= t.get("low_above",      65): grade = "Low"
    elif score >= t.get("moderate_above", 35): grade = "Moderate"
    else:                                       grade = "High"

    log.debug(f"[SKILL-I24] Risk score={score} grade={grade}")
    return {
        "risk_score":     score,
        "risk_grade":     grade,
        "risk_breakdown": breakdown,
    }


# ── SKILL-I25: Sentiment Scorecard ───────────────────────────────────────────

def compute_sentiment_score(
    news_sentiment_score: float | None,
    insider_signal: str,
    institutional_signal: str,
    analyst_recommendation: str | None,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I25: Compute Sentiment Scorecard Score (0-100).
    Args:
        news_sentiment_score   : float 0-100 from SKILL-I18 (or None)
        insider_signal         : from SKILL-I19
        institutional_signal   : from SKILL-I20
        analyst_recommendation : string from SKILL-D04 (or None)
        config                 : merged config dict
    Returns: dict with sentiment_scorecard_score, sentiment_grade,
             sentiment_breakdown
    """
    breakdown: dict[str, Any] = {}

    # News sentiment — convert 0-100 score directly
    if news_sentiment_score is not None:
        breakdown["news_sentiment"] = float(news_sentiment_score)

    # Insider signal — already green/amber/red
    if insider_signal and insider_signal not in ("na", "neutral"):
        ins_mapped = {
            "green": "green", "amber": "amber", "red": "red"
        }.get(insider_signal, "amber")
        breakdown["insider"] = ins_mapped
    elif insider_signal == "neutral":
        breakdown["insider"] = "amber"

    # Institutional signal
    if institutional_signal and institutional_signal not in ("na",):
        inst_mapped = {
            "green": "green", "amber": "amber", "red": "red"
        }.get(institutional_signal, "amber")
        breakdown["institutional"] = inst_mapped

    # Analyst recommendation
    if analyst_recommendation:
        rec_lower = analyst_recommendation.lower()
        if rec_lower in ("strong_buy", "buy"):
            breakdown["analyst"] = "green"
        elif rec_lower in ("hold", "neutral"):
            breakdown["analyst"] = "amber"
        elif rec_lower in ("sell", "underperform", "strong_sell"):
            breakdown["analyst"] = "red"

    score = _aggregate_signals(
        {k: v for k, v in breakdown.items() if v is not None},
        config,
    )

    t = (config or {}).get("scorecard_weights", {}).get("grade_cutoffs", {}).get(
        "sentiment", {"positive_above": 65, "mixed_above": 35, "negative_below": 35}
    )
    if score >= t.get("positive_above", 65): grade = "Positive"
    elif score >= t.get("mixed_above",   35): grade = "Mixed"
    else:                                      grade = "Negative"

    log.debug(f"[SKILL-I25] Sentiment score={score} grade={grade}")
    return {
        "sentiment_scorecard_score": score,
        "sentiment_grade":           grade,
        "sentiment_breakdown":       breakdown,
    }


# ── SKILL-I26: Overall Stock Score ───────────────────────────────────────────

def compute_overall_stock_score(
    fundamental_score: float,
    technical_score: float,
    valuation_score: float,
    risk_score: float,
    sentiment_scorecard_score: float,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-I26: Compute Overall Stock Score (0-100).
    Combines all five scorecard scores using configurable weights.
    Maps score to a recommendation action.
    Default weights: Fundamental 30%, Valuation 25%, Technical 20%,
                     Sentiment 15%, Risk 10%
    Args:
        fundamental_score         : from SKILL-I21
        technical_score           : from SKILL-I22
        valuation_score           : from SKILL-I23
        risk_score                : from SKILL-I24
        sentiment_scorecard_score : from SKILL-I25
        config                    : merged config dict
    Returns: dict with overall_score, recommendation, score_breakdown
    """
    weights = (config or {}).get("scorecard_weights", {}).get(
        "overall_score_weights", DEFAULT_WEIGHTS
    )

    w_f = weights.get("fundamental", 0.30)
    w_v = weights.get("valuation",   0.25)
    w_t = weights.get("technical",   0.20)
    w_s = weights.get("sentiment",   0.15)
    w_r = weights.get("risk",        0.10)

    overall = round(
        fundamental_score         * w_f +
        valuation_score           * w_v +
        technical_score           * w_t +
        sentiment_scorecard_score * w_s +
        risk_score                * w_r,
        4,
    )

    recommendation = _score_to_recommendation(overall, config)

    score_breakdown = {
        "fundamental": {"score": fundamental_score,         "weight": w_f},
        "valuation":   {"score": valuation_score,           "weight": w_v},
        "technical":   {"score": technical_score,           "weight": w_t},
        "sentiment":   {"score": sentiment_scorecard_score, "weight": w_s},
        "risk":        {"score": risk_score,                "weight": w_r},
    }

    log.info(
        f"[SKILL-I26] Overall score={overall} → {recommendation} | "
        f"F={fundamental_score:.1f} V={valuation_score:.1f} "
        f"T={technical_score:.1f} S={sentiment_scorecard_score:.1f} "
        f"R={risk_score:.1f}"
    )

    return {
        "overall_score":    overall,
        "recommendation":   recommendation,
        "score_breakdown":  score_breakdown,
    }