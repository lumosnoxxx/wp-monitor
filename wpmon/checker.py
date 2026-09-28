"""Check one site or many: detect version, compare with latest."""

from concurrent.futures import ThreadPoolExecutor

from . import config
from .detector import NOT_FOUND, detect_version
from .version_utils import compare


def check_site(session, site, latest):
    """Return a result dict for one (already normalized) site URL."""
    version, info = detect_version(session, site)
    if version is None:
        status = "UNKNOWN" if info == NOT_FOUND else "ERROR"
        return {"site": site, "version": "", "latest": latest, "status": status, "detail": info}
    return {
        "site": site,
        "version": version,
        "latest": latest,
        "status": compare(version, latest),
        "detail": f"via {info}",
    }


def check_all(session, sites, latest, workers=config.MAX_WORKERS):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda s: check_site(session, s, latest), sites))


def has_problems(results):
    return any(r["status"].startswith("OUTDATED") or r["status"] == "ERROR" for r in results)
