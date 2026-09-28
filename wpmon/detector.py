"""Detect the WordPress core version of a site.

Each detection method is a small function taking the response text and
returning a version string or None. To add a new method, write the
extractor and add one line to METHODS.
"""

import re

import requests

from . import config

VERSION = r"(\d+\.\d+(?:\.\d+)?)"


def _from_meta(text):
    for tag in re.findall(r"<meta[^>]*>", text, re.I):
        if re.search(r'name=["\']generator["\']', tag, re.I):
            m = re.search(r'content=["\']WordPress\s+' + VERSION, tag, re.I)
            if m:
                return m.group(1)
    return None


def _regex(pattern):
    def extract(text):
        m = re.search(pattern, text, re.I)
        return m.group(1) if m else None
    return extract


# (method name, path on the site, extractor)  - tried in this order
METHODS = [
    ("meta generator", "/", _from_meta),
    ("rss feed", "/feed/", _regex(r"wordpress\.org/\?v=" + VERSION)),
    ("readme.html", "/readme.html", _regex(r"Version\s+" + VERSION)),
    ("opml", "/wp-links-opml.php", _regex(r'generator="WordPress/' + VERSION)),
]

NOT_FOUND = "version hidden or not WordPress"


def detect_version(session, base_url):
    """Return (version, method_name) or (None, reason)."""
    last_error = None
    for name, path, extract in METHODS:
        try:
            r = session.get(base_url + path, timeout=config.TIMEOUT, allow_redirects=True)
            if r.status_code != 200:
                continue
            version = extract(r.text)
            if version:
                return version, name
        except requests.RequestException as e:
            last_error = type(e).__name__
    return None, (last_error or NOT_FOUND)
