"""Fetch the latest stable WordPress release."""

from . import config


def get_latest_version(session):
    r = session.get(config.LATEST_API, timeout=config.TIMEOUT)
    r.raise_for_status()
    return r.json()["offers"][0]["current"]
