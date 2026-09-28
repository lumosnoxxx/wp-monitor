"""Running the checks: a blocking function and a background wrapper for the web UI."""

import threading
from contextlib import closing

import requests

from . import config, storage
from .checker import check_all
from .latest import get_latest_version
from .sites import read_sites


def run_check(db_path, sites, workers=config.MAX_WORKERS):
    """Check `sites`, save the results in the DB, return (results, latest_version).

    Raises RuntimeError if the latest WordPress version can't be fetched.
    """
    session = requests.Session()
    session.headers["User-Agent"] = config.USER_AGENT

    try:
        latest = get_latest_version(session)
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Could not fetch latest WordPress version: {e}") from e

    results = check_all(session, sites, latest, workers)
    with closing(storage.connect(db_path)) as conn:
        storage.save_results(conn, results)
    return results, latest


class BackgroundCheck:
    """Runs one check at a time (all sites, or a single site) in a background thread."""

    def __init__(self, db_path, sites_file):
        self.db_path = db_path
        self.sites_file = sites_file
        self._lock = threading.Lock()
        self._running = False
        self._target = None          # the single site being checked, None = all sites
        self._last_error = None

    def start(self, site=None):
        """Start a check of `site`, or of every site in the file if `site` is None.

        Returns False if a check is already running.
        """
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._target = site
            self._last_error = None
        threading.Thread(target=self._work, args=(site,), daemon=True).start()
        return True

    def _work(self, site):
        error = None
        try:
            sites = [site] if site else read_sites(self.sites_file)
            if not sites:
                raise RuntimeError("No sites to check.")
            run_check(self.db_path, sites)
        except Exception as e:  # keep the thread from dying silently
            error = str(e)
        with self._lock:
            self._last_error = error
            self._running = False
            self._target = None

    def snapshot(self):
        with self._lock:
            return {"running": self._running, "target": self._target,
                    "last_error": self._last_error}
