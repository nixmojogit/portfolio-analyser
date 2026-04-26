"""
cache_manager.py
Layer      : Data
Owns       : SKILL-D13
Description: Central cache read/write manager. All data skills call this before
             making external API requests. Uses local SQLite (market_data.db).
             TTL per skill is read from skills.yaml at runtime.
"""

from __future__ import annotations
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.utils.logger import get_logger

log = get_logger(__name__)

DB_PATH = Path("data/cache/market_data.db")

# ── Schema ────────────────────────────────────────────────────────────────────

_CREATE_CACHE_TABLE = """
CREATE TABLE IF NOT EXISTS cache (
    cache_key   TEXT    PRIMARY KEY,
    skill_id    TEXT    NOT NULL,
    data        TEXT    NOT NULL,
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL
);
"""

_CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_cache_skill
ON cache (skill_id);
"""


# ── Initialisation ────────────────────────────────────────────────────────────

def init_cache_db() -> None:
    """
    SKILL-D13: Initialise the SQLite cache database and create the cache
    table and index if they do not already exist.
    Safe to call multiple times — uses CREATE IF NOT EXISTS.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(_CREATE_CACHE_TABLE)
        conn.execute(_CREATE_INDEX)
        conn.commit()
    log.info(f"Cache DB ready at {DB_PATH}")


# ── Core CRUD ─────────────────────────────────────────────────────────────────

def cache_read(
    skill_id: str,
    cache_key: str,
    ttl_hours: float,
) -> dict[str, Any]:
    """
    SKILL-D13 (read): Check whether a fresh cached record exists for cache_key.
    Returns cache_hit=False if the record is absent or older than ttl_hours.
    Cache failures are caught and logged — never crash the calling skill.
    Args:
        skill_id  : calling skill ID (for logging)
        cache_key : unique record identifier e.g. 'RELIANCE.NS_price_1d'
        ttl_hours : maximum acceptable cache age in hours
    Returns: dict with keys:
        cache_hit       (bool)
        cached_data     (any | None)
        cache_age_hours (float | None)
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT data, created_at FROM cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()

        if row is None:
            log.debug(f"[{skill_id}] Cache MISS: {cache_key}")
            return {"cache_hit": False, "cached_data": None, "cache_age_hours": None}

        data_str, created_at = row
        age_hours = (time.time() - created_at) / 3600

        if age_hours > ttl_hours:
            log.debug(
                f"[{skill_id}] Cache STALE: {cache_key} "
                f"(age={age_hours:.1f}h ttl={ttl_hours}h)"
            )
            return {
                "cache_hit": False,
                "cached_data": None,
                "cache_age_hours": round(age_hours, 2),
            }

        data = json.loads(data_str)
        log.debug(f"[{skill_id}] Cache HIT: {cache_key} (age={age_hours:.1f}h)")
        return {
            "cache_hit": True,
            "cached_data": data,
            "cache_age_hours": round(age_hours, 2),
        }

    except Exception as e:
        log.warning(f"[{skill_id}] Cache read error for '{cache_key}': {e}")
        return {"cache_hit": False, "cached_data": None, "cache_age_hours": None}


def cache_write(
    skill_id: str,
    cache_key: str,
    data: Any,
) -> bool:
    """
    SKILL-D13 (write): Serialise and store data in the SQLite cache.
    Uses UPSERT so repeated writes update the existing record cleanly.
    Non-serialisable types (e.g. datetime) are coerced to strings via default=str.
    Args:
        skill_id  : calling skill ID (for logging)
        cache_key : unique record identifier
        data      : data to store (must be JSON-serialisable)
    Returns: True on success, False on failure
    """
    try:
        now = time.time()
        data_str = json.dumps(data, default=str)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO cache (cache_key, skill_id, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    data       = excluded.data,
                    skill_id   = excluded.skill_id,
                    updated_at = excluded.updated_at
                """,
                (cache_key, skill_id, data_str, now, now),
            )
            conn.commit()
        log.debug(f"[{skill_id}] Cache WRITE: {cache_key}")
        return True

    except Exception as e:
        log.warning(f"[{skill_id}] Cache write error for '{cache_key}': {e}")
        return False


def cache_invalidate(cache_key: str) -> bool:
    """
    Delete a specific cache record by key.
    Args:
        cache_key: unique record identifier
    Returns: True if a record was deleted, False if not found
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "DELETE FROM cache WHERE cache_key = ?", (cache_key,)
            )
            conn.commit()
        deleted = cursor.rowcount > 0
        log.debug(f"Cache INVALIDATE: {cache_key} ({'deleted' if deleted else 'not found'})")
        return deleted

    except Exception as e:
        log.warning(f"Cache invalidate error for '{cache_key}': {e}")
        return False


def cache_invalidate_all(ticker: str) -> int:
    """
    Delete all cache records whose key contains the given ticker symbol.
    Args:
        ticker: e.g. 'RELIANCE.NS'
    Returns: number of records deleted
    """
    try:
        pattern = f"%{ticker}%"
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "DELETE FROM cache WHERE cache_key LIKE ?", (pattern,)
            )
            conn.commit()
        count = cursor.rowcount
        log.info(f"Cache INVALIDATE ALL: {ticker} ({count} records deleted)")
        return count

    except Exception as e:
        log.warning(f"Cache invalidate_all error for '{ticker}': {e}")
        return 0


def get_cache_stats() -> dict[str, Any]:
    """
    Return summary statistics about the current cache state.
    Returns: dict with keys:
        total_records, oldest_record, newest_record,
        stale_records (>24h old), size_bytes
    """
    try:
        now = time.time()
        with sqlite3.connect(DB_PATH) as conn:
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            oldest_ts = conn.execute("SELECT MIN(created_at) FROM cache").fetchone()[0]
            newest_ts = conn.execute("SELECT MAX(created_at) FROM cache").fetchone()[0]
            stale = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE ? - created_at > 86400",
                (now,),
            ).fetchone()[0]

        size = DB_PATH.stat().st_size if DB_PATH.exists() else 0

        return {
            "total_records": total,
            "oldest_record": (
                datetime.fromtimestamp(oldest_ts).isoformat() if oldest_ts else None
            ),
            "newest_record": (
                datetime.fromtimestamp(newest_ts).isoformat() if newest_ts else None
            ),
            "stale_records": stale,
            "size_bytes": size,
        }

    except Exception as e:
        log.warning(f"Cache stats error: {e}")
        return {}