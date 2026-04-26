"""
fundamentals_module.py
Layer      : Data
Owns       : SKILL-D03, SKILL-D04, SKILL-D05, SKILL-D14
Description: Fetches financial statements, key ratios, and supplementary
             fundamental data from Yahoo Finance and Screener.in.
             Also handles one-time portfolio import from Excel file.
"""

from __future__ import annotations
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup
import yfinance as yf

from src.layers.data.cache_manager import cache_read, cache_write
from src.layers.configuration.config_manager import get_skill_ttl
from src.utils.logger import get_logger
from src.utils.validators import validate_ticker

log = get_logger(__name__)

PORTFOLIO_DB = Path("data/portfolio/portfolio.db")
SCREENER_BASE = "https://www.screener.in/company"

REQUIRED_HOLDINGS_COLS = [
    "Ticker", "Company Name", "Sector",
    "Buy Price", "Quantity",
]


# ── Utilities ─────────────────────────────────────────────────────────────────

def _safe_get(data: dict, key: str, default=None):
    """Safely retrieve a key from a dict, returning default on KeyError/None."""
    try:
        val = data.get(key)
        return val if val is not None else default
    except Exception:
        return default


def _build_screener_url(ticker: str) -> str:
    """
    Build the Screener.in URL for a given ticker symbol.
    Strips exchange suffix before building URL.
    e.g. 'RELIANCE.NS' -> 'https://www.screener.in/company/RELIANCE/'
    """
    base = ticker.split(".")[0].upper()
    return f"{SCREENER_BASE}/{base}/"


def _screener_headers() -> dict:
    """Return browser-like headers for Screener.in requests."""
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def _parse_screener_number(text: str) -> float | None:
    """Parse a Screener.in formatted number string to float."""
    try:
        cleaned = text.replace(",", "").replace("%", "").replace("₹", "").strip()
        return float(cleaned) if cleaned else None
    except (ValueError, AttributeError):
        return None


# ── SKILL-D03: Fetch Financial Statements ─────────────────────────────────────

