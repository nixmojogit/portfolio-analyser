"""
recommendation_engine.py
Layer      : Action
Owns       : SKILL-A01
Description: Applies three-layer decision matrix to scorecard outputs
             to generate final Buy/Hold/Reduce/Exit recommendations
             for existing portfolio holdings (Goal 1).
             Stop-loss breach and thesis integrity override all scores.
"""

from __future__ import annotations
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)


def generate_stock_recommendation(
    overall_score: float,
    fundamental_grade: str,
    technical_grade: str,
    sentiment_grade: str,
    stop_loss_signal: str,
    thesis_intact: bool,
    score_breakdown: dict,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-A01: Generate Stock Recommendation.
    Applies decision matrix to produce a final recommendation.
    Override rules (in priority order):
      1. Stop-loss breached → Exit
      2. Thesis broken → Reduce (unless already Exit)
      3. Score-based recommendation from SKILL-I26
    Args:
        overall_score    : float 0-100 from SKILL-I26
        fundamental_grade: 'Strong'|'Moderate'|'Weak'
        technical_grade  : 'Bullish'|'Neutral'|'Bearish'
        sentiment_grade  : 'Positive'|'Mixed'|'Negative'
        stop_loss_signal : 'safe'|'warning'|'breached'
        thesis_intact    : bool from portfolio config
        score_breakdown  : dict of scorecard scores
        config           : merged config dict
    Returns: dict with recommendation, recommendation_rationale,
             supporting_signals, contradicting_signals, recommended_action
    """
    # ── Score-based recommendation ────────────────────────────────────────────
    t = (config or {}).get("scorecard_weights", {}).get(
        "recommendation_thresholds",
        {"strong_buy": 75, "buy": 55, "hold": 35, "reduce": 20}
    )
    if overall_score >= t.get("strong_buy", 75):
        base_rec = "Strong Buy"
    elif overall_score >= t.get("buy", 55):
        base_rec = "Buy"
    elif overall_score >= t.get("hold", 35):
        base_rec = "Hold"
    elif overall_score >= t.get("reduce", 20):
        base_rec = "Reduce"
    else:
        base_rec = "Exit"

    # ── Override rules ────────────────────────────────────────────────────────
    recommendation = _apply_override_rules(base_rec, stop_loss_signal, thesis_intact)

    # ── Supporting and contradicting signals ──────────────────────────────────
    supporting, contradicting = _classify_signals(
        fundamental_grade, technical_grade, sentiment_grade,
        stop_loss_signal, thesis_intact, score_breakdown,
    )

    # ── Rationale ─────────────────────────────────────────────────────────────
    rationale = _generate_rationale(
        recommendation, overall_score, score_breakdown,
        supporting, contradicting, stop_loss_signal, thesis_intact,
    )

    # ── Specific action ───────────────────────────────────────────────────────
    action = _generate_action(recommendation, overall_score, score_breakdown)

    log.info(f"[SKILL-A01] Recommendation: {recommendation} (score={overall_score:.1f})")

    return {
        "recommendation":             recommendation,
        "recommendation_rationale":   rationale,
        "supporting_signals":         supporting,
        "contradicting_signals":      contradicting,
        "recommended_action":         action,
        "base_recommendation":        base_rec,
        "override_applied":           recommendation != base_rec,
    }


def _apply_override_rules(
    recommendation: str,
    stop_loss_signal: str,
    thesis_intact: bool,
) -> str:
    """
    Apply override rules that supersede the score-based recommendation.
    Priority: stop-loss breach > thesis broken > score-based.
    """
    overrides = []

    if stop_loss_signal == "breached":
        overrides.append("stop_loss_breach")
        return "Exit"

    if not thesis_intact:
        overrides.append("thesis_broken")
        if recommendation in ("Strong Buy", "Buy"):
            return "Reduce"

    return recommendation


def _classify_signals(
    fundamental_grade: str,
    technical_grade: str,
    sentiment_grade: str,
    stop_loss_signal: str,
    thesis_intact: bool,
    score_breakdown: dict,
) -> tuple[list[str], list[str]]:
    """Classify signals as supporting or contradicting the investment case."""
    supporting    = []
    contradicting = []

    # Fundamentals
    if fundamental_grade == "Strong":
        supporting.append("Strong fundamentals — revenue, margins and FCF healthy")
    elif fundamental_grade == "Weak":
        contradicting.append("Weak fundamentals — revenue or profitability concerns")

    # Technicals
    if technical_grade == "Bullish":
        supporting.append("Bullish technical trend — price above key moving averages")
    elif technical_grade == "Bearish":
        contradicting.append("Bearish technical trend — price below 200D moving average")

    # Sentiment
    if sentiment_grade == "Positive":
        supporting.append("Positive news sentiment and analyst coverage")
    elif sentiment_grade == "Negative":
        contradicting.append("Negative news sentiment detected")

    # Stop-loss
    if stop_loss_signal == "warning":
        contradicting.append("Price approaching stop-loss level — monitor closely")
    elif stop_loss_signal == "breached":
        contradicting.append("Stop-loss breached — capital protection rule triggered")

    # Thesis
    if not thesis_intact:
        contradicting.append("Investment thesis flagged as changed or broken")

    # Individual scorecard scores
    for sc_name, sc_data in score_breakdown.items():
        score = sc_data.get("score", 50) if isinstance(sc_data, dict) else sc_data
        if score >= 70:
            supporting.append(f"{sc_name.capitalize()} scorecard is strong ({score:.0f}/100)")
        elif score <= 25:
            contradicting.append(f"{sc_name.capitalize()} scorecard is weak ({score:.0f}/100)")

    return supporting, contradicting


def _generate_rationale(
    recommendation: str,
    overall_score: float,
    score_breakdown: dict,
    supporting: list[str],
    contradicting: list[str],
    stop_loss_signal: str,
    thesis_intact: bool,
) -> str:
    """Generate a plain English rationale for the recommendation."""
    parts = [f"Overall score of {overall_score:.1f}/100 → {recommendation}."]

    if stop_loss_signal == "breached":
        parts.append("Stop-loss has been breached — exit rule triggered regardless of fundamentals.")
    elif not thesis_intact:
        parts.append("Investment thesis has been flagged as changed — position under review.")

    if supporting:
        parts.append(f"Key supporting factors: {'; '.join(supporting[:3])}.")
    if contradicting:
        parts.append(f"Key risk factors: {'; '.join(contradicting[:3])}.")

    return " ".join(parts)


def _generate_action(
    recommendation: str,
    overall_score: float,
    score_breakdown: dict,
) -> str:
    """Generate a specific recommended action string."""
    actions = {
        "Strong Buy": "Add to position — consider increasing allocation by up to 50%",
        "Buy":        "Add moderately — consider increasing allocation by 20-30%",
        "Hold":       "Hold current position — no action required",
        "Reduce":     "Trim position — consider reducing allocation by 30-50%",
        "Exit":       "Exit position — sell all shares to protect capital",
    }
    return actions.get(recommendation, "Review position")