"""
init_db.py
Run once from the project root to initialise portfolio.db with all
required tables. Safe to re-run — uses CREATE TABLE IF NOT EXISTS.
Usage: python init_db.py
"""

import sqlite3
from pathlib import Path
from src.utils.logger import get_logger, setup_root_logger

setup_root_logger("INFO")
log = get_logger(__name__)

DB_PATH = Path("data/portfolio/portfolio.db")

# ── Table Definitions ─────────────────────────────────────────────────────────

TABLES = {

    "holdings": """
        CREATE TABLE IF NOT EXISTS holdings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL UNIQUE,
            company_name    TEXT    NOT NULL,
            sector          TEXT    NOT NULL,
            buy_price       REAL    NOT NULL,
            quantity        REAL    NOT NULL,
            buy_date        TEXT,
            stop_loss_pct   REAL    NOT NULL DEFAULT 8.0,
            thesis          TEXT,
            thesis_intact   INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """,

    "thesis_log": """
        CREATE TABLE IF NOT EXISTS thesis_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            thesis_text     TEXT,
            thesis_intact   INTEGER NOT NULL,
            changed_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            changed_by      TEXT    NOT NULL DEFAULT 'user'
        );
    """,

    "scores_history": """
        CREATE TABLE IF NOT EXISTS scores_history (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                  TEXT    NOT NULL,
            score_date              TEXT    NOT NULL,
            overall_score           REAL,
            fundamental_score       REAL,
            technical_score         REAL,
            valuation_score         REAL,
            risk_score              REAL,
            sentiment_score         REAL,
            recommendation          TEXT,
            created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """,

    "recommendations_history": """
        CREATE TABLE IF NOT EXISTS recommendations_history (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                  TEXT    NOT NULL,
            recommendation          TEXT    NOT NULL,
            overall_score           REAL,
            rationale               TEXT,
            recommended_action      TEXT,
            supporting_signals      TEXT,
            contradicting_signals   TEXT,
            generated_at            TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """,

    "alerts_log": """
        CREATE TABLE IF NOT EXISTS alerts_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id        TEXT    NOT NULL UNIQUE,
            alert_type      TEXT    NOT NULL,
            ticker          TEXT,
            message         TEXT    NOT NULL,
            urgency         TEXT    NOT NULL DEFAULT 'medium',
            metadata        TEXT,
            is_resolved     INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            resolved_at     TEXT
        );
    """,

    "performance_history": """
        CREATE TABLE IF NOT EXISTS performance_history (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            record_date             TEXT    NOT NULL UNIQUE,
            total_portfolio_value   REAL,
            day_change_pct          REAL,
            total_return_pct        REAL,
            benchmark_return_pct    REAL,
            created_at              TEXT    NOT NULL DEFAULT (datetime('now'))
        );
    """,

    "rebalancing_log": """
        CREATE TABLE IF NOT EXISTS rebalancing_log (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id                 TEXT    NOT NULL UNIQUE,
            plan_date               TEXT    NOT NULL,
            plan_data               TEXT    NOT NULL,
            estimated_beta_after    REAL,
            estimated_sharpe_after  REAL,
            status                  TEXT    NOT NULL DEFAULT 'pending',
            created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
            executed_at             TEXT
        );
    """,

    "watchlist": """
        CREATE TABLE IF NOT EXISTS watchlist (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL UNIQUE,
            company_name    TEXT,
            sector          TEXT,
            overall_score   REAL,
            added_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            notes           TEXT
        );
    """,
}

# ── Indexes ───────────────────────────────────────────────────────────────────

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_scores_ticker   ON scores_history (ticker);",
    "CREATE INDEX IF NOT EXISTS idx_scores_date     ON scores_history (score_date);",
    "CREATE INDEX IF NOT EXISTS idx_alerts_type     ON alerts_log (alert_type);",
    "CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts_log (is_resolved);",
    "CREATE INDEX IF NOT EXISTS idx_reco_ticker     ON recommendations_history (ticker);",
    "CREATE INDEX IF NOT EXISTS idx_thesis_ticker   ON thesis_log (ticker);",
]

# ── Init Function ─────────────────────────────────────────────────────────────

def init_portfolio_db() -> None:
    """
    Initialise portfolio.db with all required tables and indexes.
    Safe to re-run — all statements use IF NOT EXISTS.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")   # better concurrent access
        conn.execute("PRAGMA foreign_keys=ON;")

        for table_name, ddl in TABLES.items():
            conn.execute(ddl)
            log.info(f"  Table ready : {table_name}")

        for idx_sql in INDEXES:
            conn.execute(idx_sql)

        conn.commit()

    log.info(f"Portfolio DB ready at {DB_PATH}")


# ── Verify ────────────────────────────────────────────────────────────────────

def verify_portfolio_db() -> None:
    """
    Print all tables present in portfolio.db as a quick sanity check.
    """
    with sqlite3.connect(DB_PATH) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
    # Exclude internal SQLite tables (e.g. sqlite_sequence from AUTOINCREMENT)
    table_names = [t[0] for t in tables if not t[0].startswith("sqlite_")]
    log.info(f"Tables in portfolio.db: {table_names}")
    assert len(table_names) == len(TABLES), (
        f"Expected {len(TABLES)} tables, found {len(table_names)}"
    )
    log.info("✅ All tables verified.")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Initialising portfolio.db ...")
    init_portfolio_db()
    verify_portfolio_db()