"""
alert_manager.py
Layer      : Action
Owns       : SKILL-A07, SKILL-A08, SKILL-A09
Description: Detects stop-loss breaches, thesis integrity risks, and
             generates structured alert records stored in portfolio.db.
             Alerts are surfaced in the Presentation Layer dashboard.
"""

from __future__ import annotations
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

PORTFOLIO_DB = Path("data/portfolio/portfolio.db")

ALERT_TYPES = [
    "stop_loss_breach",
    "stop_loss_warning",
    "thesis_risk",
    "thesis_broken",
    "sector_drift",
    "sentiment_deterioration",
    "rebalancing_required",
    "promoter_pledge_risk",
]


# ── SKILL-A07: Detect Stop-Loss Breach ───────────────────────────────────────

def detect_stop_loss_breach(
    stop_loss_signals: dict[str, dict],
) -> dict[str, Any]:
    """
    SKILL-A07: Detect Stop-Loss Breach.
    Checks stop-loss signals for all holdings and identifies
    breaches and proximity warnings.
    Args:
        stop_loss_signals: dict of ticker -> stop-loss result dict
                           (from SKILL-I31)
    Returns: dict with breached_tickers, warning_tickers, alerts list
    """
    breached = []
    warnings = []
    alerts   = []

    for ticker, sl in stop_loss_signals.items():
        signal = sl.get("stop_loss_signal", "safe")
        drawdown = sl.get("current_drawdown_pct")
        proximity = sl.get("proximity_to_stop_pct")

        if signal == "breached":
            breached.append(ticker)
            alerts.append({
                "alert_type": "stop_loss_breach",
                "ticker":     ticker,
                "message":    (
                    f"{ticker} stop-loss breached. "
                    f"Current drawdown: {drawdown:.1f}%. Exit position."
                ),
                "urgency":    "high",
                "metadata":   sl,
            })
        elif signal == "warning":
            warnings.append(ticker)
            alerts.append({
                "alert_type": "stop_loss_warning",
                "ticker":     ticker,
                "message":    (
                    f"{ticker} approaching stop-loss. "
                    f"Only {proximity:.1f}% above stop-loss level."
                ),
                "urgency":    "medium",
                "metadata":   sl,
            })

    log.info(
        f"[SKILL-A07] Stop-loss check: "
        f"{len(breached)} breached, {len(warnings)} warnings"
    )
    return {
        "breached_tickers": breached,
        "warning_tickers":  warnings,
        "alerts":           alerts,
    }


# ── SKILL-A08: Detect Thesis Integrity Change ─────────────────────────────────

def detect_thesis_integrity_change(
    fundamental_scores: dict[str, dict],
    thesis_flags: dict[str, bool],
    revenue_signals: dict[str, str],
    fcf_signals: dict[str, str],
) -> dict[str, Any]:
    """
    SKILL-A08: Detect Thesis Integrity Change.
    Flags holdings where multiple fundamental signals have deteriorated.
    Args:
        fundamental_scores : dict of ticker -> fundamental score dict
        thesis_flags       : dict of ticker -> thesis_intact bool
        revenue_signals    : dict of ticker -> revenue_signal string
        fcf_signals        : dict of ticker -> fcf_signal string
    Returns: dict with thesis_risk_tickers, thesis_broken_tickers, alerts
    """
    thesis_risk   = []
    thesis_broken = []
    alerts        = []

    all_tickers = set(fundamental_scores.keys()) | set(thesis_flags.keys())

    for ticker in all_tickers:
        # Manually flagged as broken
        if not thesis_flags.get(ticker, True):
            thesis_broken.append(ticker)
            alerts.append({
                "alert_type": "thesis_broken",
                "ticker":     ticker,
                "message":    (
                    f"{ticker} investment thesis flagged as broken. "
                    "Review position and consider reducing."
                ),
                "urgency":    "high",
                "metadata":   {"thesis_intact": False},
            })
            continue

        # Detect deterioration — both revenue and FCF are red
        rev_signal = revenue_signals.get(ticker, "amber")
        fcf_signal = fcf_signals.get(ticker, "amber")
        f_score    = fundamental_scores.get(ticker, {})
        f_val      = f_score.get("fundamental_score", 50)

        if rev_signal == "red" and fcf_signal == "red" and f_val < 35:
            thesis_risk.append(ticker)
            alerts.append({
                "alert_type": "thesis_risk",
                "ticker":     ticker,
                "message":    (
                    f"{ticker} showing thesis deterioration — "
                    "both revenue and FCF are weak. Review investment case."
                ),
                "urgency":    "medium",
                "metadata":   {
                    "revenue_signal": rev_signal,
                    "fcf_signal":     fcf_signal,
                    "fundamental_score": f_val,
                },
            })

    log.info(
        f"[SKILL-A08] Thesis check: "
        f"{len(thesis_broken)} broken, {len(thesis_risk)} at risk"
    )
    return {
        "thesis_risk_tickers":   thesis_risk,
        "thesis_broken_tickers": thesis_broken,
        "alerts":                alerts,
    }