def fetch_financial_statements(
    ticker: str,
    frequency: str = "both",
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D03: Fetch Financial Statements.
    Retrieves income statement, balance sheet, and cash flow statement
    from Yahoo Finance. Handles annual and quarterly frequencies.
    Args:
        ticker    : NSE/BSE ticker e.g. 'RELIANCE.NS'
        frequency : 'annual', 'quarterly', or 'both'
        config    : merged config dict
    Returns: dict with keys:
        income_statement (pd.DataFrame)
        balance_sheet    (pd.DataFrame)
        cash_flow        (pd.DataFrame)
    """
    from src.layers.data.price_module import build_ticker
    ticker = build_ticker(ticker)
    skill_id = "SKILL-D03"
    ttl = get_skill_ttl(config, skill_id) if config else 168
    cache_key = f"{ticker}_financials_{frequency}"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        data = cached["cached_data"]
        return {
            "income_statement": _dict_to_df(data.get("income_statement")),
            "balance_sheet":    _dict_to_df(data.get("balance_sheet")),
            "cash_flow":        _dict_to_df(data.get("cash_flow")),
        }

    log.info(f"[{skill_id}] Fetching financial statements: {ticker}")
    try:
        t = yf.Ticker(ticker)
        if frequency in ("annual", "both"):
            income = t.financials
            balance = t.balance_sheet
            cashflow = t.cashflow
        else:
            income = t.quarterly_financials
            balance = t.quarterly_balance_sheet
            cashflow = t.quarterly_cashflow

        # Transpose so dates are rows, metrics are columns
        income_df  = income.T  if income  is not None and not income.empty  else pd.DataFrame()
        balance_df = balance.T if balance is not None and not balance.empty else pd.DataFrame()
        cashflow_df= cashflow.T if cashflow is not None and not cashflow.empty else pd.DataFrame()

        payload = {
            "income_statement": _df_to_dict(income_df),
            "balance_sheet":    _df_to_dict(balance_df),
            "cash_flow":        _df_to_dict(cashflow_df),
        }
        cache_write(skill_id, cache_key, payload)

        return {
            "income_statement": income_df,
            "balance_sheet":    balance_df,
            "cash_flow":        cashflow_df,
        }

    except Exception as e:
        log.error(f"[{skill_id}] Failed for {ticker}: {e}")
        return {
            "income_statement": pd.DataFrame(),
            "balance_sheet":    pd.DataFrame(),
            "cash_flow":        pd.DataFrame(),
        }


# ── SKILL-D04: Fetch Key Ratios & Multiples ───────────────────────────────────

def fetch_key_ratios(
    ticker: str,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D04: Fetch Key Ratios & Multiples.
    Retrieves pre-computed valuation ratios from Yahoo Finance info dict.
    Args:
        ticker : NSE/BSE ticker
        config : merged config dict
    Returns: dict with valuation ratios, analyst targets, beta, EPS estimates
    """
    from src.layers.data.price_module import build_ticker
    ticker = build_ticker(ticker)
    skill_id = "SKILL-D04"
    ttl = get_skill_ttl(config, skill_id) if config else 24
    cache_key = f"{ticker}_ratios"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        return cached["cached_data"]

    log.info(f"[{skill_id}] Fetching key ratios: {ticker}")
    try:
        info = yf.Ticker(ticker).info

        result = {
            "pe_ratio":               _safe_get(info, "trailingPE"),
            "forward_pe":             _safe_get(info, "forwardPE"),
            "pb_ratio":               _safe_get(info, "priceToBook"),
            "ps_ratio":               _safe_get(info, "priceToSalesTrailing12Months"),
            "ev_ebitda":              _safe_get(info, "enterpriseToEbitda"),
            "beta":                   _safe_get(info, "beta"),
            "dividend_yield":         _safe_get(info, "dividendYield"),
            "payout_ratio":           _safe_get(info, "payoutRatio"),
            "analyst_target_price":   _safe_get(info, "targetMeanPrice"),
            "analyst_target_low":     _safe_get(info, "targetLowPrice"),
            "analyst_target_high":    _safe_get(info, "targetHighPrice"),
            "analyst_recommendation": _safe_get(info, "recommendationKey"),
            "trailing_eps":           _safe_get(info, "trailingEps"),
            "forward_eps":            _safe_get(info, "forwardEps"),
            "revenue_growth":         _safe_get(info, "revenueGrowth"),
            "earnings_growth":        _safe_get(info, "earningsGrowth"),
            "roe":                    _safe_get(info, "returnOnEquity"),
            "roa":                    _safe_get(info, "returnOnAssets"),
            "debt_to_equity":         _safe_get(info, "debtToEquity"),
            "current_ratio":          _safe_get(info, "currentRatio"),
            "gross_margins":          _safe_get(info, "grossMargins"),
            "operating_margins":      _safe_get(info, "operatingMargins"),
            "profit_margins":         _safe_get(info, "profitMargins"),
            "market_cap":             _safe_get(info, "marketCap"),
            "enterprise_value":       _safe_get(info, "enterpriseValue"),
        }

        cache_write(skill_id, cache_key, result)
        return result

    except Exception as e:
        log.error(f"[{skill_id}] Failed for {ticker}: {e}")
        return {}


# ── SKILL-D05: Scrape Screener.in Fundamentals ───────────────────────────────

def scrape_screener_fundamentals(
    ticker: str,
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D05: Scrape Screener.in Fundamentals.
    Scrapes Screener.in for ROIC, ROCE, EV/EBITDA, promoter holding,
    financial history, and peer comparison data.
    Applies request delay to avoid rate limiting.
    Args:
        ticker : base ticker e.g. 'RELIANCE' or 'RELIANCE.NS'
        config : merged config dict
    Returns: dict with fundamental history and peer data
    """
    skill_id = "SKILL-D05"
    ttl = get_skill_ttl(config, skill_id) if config else 168
    base = ticker.split(".")[0].upper()
    cache_key = f"{base}_screener"

    cached = cache_read(skill_id, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        data = cached["cached_data"]
        peer_df = pd.DataFrame(data.get("peer_comparison", []))
        return {**data, "peer_comparison": peer_df}

    delay = (config or {}).get("system", {}).get("scraper_request_delay_seconds", 2.5)
    url = _build_screener_url(base)
    log.info(f"[{skill_id}] Scraping Screener.in: {url}")
    time.sleep(delay)

    try:
        resp = requests.get(url, headers=_screener_headers(), timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        result = {
            "roic":                  _scrape_ratio(soup, "Return on capital employed"),
            "roce":                  _scrape_ratio(soup, "Return on capital employed"),
            "ev_ebitda_screener":    None,
            "promoter_holding_pct":  _scrape_promoter_holding(soup),
            "roe_history":           _scrape_annual_metric(soup, "Return on equity"),
            "revenue_history":       _scrape_annual_metric(soup, "Sales"),
            "net_profit_history":    _scrape_annual_metric(soup, "Net Profit"),
            "peer_comparison":       [],
        }

        peer_df = _scrape_peer_table(soup)
        result["peer_comparison"] = peer_df.to_dict("records") if not peer_df.empty else []

        # Cache serialisable copy
        cache_write(skill_id, cache_key, result)

        return {**result, "peer_comparison": peer_df}

    except requests.exceptions.HTTPError as e:
        log.warning(f"[{skill_id}] HTTP error scraping {url}: {e}")
        return _empty_screener_result()
    except Exception as e:
        log.warning(f"[{skill_id}] Scrape failed for {base}: {e}")
        return _empty_screener_result()


def _scrape_ratio(soup: BeautifulSoup, label: str) -> float | None:
    """Find a ratio value from Screener.in key metrics section by label."""
    try:
        spans = soup.find_all("span", class_="name")
        for span in spans:
            if label.lower() in span.get_text(strip=True).lower():
                val_span = span.find_next_sibling("span", class_="number")
                if val_span:
                    return _parse_screener_number(val_span.get_text(strip=True))
    except Exception:
        pass
    return None


def _scrape_promoter_holding(soup: BeautifulSoup) -> float | None:
    """Extract promoter holding % from Screener.in shareholding section."""
    try:
        tables = soup.find_all("table")
        for table in tables:
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            if any("promoter" in h.lower() for h in headers):
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if cells and "promoter" in cells[0].get_text(strip=True).lower():
                        last_val = cells[-1].get_text(strip=True)
                        return _parse_screener_number(last_val)
    except Exception:
        pass
    return None


def _scrape_annual_metric(soup: BeautifulSoup, metric_name: str) -> list[float]:
    """Extract annual metric history from Screener.in profit & loss table."""
    try:
        rows = soup.select("section#profit-loss table tbody tr")
        for row in rows:
            cols = row.find_all("td")
            if cols and metric_name.lower() in cols[0].get_text(strip=True).lower():
                values = []
                for cell in cols[1:]:
                    val = _parse_screener_number(cell.get_text(strip=True))
                    if val is not None:
                        values.append(val)
                return values[-5:]  # last 5 years
    except Exception:
        pass
    return []


def _scrape_peer_table(soup: BeautifulSoup) -> pd.DataFrame:
    """Extract peer comparison table from Screener.in."""
    try:
        peer_section = soup.find("section", id="peers")
        if not peer_section:
            return pd.DataFrame()
        table = peer_section.find("table")
        if not table:
            return pd.DataFrame()
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        rows = []
        for tr in table.find_all("tr")[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all("td")]
            if cells:
                rows.append(cells)
        if rows and headers:
            df = pd.DataFrame(rows, columns=headers[:len(rows[0])])
            return df
    except Exception:
        pass
    return pd.DataFrame()


def _empty_screener_result() -> dict[str, Any]:
    """Return an empty result dict when scraping fails."""
    return {
        "roic": None, "roce": None, "ev_ebitda_screener": None,
        "promoter_holding_pct": None, "roe_history": [],
        "revenue_history": [], "net_profit_history": [],
        "peer_comparison": pd.DataFrame(),
    }


# ── SKILL-D14: Import Portfolio from Excel ────────────────────────────────────

def import_portfolio_from_excel(
    file_path: str | Path = "data/input/portfolio.xlsx",
    config: dict | None = None,
) -> dict[str, Any]:
    """
    SKILL-D14: Import Portfolio from Excel.
    Reads user portfolio from .xlsx, validates required columns, normalises
    tickers, and writes to portfolio.db holdings table.
    One-time import — warns before overwriting existing holdings.
    Args:
        file_path : path to .xlsx portfolio file
        config    : merged config dict
    Returns: dict with keys:
        holdings_df       (pd.DataFrame: validated holdings)
        import_status     (str: 'success', 'partial', or 'failed')
        validation_errors (list of error strings)
    """
    skill_id = "SKILL-D14"
    file_path = Path(file_path)
    errors: list[str] = []

    if not file_path.exists():
        log.error(f"[{skill_id}] File not found: {file_path}")
        return {
            "holdings_df": pd.DataFrame(),
            "import_status": "failed",
            "validation_errors": [f"File not found: {file_path}"],
        }

    log.info(f"[{skill_id}] Importing portfolio from {file_path}")
    try:
        df = pd.read_excel(file_path, engine="openpyxl")
        df.columns = df.columns.str.strip()
    except Exception as e:
        return {
            "holdings_df": pd.DataFrame(),
            "import_status": "failed",
            "validation_errors": [f"Could not read Excel file: {e}"],
        }

    # Check required columns
    missing = [c for c in REQUIRED_HOLDINGS_COLS if c not in df.columns]
    if missing:
        return {
            "holdings_df": pd.DataFrame(),
            "import_status": "failed",
            "validation_errors": [f"Missing required columns: {missing}"],
        }

    # Normalise tickers — append .NS if no suffix
    exchange = (config or {}).get("system", {}).get("default_exchange_suffix", "NS")
    df["Ticker"] = df["Ticker"].apply(
        lambda t: t.strip().upper() if "." in str(t)
        else f"{str(t).strip().upper()}.{exchange}"
    )

    # Fill optional columns with defaults
    if "Stop Loss %" not in df.columns:
        df["Stop Loss %"] = 8.0
    else:
        df["Stop Loss %"] = df["Stop Loss %"].fillna(8.0)

    if "Investment Thesis" not in df.columns:
        df["Investment Thesis"] = ""
    else:
        df["Investment Thesis"] = df["Investment Thesis"].fillna("")
    valid_rows = []
    for idx, row in df.iterrows():
        row_errors = _validate_holding_row(idx, row)
        if row_errors:
            errors.extend(row_errors)
            log.warning(f"[{skill_id}] Skipping row {idx}: {row_errors}")
        else:
            valid_rows.append(row)

    if not valid_rows:
        return {
            "holdings_df": pd.DataFrame(),
            "import_status": "failed",
            "validation_errors": errors,
        }

    valid_df = pd.DataFrame(valid_rows)

    # Write to portfolio.db
    db_errors = _write_holdings_to_db(valid_df, skill_id)
    errors.extend(db_errors)

    status = "success" if not errors else "partial"
    log.info(
        f"[{skill_id}] Import {status}: "
        f"{len(valid_rows)} holdings written, {len(errors)} error(s)."
    )

    return {
        "holdings_df": valid_df,
        "import_status": status,
        "validation_errors": errors,
    }


def _validate_holding_row(idx: int, row: pd.Series) -> list[str]:
    """Validate a single holding row. Returns list of error strings."""
    errs = []
    try:
        buy_price = float(row["Buy Price"])
        if buy_price <= 0:
            errs.append(f"Row {idx}: Buy Price must be > 0, got {buy_price}")
    except (ValueError, TypeError):
        errs.append(f"Row {idx}: Buy Price is not numeric: {row['Buy Price']}")

    try:
        qty = float(row["Quantity"])
        if qty <= 0:
            errs.append(f"Row {idx}: Quantity must be > 0, got {qty}")
    except (ValueError, TypeError):
        errs.append(f"Row {idx}: Quantity is not numeric: {row['Quantity']}")

    if pd.isnull(row.get("Company Name")) or str(row["Company Name"]).strip() == "":
        errs.append(f"Row {idx}: Company Name is empty")

    if pd.isnull(row.get("Sector")) or str(row["Sector"]).strip() == "":
        errs.append(f"Row {idx}: Sector is empty")

    return errs


def _write_holdings_to_db(df: pd.DataFrame, skill_id: str) -> list[str]:
    """Write validated holdings DataFrame to portfolio.db. Returns error list."""
    errors = []
    try:
        db_path = PORTFOLIO_DB
        with sqlite3.connect(db_path) as conn:
            for _, row in df.iterrows():
                try:
                    conn.execute("""
                        INSERT INTO holdings
                            (ticker, company_name, sector, buy_price, quantity,
                             stop_loss_pct, thesis, thesis_intact)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(ticker) DO UPDATE SET
                            company_name  = excluded.company_name,
                            sector        = excluded.sector,
                            buy_price     = excluded.buy_price,
                            quantity      = excluded.quantity,
                            stop_loss_pct = excluded.stop_loss_pct,
                            thesis        = excluded.thesis,
                            updated_at    = datetime('now')
                    """, (
                        str(row["Ticker"]),
                        str(row["Company Name"]),
                        str(row["Sector"]),
                        float(row["Buy Price"]),
                        float(row["Quantity"]),
                        float(row.get("Stop Loss %", 8.0)),
                        str(row.get("Investment Thesis", "")),
                        1,
                    ))
                except Exception as e:
                    errors.append(f"DB write error for {row['Ticker']}: {e}")
            conn.commit()
    except Exception as e:
        errors.append(f"DB connection error: {e}")
    return errors


# ── DataFrame serialisation helpers ───────────────────────────────────────────

def _df_to_dict(df: pd.DataFrame) -> dict:
    """Serialise a DataFrame to a JSON-safe dict for cache storage."""
    if df.empty:
        return {"columns": [], "index": [], "rows": []}
    return {
        "columns": df.columns.tolist(),
        "index":   [str(i) for i in df.index],
        "rows":    df.where(pd.notnull(df), None).values.tolist(),
    }


def _dict_to_df(data: dict | None) -> pd.DataFrame:
    """Reconstruct a DataFrame from a cached dict."""
    if not data or not data.get("columns"):
        return pd.DataFrame()
    df = pd.DataFrame(data["rows"], columns=data["columns"])
    df.index = pd.to_datetime(data["index"], errors="coerce")
    return df