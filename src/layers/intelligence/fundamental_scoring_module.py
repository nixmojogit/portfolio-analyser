"""
fundamental_scoring_module.py
Layer      : Intelligence
Owns       : SKILL-I07, SKILL-I08, SKILL-I09, SKILL-I13, SKILL-I14,
             SKILL-I15, SKILL-I16, SKILL-I17
"""

from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd
from src.utils.logger import get_logger

log = get_logger(__name__)


def _safe_float(val) -> float | None:
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def _signal_to_subscore(signal: str) -> float | None:
    return {"green": 80.0, "amber": 50.0, "red": 15.0}.get(
        signal.lower() if signal else "na"
    )


def _pct_change(new_val, old_val) -> float | None:
    if old_val is None or new_val is None or old_val == 0:
        return None
    return round(((new_val - old_val) / abs(old_val)) * 100, 4)


def _get_series_value(df: pd.DataFrame, keywords: list) -> pd.Series | None:
    if df is None or df.empty:
        return None
    for col in df.columns:
        if all(kw.lower() in str(col).lower() for kw in keywords):
            s = df[col].dropna()
            if len(s) > 0:
                return s
    return None


def _find(df: pd.DataFrame, *keyword_lists) -> pd.Series | None:
    """Chain multiple keyword searches — returns first non-None result."""
    for kws in keyword_lists:
        result = _get_series_value(df, kws)
        if result is not None:
            return result
    return None


def compute_revenue_growth(income_statement: pd.DataFrame,
                           config: dict | None = None) -> dict:
    empty = {"revenue_growth_yoy": None, "revenue_growth_qoq": None,
             "revenue_cagr_3y": None, "growth_trajectory": "unknown",
             "revenue_signal": "amber"}
    rev = _find(income_statement, ["total", "revenue"], ["revenue"], ["total", "income"])
    if rev is None or len(rev) < 2:
        return empty
    latest, prior = _safe_float(rev.iloc[0]), _safe_float(rev.iloc[1])
    yoy = _pct_change(latest, prior)
    cagr_3y = None
    if len(rev) >= 4:
        oldest = _safe_float(rev.iloc[3])
        if oldest and latest and oldest > 0:
            cagr_3y = round(((latest / oldest) ** (1/3) - 1) * 100, 4)
    trajectory = "stable"
    if len(rev) >= 4:
        rates = [r for r in [_pct_change(_safe_float(rev.iloc[i]),
                 _safe_float(rev.iloc[i+1])) for i in range(min(3, len(rev)-1))]
                 if r is not None]
        if len(rates) >= 2:
            if rates[0] > rates[-1] + 3:   trajectory = "decelerating"
            elif rates[0] < rates[-1] - 3: trajectory = "accelerating"
    t = (config or {}).get("thresholds", {}).get("revenue_growth_yoy_pct", {})
    g, a = t.get("green_above", 10), t.get("amber_above", 0)
    signal = ("amber" if yoy is None else
              "green" if yoy >= g else
              "amber" if yoy >= a else "red")
    return {"revenue_growth_yoy": yoy, "revenue_growth_qoq": None,
            "revenue_cagr_3y": cagr_3y, "growth_trajectory": trajectory,
            "revenue_signal": signal}


def compute_margin_trends(income_statement: pd.DataFrame,
                          config: dict | None = None) -> dict:
    empty = {"gross_margin": None, "operating_margin": None, "net_margin": None,
             "margin_trend": "stable", "margin_signal": "amber"}
    rev_s   = _find(income_statement, ["total", "revenue"], ["revenue"])
    gross_s = _find(income_statement, ["gross", "profit"])
    op_s    = _find(income_statement, ["operating", "income"], ["ebit"])
    net_s   = _find(income_statement, ["net", "income"])
    if rev_s is None or len(rev_s) < 1:
        return empty
    rv = _safe_float(rev_s.iloc[0])
    if not rv or rv == 0:
        return empty
    def _m(s):
        if s is None or s.empty: return None
        v = _safe_float(s.iloc[0])
        return round((v / rv) * 100, 4) if v else None
    gross_margin = _m(gross_s)
    op_margin    = _m(op_s)
    net_margin   = _m(net_s)
    trend = "stable"
    if net_s is not None and len(net_s) >= 4 and len(rev_s) >= 4:
        ms = []
        for i in range(4):
            r = _safe_float(rev_s.iloc[i])
            n = _safe_float(net_s.iloc[i])
            if r and r != 0 and n is not None:
                ms.append((n / r) * 100)
        if len(ms) >= 3:
            avg = sum(ms[1:]) / len(ms[1:])
            if ms[0] > avg + 1:   trend = "expanding"
            elif ms[0] < avg - 1: trend = "compressing"
    t = (config or {}).get("thresholds", {}).get("net_profit_margin_pct", {})
    g, a = t.get("green_above", 15), t.get("amber_above", 5)
    signal = ("amber" if net_margin is None else
              "green" if net_margin >= g else
              "amber" if net_margin >= a else "red")
    if trend == "compressing" and signal == "green":
        signal = "amber"
    return {"gross_margin": gross_margin, "operating_margin": op_margin,
            "net_margin": net_margin, "margin_trend": trend, "margin_signal": signal}


