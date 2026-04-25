"""
helpers.py
General-purpose utility functions used across multiple layers.
"""

from __future__ import annotations
from datetime import datetime, date, time
import zoneinfo
import pandas as pd


IST = zoneinfo.ZoneInfo("Asia/Kolkata")
MARKET_OPEN  = time(9, 15)
MARKET_CLOSE = time(15, 30)


def format_inr(value: float, crore: bool = False) -> str:
    """
    Format a float value as an Indian Rupee string.
    Uses Indian numbering system (lakhs / crores).
    Args:
        value : numeric value
        crore : if True, display in crores (divide by 1e7)
    Returns: formatted string e.g. '₹12,34,567' or '₹12.35 Cr'
    """
    if value is None:
        return "N/A"
    if crore:
        return f"₹{value / 1e7:,.2f} Cr"
    # Indian numbering: last 3 digits, then groups of 2
    value = round(value, 2)
    is_negative = value < 0
    s = f"{abs(value):.2f}"
    integer_part, decimal_part = s.split(".")
    # Apply Indian grouping
    if len(integer_part) > 3:
        last_three = integer_part[-3:]
        rest = integer_part[:-3]
        groups = []
        while len(rest) > 2:
            groups.append(rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.append(rest)
        groups.reverse()
        integer_part = ",".join(groups) + "," + last_three
    formatted = f"₹{'-' if is_negative else ''}{integer_part}.{decimal_part}"
    return formatted


def pct_change(new_val: float, old_val: float) -> float | None:
    """
    Compute percentage change from old_val to new_val.
    Returns None if old_val is zero to avoid ZeroDivisionError.
    Args:
        new_val : current value
        old_val : reference / base value
    Returns: percentage change as float or None
    """
    if old_val is None or new_val is None:
        return None
    if old_val == 0:
        return None
    return round(((new_val - old_val) / abs(old_val)) * 100, 4)


def safe_divide(numerator: float, denominator: float, default=None):
    """
    Safe division that returns default instead of raising ZeroDivisionError.
    Also handles None inputs gracefully.
    Args:
        numerator   : dividend
        denominator : divisor
        default     : value to return if denominator is zero or None
    Returns: result of division or default
    """
    if numerator is None or denominator is None:
        return default
    if denominator == 0:
        return default
    return numerator / denominator


def is_market_open() -> bool:
    """
    Check whether Indian stock markets (NSE/BSE) are currently open.
    Market hours: 09:15 to 15:30 IST, Monday to Friday.
    Note: Does not account for Indian public holidays.
    Returns: bool — True if market is currently open
    """
    now_ist = datetime.now(IST)
    if now_ist.weekday() >= 5:          # Saturday=5, Sunday=6
        return False
    current_time = now_ist.time()
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def trading_days_between(start: date, end: date) -> int:
    """
    Count the number of NSE trading days between two dates.
    Excludes weekends. Does not account for public holidays.
    Args:
        start : start date (inclusive)
        end   : end date (inclusive)
    Returns: integer count of trading days
    """
    if start > end:
        return 0
    date_range = pd.bdate_range(start=start, end=end)
    return len(date_range)


def flatten_dict(d: dict, parent_key: str = "", sep: str = "_") -> dict:
    """
    Recursively flatten a nested dict to a single-level dict.
    Example: {'a': {'b': 1}} -> {'a_b': 1}
    Args:
        d          : nested dict to flatten
        parent_key : prefix string for nested keys
        sep        : separator between key levels (default '_')
    Returns: flat single-level dict
    """
    items: list = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)