# ── SKILL-A09: Generate Alert ─────────────────────────────────────────────────

def generate_alert(
    alert_type: str,
    message: str,
    urgency: str,
    ticker: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-A09: Generate Alert.
    Creates a structured alert record and writes it to alerts_log in portfolio.db.
    Args:
        alert_type : one of ALERT_TYPES
        message    : human-readable alert description
        urgency    : 'high'|'medium'|'low'
        ticker     : associated ticker (optional)
        metadata   : additional context dict (optional)
    Returns: dict with alert_id and alert_record
    """
    import json

    alert_id = str(uuid.uuid4())[:8]
    now      = datetime.now().isoformat()

    alert_record = {
        "alert_id":   alert_id,
        "alert_type": alert_type,
        "ticker":     ticker,
        "message":    message,
        "urgency":    urgency,
        "metadata":   json.dumps(metadata or {}),
        "is_resolved": 0,
        "created_at": now,
    }

    try:
        with sqlite3.connect(PORTFOLIO_DB) as conn:
            conn.execute("""
                INSERT OR IGNORE INTO alerts_log
                    (alert_id, alert_type, ticker, message, urgency,
                     metadata, is_resolved, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                alert_id, alert_type, ticker, message, urgency,
                alert_record["metadata"], 0, now,
            ))
            conn.commit()
        log.debug(f"[SKILL-A09] Alert stored: [{urgency.upper()}] {alert_type} — {ticker}")
    except Exception as e:
        log.warning(f"[SKILL-A09] Failed to store alert: {e}")

    return {"alert_id": alert_id, "alert_record": alert_record}


def get_active_alerts(db_path: str | None = None) -> list[dict]:
    """
    Retrieve all unresolved alerts from portfolio.db sorted by urgency.
    Args:
        db_path: optional path override (uses PORTFOLIO_DB by default)
    Returns: list of alert dicts sorted by urgency (high first)
    """
    import json

    path = db_path or str(PORTFOLIO_DB)
    urgency_order = {"high": 0, "medium": 1, "low": 2}

    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM alerts_log
                WHERE is_resolved = 0
                ORDER BY created_at DESC
            """).fetchall()

        alerts = []
        for row in rows:
            d = dict(row)
            try:
                d["metadata"] = json.loads(d.get("metadata") or "{}")
            except Exception:
                d["metadata"] = {}
            alerts.append(d)

        alerts.sort(key=lambda a: urgency_order.get(a.get("urgency", "low"), 2))
        return alerts

    except Exception as e:
        log.warning(f"get_active_alerts error: {e}")
        return []


def resolve_alert(
    alert_id: str,
    db_path: str | None = None,
) -> bool:
    """
    Mark an alert as resolved in portfolio.db.
    Args:
        alert_id : unique alert identifier
        db_path  : optional path override
    Returns: True if resolved, False if not found
    """
    path = db_path or str(PORTFOLIO_DB)
    try:
        with sqlite3.connect(path) as conn:
            cursor = conn.execute("""
                UPDATE alerts_log
                SET is_resolved = 1,
                    resolved_at = ?
                WHERE alert_id = ?
            """, (datetime.now().isoformat(), alert_id))
            conn.commit()
        resolved = cursor.rowcount > 0
        if resolved:
            log.info(f"[SKILL-A09] Alert {alert_id} resolved")
        return resolved
    except Exception as e:
        log.warning(f"resolve_alert error: {e}")
        return False


def store_alerts_batch(alerts: list[dict]) -> int:
    """
    Store a batch of alert dicts (from SKILL-A07 / SKILL-A08) to portfolio.db.
    Args:
        alerts: list of alert dicts with keys: alert_type, message, urgency,
                ticker (optional), metadata (optional)
    Returns: number of alerts successfully stored
    """
    stored = 0
    for alert in alerts:
        result = generate_alert(
            alert_type=alert.get("alert_type", "unknown"),
            message=alert.get("message", ""),
            urgency=alert.get("urgency", "medium"),
            ticker=alert.get("ticker"),
            metadata=alert.get("metadata"),
        )
        if result.get("alert_id"):
            stored += 1
    return stored