def compute_free_cash_flow(cash_flow: pd.DataFrame, income_statement: pd.DataFrame,
                           config: dict | None = None) -> dict:
    empty = {"fcf": None, "fcf_growth_yoy": None, "fcf_margin": None,
             "fcf_vs_net_income": None, "fcf_signal": "amber"}
    ocf_s   = _find(cash_flow, ["operating", "cash", "flow"], ["operating", "activities"])
    capex_s = _find(cash_flow, ["capital", "expenditure"], ["purchase", "property"])
    if ocf_s is None:
        return empty
    ocf_val    = _safe_float(ocf_s.iloc[0])
    ocf_prev   = _safe_float(ocf_s.iloc[1]) if len(ocf_s) > 1 else None
    capex_val  = abs(_safe_float(capex_s.iloc[0]) or 0) if capex_s is not None else 0
    capex_prev = abs(_safe_float(capex_s.iloc[1]) or 0)                  if capex_s is not None and len(capex_s) > 1 else 0
    fcf        = (ocf_val  - capex_val)  if ocf_val  is not None else None
    fcf_prev   = (ocf_prev - capex_prev) if ocf_prev is not None else None
    fcf_growth = _pct_change(fcf, fcf_prev)
    rev_s      = _find(income_statement, ["total", "revenue"], ["revenue"])
    fcf_margin = None
    if rev_s is not None and fcf is not None:
        rv = _safe_float(rev_s.iloc[0])
        if rv and rv != 0:
            fcf_margin = round((fcf / rv) * 100, 4)
    net_s     = _find(income_statement, ["net", "income"])
    fcf_vs_ni = None
    if net_s is not None and fcf is not None:
        ni = _safe_float(net_s.iloc[0])
        if ni and ni != 0:
            fcf_vs_ni = round(fcf / ni, 4)
    signal = ("amber" if fcf is None else
              "green" if fcf > 0 and (fcf_growth is None or fcf_growth >= 0) else
              "amber" if fcf > 0 else "red")
    return {"fcf": fcf, "fcf_growth_yoy": fcf_growth, "fcf_margin": fcf_margin,
            "fcf_vs_net_income": fcf_vs_ni, "fcf_signal": signal}


def compute_roic(income_statement: pd.DataFrame, balance_sheet: pd.DataFrame,
                 roic_screener: float | None = None, config: dict | None = None) -> dict:
    roic = None
    try:
        op_s   = _find(income_statement, ["operating", "income"], ["ebit"])
        ta_s   = _find(balance_sheet, ["total", "assets"])
        cl_s   = _find(balance_sheet, ["current", "liabilities"])
        cash_s = _find(balance_sheet, ["cash", "equivalents"], ["cash"])
        tax_s  = _find(income_statement, ["tax", "provision"], ["income", "tax"])
        net_s  = _find(income_statement, ["net", "income"])
        op   = _safe_float(op_s.iloc[0])   if op_s   is not None else None
        ta   = _safe_float(ta_s.iloc[0])   if ta_s   is not None else None
        cl   = _safe_float(cl_s.iloc[0])   if cl_s   is not None else None
        cash = _safe_float(cash_s.iloc[0]) if cash_s is not None else 0
        tax  = _safe_float(tax_s.iloc[0])  if tax_s  is not None else None
        net  = _safe_float(net_s.iloc[0])  if net_s  is not None else None
        tax_rate = 0.25
        if tax is not None and net is not None and (net + tax) != 0:
            tax_rate = min(max(abs(tax) / abs(net + tax), 0), 0.45)
        if op and ta and cl:
            nopat = op * (1 - tax_rate)
            ic    = ta - (cl or 0) - (cash or 0)
            if ic and ic != 0:
                roic = round((nopat / ic) * 100, 4)
    except Exception:
        pass
    if roic is None and roic_screener is not None:
        roic = _safe_float(roic_screener)
    t = (config or {}).get("thresholds", {}).get("roic_pct", {})
    g, a = t.get("green_above", 12), t.get("amber_above", 8)
    signal = ("amber" if roic is None else
              "green" if roic >= g else
              "amber" if roic >= a else "red")
    return {"roic": roic, "roic_signal": signal}


