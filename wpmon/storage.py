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

# User-entered info about a site: not touched by checks, edited only from the admin page.
SCHEMA_META = """
CREATE TABLE IF NOT EXISTS site_meta (
    site          TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    description   TEXT NOT NULL DEFAULT '',
    responsible   TEXT NOT NULL DEFAULT ''
)
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.execute(SCHEMA_META)
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


def get_all_meta(conn):
    """{site: row} for every site with saved name/description/responsible."""
    return {r["site"]: r for r in conn.execute("SELECT * FROM site_meta")}


def get_meta(conn, site):
    return conn.execute("SELECT * FROM site_meta WHERE site = ?", (site,)).fetchone()


def save_meta(conn, site, name="", description="", responsible=""):
    """Insert or replace the info for one site. Empty fields are stored as ''."""
    conn.execute(
        """
        INSERT INTO site_meta (site, name, description, responsible)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(site) DO UPDATE SET
            name = excluded.name, description = excluded.description, responsible = excluded.responsible
        """,
        (site, name, description, responsible),
    )
    conn.commit()


def delete_meta(conn, site):
    cur = conn.execute("DELETE FROM site_meta WHERE site = ?", (site,))
    conn.commit()
    return cur.rowcount
