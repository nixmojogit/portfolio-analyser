"""
sector_universe_module.py
Layer      : Data
Owns       : SKILL-D15
Description: Fetches Nifty sector index constituents from niftyindices.com
             official CSV files. Returns NSE ticker symbols and company names
             for each sector. Used by G2 discovery to build a dynamic universe.
             Cache TTL: 168 hours (7 days).
"""

from __future__ import annotations
import io
from typing import Any

import pandas as pd
import requests

from src.layers.data.cache_manager import cache_read, cache_write
from src.layers.configuration.config_manager import get_skill_ttl
from src.utils.logger import get_logger

log = get_logger(__name__)

SKILL_ID = "SKILL-D15"
BASE_URL  = "https://www.niftyindices.com/IndexConstituent/{filename}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":   "text/csv,application/csv,*/*",
    "Referer":  "https://www.niftyindices.com/indices/equity/sectoral-indices",
}

# Sector -> niftyindices.com CSV filename
SECTOR_CSV_MAP: dict[str, str] = {
    "Technology":         "ind_niftyitlist.csv",
    "Financial Services": "ind_niftyfinancelist.csv",
    "Healthcare":         "ind_niftyhealthcarelist.csv",
    "Pharma":             "ind_niftypharmalist.csv",
    "Consumer":           "ind_niftyfmcglist.csv",
    "FMCG":               "ind_niftyfmcglist.csv",
    "Automobile":         "ind_niftyautolist.csv",
    "Energy":             "ind_niftyenergylist.csv",
    "Metals":             "ind_niftymetallist.csv",
    "Infrastructure":     "ind_niftyinfralist.csv",
    "Realty":             "ind_niftyrealtylist.csv",
}


def fetch_sector_constituents(
    sector: str,
    config: dict | None = None,
) -> list[dict]:
    """
    SKILL-D15: Fetch Nifty sector index constituents from niftyindices.com.
    Returns list of dicts with keys: ticker (NSE .NS suffix), company_name.
    Returns empty list on failure.
    """
    ttl       = get_skill_ttl(config, SKILL_ID) if config else 168
    cache_key = f"sector_universe_{sector.lower().replace(' ', '_')}"

    cached = cache_read(SKILL_ID, cache_key, ttl_hours=ttl)
    if cached["cache_hit"]:
        return cached["cached_data"].get("constituents", [])

    csv_file = SECTOR_CSV_MAP.get(sector)
    if not csv_file:
        log.warning(f"[{SKILL_ID}] No CSV mapping for sector: {sector}")
        return []

    url = BASE_URL.format(filename=csv_file)
    log.info(f"[{SKILL_ID}] Fetching constituents for {sector}: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        df = pd.read_csv(io.StringIO(resp.text))
        df.columns = df.columns.str.strip()

        # Symbol column
        sym_col = next(
            (c for c in df.columns if c.strip().upper() == "SYMBOL"), None
        )
        # Company name column
        name_col = next(
            (c for c in df.columns
             if c.strip().upper() in ("COMPANY NAME", "COMPANYNAME", "NAME")),
            None
        )

        if sym_col is None:
            log.warning(f"[{SKILL_ID}] Symbol column not found for {sector}")
            return []

        constituents = []
        for _, row in df.iterrows():
            sym = str(row[sym_col]).strip() if pd.notna(row[sym_col]) else ""
            if not sym:
                continue
            name = str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else sym
            constituents.append({
                "ticker":       f"{sym}.NS",
                "company_name": name,
            })

        log.info(f"[{SKILL_ID}] {sector}: {len(constituents)} constituents fetched")
        cache_write(SKILL_ID, cache_key, {"constituents": constituents})
        return constituents

    except Exception as e:
        log.warning(f"[{SKILL_ID}] Failed fetching {sector}: {e}")
        return []


def fetch_all_sector_constituents(
    sectors: list[str],
    config: dict | None = None,
) -> dict[str, list[dict]]:
    """
    Fetch constituents for multiple sectors.
    Returns dict of sector -> list of {ticker, company_name} dicts.
    Deduplicates across sectors by ticker.
    """
    result:    dict[str, list[dict]] = {}
    seen_tickers: set = set()

    for sector in sectors:
        constituents = fetch_sector_constituents(sector, config)
        unique = []
        for c in constituents:
            if c["ticker"] not in seen_tickers:
                seen_tickers.add(c["ticker"])
                unique.append(c)
        if unique:
            result[sector] = unique

    return result