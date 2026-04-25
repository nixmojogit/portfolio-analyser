"""
validators.py
Input validation functions used across configuration and data layers.
"""

from __future__ import annotations
from datetime import datetime
import re
import pandas as pd


NSE_TICKER_PATTERN = re.compile(r"^[A-Z0-9&-]+\.(NS|BO)$")

REQUIRED_HOLDINGS_COLUMNS = [
    "Ticker",
    "Company Name",
    "Sector",
    "Buy Price",
    "Quantity",
    "Buy Date",
]

VALID_SECTORS = [
    "Technology",
    "Financial Services",
    "Consumer",
    "Healthcare",
    "Energy",
    "Infrastructure",
    "Automobile",
    "Pharma",
    "FMCG",
    "Metals",
    "Realty",
    "Media",
    "Telecom",
    "Others",
]


def validate_ticker(ticker: str) -> bool:
    """
    Validate that a ticker string is in correct NSE/BSE format.
    Valid examples: 'RELIANCE.NS', 'TCS.NS', 'INFY.BO'
    Invalid examples: 'RELIANCE', 'tcs.ns', 'TCS.NYSE'
    Args:
        ticker: ticker string to validate
    Returns: True if valid format, False otherwise
    """
    if not ticker or not isinstance(ticker, str):
        return False
    return bool(NSE_TICKER_PATTERN.match(ticker.strip()))


def validate_holdings_dataframe(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """
    Validate that a portfolio holdings DataFrame has all required columns
    and no missing values in required fields.
    Required columns: Ticker, Company Name, Sector, Buy Price,
                      Quantity, Buy Date
    Args:
        df: pd.DataFrame to validate (typically loaded from Excel)
    Returns: tuple of (is_valid: bool, errors: list of error message strings)
    """
    errors: list[str] = []

    if df is None or df.empty:
        return False, ["DataFrame is empty or None."]

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Check required columns exist
    missing_cols = [c for c in REQUIRED_HOLDINGS_COLUMNS if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")
        return False, errors

    # Check for missing values in required columns
    for col in REQUIRED_HOLDINGS_COLUMNS:
        null_rows = df[df[col].isnull()].index.tolist()
        if null_rows:
            errors.append(f"Column '{col}' has missing values at rows: {null_rows}")

    # Validate Buy Price is positive numeric
    for idx, val in df["Buy Price"].items():
        valid, msg = validate_positive_float(val, f"Buy Price (row {idx})")
        if not valid:
            errors.append(msg)

    # Validate Quantity is positive numeric
    for idx, val in df["Quantity"].items():
        valid, msg = validate_positive_float(val, f"Quantity (row {idx})")
        if not valid:
            errors.append(msg)

    # Validate Buy Date format
    for idx, val in df["Buy Date"].items():
        if pd.isnull(val):
            continue
        date_str = str(val).strip()
        # Accept DD-MM-YYYY or YYYY-MM-DD (common Excel date formats)
        if not (validate_date_string(date_str, "%d-%m-%Y") or
                validate_date_string(date_str, "%Y-%m-%d") or
                validate_date_string(date_str, "%d/%m/%Y")):
            errors.append(
                f"Buy Date at row {idx} has unrecognised format: '{date_str}'. "
                "Use DD-MM-YYYY."
            )

    is_valid = len(errors) == 0
    return is_valid, errors


def validate_date_string(date_str: str, fmt: str = "%d-%m-%Y") -> bool:
    """
    Validate that a date string matches the expected format.
    Args:
        date_str : date string to validate e.g. '15-01-2024'
        fmt      : expected strptime format (default '%d-%m-%Y')
    Returns: True if valid, False otherwise
    """
    if not date_str or not isinstance(date_str, str):
        return False
    try:
        datetime.strptime(date_str.strip(), fmt)
        return True
    except ValueError:
        return False


def validate_positive_float(value, field_name: str = "value") -> tuple[bool, str]:
    """
    Validate that a value is a positive float or int.
    Args:
        value      : value to validate
        field_name : field name for error message context
    Returns: tuple of (is_valid: bool, error_message: str)
             error_message is empty string if valid
    """
    if value is None:
        return False, f"'{field_name}' is None."
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False, f"'{field_name}' is not numeric: {value!r}"
    if numeric <= 0:
        return False, f"'{field_name}' must be greater than zero, got {numeric}."
    return True, ""