"""SQLite storage: one row per site with the state at its last check."""

import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS site_status (
    site          TEXT PRIMARY KEY,
    version       TEXT,             -- version detected at last check ('' if none)
    latest        TEXT,             -- latest WP release at that moment
    status        TEXT NOT NULL,    -- UP-TO-DATE / OUTDATED (...) / UNKNOWN / ERROR
    detail        TEXT,
    last_checked  TEXT NOT NULL     -- UTC ISO timestamp
)
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def save_results(conn, results, checked_at=None):
    """Insert new sites, update existing ones."""
    ts = checked_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany(
        """
        INSERT INTO site_status (site, version, latest, status, detail, last_checked)
        VALUES (:site, :version, :latest, :status, :detail, :ts)
        ON CONFLICT(site) DO UPDATE SET
            version = excluded.version,
            latest = excluded.latest,
            status = excluded.status,
            detail = excluded.detail,
            last_checked = excluded.last_checked
        """,
        [{**r, "ts": ts} for r in results],
    )
    conn.commit()


def get_all(conn):
    return conn.execute("SELECT * FROM site_status ORDER BY site").fetchall()


def get_last_check(conn):
    """Latest WP version and timestamp of the most recent check (None if DB is empty)."""
    return conn.execute(
        "SELECT latest, last_checked FROM site_status ORDER BY last_checked DESC LIMIT 1"
    ).fetchone()


def delete_site(conn, site):
    cur = conn.execute("DELETE FROM site_status WHERE site = ?", (site,))
    conn.commit()
    return cur.rowcount