def compute_relative_strength(price_df: pd.DataFrame, sector_index_df: pd.DataFrame,
                               config: dict | None = None) -> dict:
    empty = {"rs_1m": None, "rs_3m": None, "rs_6m": None, "rs_signal": "inline"}
    if price_df is None or price_df.empty:
        return empty
    if sector_index_df is None or sector_index_df.empty:
        return empty
    sc = price_df["Close"].dropna()
    ic = sector_index_df["Close"].dropna()
    common = sc.index.intersection(ic.index)
    if len(common) < 21:
        return empty
    def _rel(days):
        if len(common) < days: return None
        p = common[-days:]
        sr = _pct_change(_safe_float(sc.loc[p[-1]]), _safe_float(sc.loc[p[0]]))
        ir = _pct_change(_safe_float(ic.loc[p[-1]]), _safe_float(ic.loc[p[0]]))
        return round(sr - ir, 4) if sr is not None and ir is not None else None
    rs_1m, rs_3m, rs_6m = _rel(21), _rel(63), _rel(126)
    anchor = rs_3m if rs_3m is not None else rs_1m
    signal = ("outperforming" if anchor is not None and anchor > 3 else
              "underperforming" if anchor is not None and anchor < -3 else "inline")
    return {"rs_1m": rs_1m, "rs_3m": rs_3m, "rs_6m": rs_6m, "rs_signal": signal}


def compute_earnings_surprise(actual_eps: list, estimated_eps: list,
                               config: dict | None = None) -> dict:
    empty = {"surprise_pct_list": [], "avg_surprise_pct": None, "surprise_signal": "na"}
    if not actual_eps or not estimated_eps:
        return empty
    surprises = []
    for a, e in zip(actual_eps, estimated_eps):
        av, ev = _safe_float(a), _safe_float(e)
        if av is not None and ev is not None and ev != 0:
            surprises.append(round(((av - ev) / abs(ev)) * 100, 4))
    if not surprises:
        return empty
    avg = round(sum(surprises) / len(surprises), 4)
    t   = (config or {}).get("thresholds", {}).get("earnings_surprise_pct", {})
    signal = ("consistent_beat" if avg >= t.get("consistent_beat_above", 5) else
              "consistent_miss" if avg <= t.get("consistent_miss_below", -5) else "inline")
    return {"surprise_pct_list": surprises, "avg_surprise_pct": avg,
            "surprise_signal": signal}


def compute_earnings_estimate_revisions(current_estimate, prior_estimate,
                                        config: dict | None = None) -> dict:
    cur, pri = _safe_float(current_estimate), _safe_float(prior_estimate)
    if cur is None or pri is None or pri == 0:
        return {"revision_pct": None, "revision_signal": "na"}
    rev_pct = round(((cur - pri) / abs(pri)) * 100, 4)
    signal  = ("upgraded" if rev_pct > 3 else
               "downgraded" if rev_pct < -3 else "stable")
    return {"revision_pct": rev_pct, "revision_signal": signal}


def compute_promoter_holding_signal(promoter_holding_pct, promoter_change_qoq,
                                    pledge_pct, config: dict | None = None) -> dict:
    if promoter_holding_pct is None:
        return {"promoter_signal": "amber", "promoter_score": 50.0}
    t  = (config or {}).get("thresholds", {}).get("promoter_holding_pct", {})
    pt = (config or {}).get("thresholds", {}).get("promoter_pledge_pct", {})
    g, a = t.get("green_above", 50), t.get("amber_above", 40)
    if promoter_holding_pct >= g:   signal, score = "green", 80.0
    elif promoter_holding_pct >= a: signal, score = "amber", 50.0
    else:                           signal, score = "red",   15.0
    drop = (config or {}).get("thresholds", {}).get(
        "promoter_change_qoq_pct", {}).get("significant_drop_below", -3)
    if promoter_change_qoq is not None and promoter_change_qoq < drop:
        signal, score = "red", 15.0
    if pledge_pct is not None:
        if pledge_pct > pt.get("red_above", 30):   signal, score = "red",   15.0
        elif pledge_pct > 10 and signal == "green": signal, score = "amber", 50.0
    return {"promoter_signal": signal, "promoter_score": score}
